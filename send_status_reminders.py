"""Send a reminder for every open skjema that should have been delivered by now.

Not wired into app.py - run by hand (ENV is taken from .env):

    python send_status_reminders.py --body-file reminder.txt          # dry run: writes every email to a .txt
    python send_status_reminders.py --body-file reminder.txt --send   # send
    python send_status_reminders.py --body-file reminder.txt --tiltak 10 11b --send          # only these tiltak
    python send_status_reminders.py --body-file reminder.txt --test-to me@digdir.no --limit 1 --send
    python send_status_reminders.py --body-file reminder.txt --app regvil-2025-status --send  # only status

By default every app is checked, so each tiltak is reminded about the skjema it is at now,
whether that is initiell, oppstart, status or slutt. An instance gets a reminder when it
  - has become visible before today (visibleAfter, Norwegian date),
  - is not completed, not archived and not (soft/hard) deleted,
  - has form data and a report id tag, and is not a test (ZZZ...),
  - is not superseded by a newer instance for the same report id (old round left open),
  - has not been notified in the last --skip-notified-days days (default 1, so a second run
    the same day does not send twice).

The email goes to Prefill.Kontaktperson, like send_warning.py, or with --recipient initiell
to the contact person the virksomhet gave in the initiell skjema. Every email address gets
one email, listing all its tiltak: in place of {tiltak} in the body, or appended at the end
when the body has no {tiltak}. It is sent now and logged as Varsling1Send once per tiltak
(all with the same shipment id), so notification_status.py picks up the delivery receipts.
"""
import argparse
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytz

from clients.instance_logging import InstanceTracker
from clients.varsling_client import AltinnVarslingClient
from config.config_loader import load_full_config
from config.utils import connect_blob
from get_data_from_storage import (
    APPS,
    ENV,
    OUTPUT_DIR,
    PATH_TO_CONFIG_FOLDER,
    StorageReader,
    _get,
    is_completed,
    is_test_report,
    write_csv,
)
from get_open_instances import Notifications, _data_element, _parse
from send_missing_notifications import _format
from tiltak_overview import tiltak_sort_key

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

OSLO = pytz.timezone("Europe/Oslo")
# How each skjema is named in the tiltak list of the email
SKJEMA_LABEL = {
    "regvil-2025-initiell": "registrering av tiltaket",
    "regvil-2025-oppstart": "oppstart av tiltaket",
    "regvil-2025-status": "statusrapportering",
    "regvil-2025-slutt": "sluttrapportering",
}


def recipient_for(form: Dict[str, Any], source: str) -> tuple:
    if source == "initiell" and _get(form, "Initiell.Kontaktperson.EPostadresse"):
        return _get(form, "Initiell.Kontaktperson.EPostadresse"), "initiell"
    return _get(form, "Prefill.Kontaktperson.EPostadresse"), "prefill"


def matching_tiltak(number: Optional[str], wanted: List[str]) -> Optional[str]:
    """The entry of --tiltak that this tiltak number matches; 11 also matches deltiltak 11a, 11b, ..."""
    number = str(number or "").strip().lower()
    for entry in wanted:
        entry = entry.strip().lower()
        if number == entry or (entry.isdigit() and re.fullmatch(rf"{entry}[a-z]+", number)):
            return entry
    return None


def body_with_tiltak(body: str, group: List[Dict[str, Any]]) -> str:
    lines = "\n".join(f"- Tiltak {r['digitaliseringstiltak'] or '?'}: {(r['tiltak_navn'] or '').strip()} "
                      f"({SKJEMA_LABEL[r['app_name']]})" for r in group)
    if "{tiltak}" in body:
        return body.replace("{tiltak}", lines)
    return f"{body.rstrip()}\n\nPåminnelsen gjelder følgende tiltak:\n{lines}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Remind the contact person of every overdue open skjema.")
    parser.add_argument("--app", choices=APPS, help="Only this app (default: all, each tiltak's current skjema)")
    parser.add_argument("--subject", help="Email subject (default: emailSubject of the app, or of status)")
    parser.add_argument("--body-file", type=Path, help="UTF-8 text file with the email body (default: emailBody of the app, or of status)")
    parser.add_argument("--recipient", choices=["prefill", "initiell"], default="prefill",
                        help="Contact person to email: Prefill.Kontaktperson (default) or Initiell.Kontaktperson")
    parser.add_argument("--skip-notified-days", type=int, default=1,
                        help="Skip instances notified in the last N days (default 1)")
    parser.add_argument("--tiltak", nargs="+", metavar="NR",
                        help="Only these tiltak, e.g. --tiltak 10 17 11b (11 also matches 11a, 11b, ...)")
    parser.add_argument("--test-to", metavar="EMAIL",
                        help="Send every email to this address instead (subject marked [TEST], nothing logged)")
    parser.add_argument("--limit", type=int, help="Send at most this many emails")
    parser.add_argument("--send", action="store_true", help="Actually send (default: only show)")
    args = parser.parse_args()

    configs = {app_name: load_full_config(PATH_TO_CONFIG_FOLDER, app_name, ENV) for app_name in APPS}
    default_app = args.app or "regvil-2025-status"
    app_config = configs[default_app].app_config
    subject = args.subject or app_config.emailSubject
    body = args.body_file.read_text(encoding="utf-8") if args.body_file else app_config.emailBody
    if not subject or not body:
        raise ValueError("Email subject and body must not be empty")

    now = datetime.now(timezone.utc)
    start_of_today = OSLO.localize(datetime.combine(now.astimezone(OSLO).date(), datetime.min.time()))
    notified_since = now - timedelta(days=args.skip_notified_days)

    readers = {app_name: StorageReader(configs[app_name]) for app_name in APPS}
    container = connect_blob()
    if not container:
        raise RuntimeError("REMINDER:No blob connection - needed to check earlier notifications")
    notifications = Notifications(container)

    # every instance of every app, to see if a newer one exists for the same report id
    newest_created: Dict[str, datetime] = {}
    candidates = []
    for app_name in APPS:
        for instance in readers[app_name].fetch_all_instances():
            data_element = _data_element(instance)
            tags = (data_element or {}).get("tags") or []
            created = _parse(instance.get("created") or (data_element or {}).get("created"))
            if tags and created and not (instance.get("status") or {}).get("isHardDeleted"):
                newest_created[tags[0]] = max(created, newest_created.get(tags[0], created))
            if args.app in (None, app_name):
                candidates.append((app_name, instance, data_element, tags[0] if tags else None, created))

    mode = "check only" if not args.send else f"TEST SENDING to {args.test_to}" if args.test_to else "SENDING"
    print(f"ENV={ENV}, {args.app or 'all apps'}, visible before {start_of_today:%Y-%m-%d}, {mode}"
          f"{', tiltak ' + ' '.join(args.tiltak) if args.tiltak else ''}\nSubject: {subject}\n")
    matched_tiltak: set = set()
    results: List[Dict[str, Any]] = []
    tracker = InstanceTracker.from_directory(f"{ENV}/varsling/")
    varsling_client = AltinnVarslingClient.init_from_config(configs[default_app])
    skipped: Dict[str, int] = {}

    for app_name, instance, data_element, report_id, created in candidates:
        status = instance.get("status") or {}
        visible_after = _parse(instance.get("visibleAfter"))

        reason = None
        if is_completed(instance) or status.get("isArchived"):
            reason = "completed"
        elif status.get("isHardDeleted") or status.get("isSoftDeleted"):
            reason = "deleted"
        elif not data_element:
            reason = "no form data"
        elif not report_id:
            reason = "no report id tag"
        elif is_test_report(report_id):
            reason = "test"
        elif not visible_after or visible_after >= start_of_today:
            reason = "not visible before today"
        elif created and newest_created.get(report_id, created) > created:
            reason = "superseded by a newer instance"
        elif any((_parse(s.get("processed_timestamp")) or now) >= notified_since
                 for s in notifications.sent.get((report_id, app_name), [])):
            reason = f"notified in the last {args.skip_notified_days} day(s)"
        if reason:
            skipped[reason] = skipped.get(reason, 0) + 1
            continue

        party_id, instance_id = instance["id"].split("/")
        form = readers[app_name].fetch_form(instance, data_element) or {}
        if args.tiltak:
            wanted = matching_tiltak(_get(form, "Prefill.Tiltak.Nummer"), args.tiltak)
            if not wanted:
                skipped["not in --tiltak"] = skipped.get("not in --tiltak", 0) + 1
                continue
            matched_tiltak.add(wanted)
        recipient, recipient_source = recipient_for(form, args.recipient)
        org_number = instance["instanceOwner"].get("organisationNumber")
        org_name = _get(form, "Prefill.AnsvarligVirksomhet.Navn")
        result = {
            "app_name": app_name,
            "instancePartyId": party_id,
            "instanceId": instance_id,
            "digitaliseringstiltak_report_id": report_id,
            "digitaliseringstiltak": _get(form, "Prefill.Tiltak.Nummer"),
            "org_number": org_number,
            "virksomhets_name": org_name,
            "visibleAfter": instance.get("visibleAfter"),
            "days_visible": (now - visible_after).days,
            "started_by_user": data_element.get("createdBy") != data_element.get("lastChangedBy"),
            "tiltak_navn": _get(form, "Prefill.Tiltak.Tekst"),
            "recipient": recipient,
            "recipient_source": recipient_source,
        }
        results.append(result)
        if not recipient:
            result["result"] = "skipped: no recipient email"

    # one email per address, listing all its tiltak
    by_recipient: Dict[str, List[Dict[str, Any]]] = {}
    for result in results:
        if result["recipient"]:
            by_recipient.setdefault(result["recipient"].strip().lower(), []).append(result)

    previews: List[str] = []
    groups = sorted(by_recipient.items())
    if args.limit is not None:
        groups = groups[:args.limit]
    for recipient, group in groups:
        group.sort(key=lambda r: tiltak_sort_key(r["digitaliseringstiltak"]))
        print(f"{recipient}: {len(group)} tiltak")
        for r in group:
            print(f"    {r['digitaliseringstiltak_report_id']:<6} tiltak {r['digitaliseringstiltak'] or '?':<5} "
                  f"{r['app_name'].replace('regvil-2025-', ''):<9} "
                  f"{r['virksomhets_name'] or r['org_number']} (visible {r['days_visible']} days, "
                  f"{'started' if r['started_by_user'] else 'not started'})")
        for r in group:
            r["tiltak_in_email"] = len(group)
        if not args.send:
            for r in group:
                r["result"] = "would be sent"
            previews.append(f"Til: {recipient}\nEmne: {subject}\nTiltak: {len(group)}\n\n{body_with_tiltak(body, group)}")
            continue

        send_time = _format(datetime.now(timezone.utc) + timedelta(minutes=1))
        response = varsling_client.send_notification(recipient_email=args.test_to or recipient,
                                                     subject=f"[TEST] {subject}" if args.test_to else subject,
                                                     body=body_with_tiltak(body, group),
                                                     send_time=send_time, appname=group[0]["app_name"])
        if response is None or response.status_code != 201:
            failure = f"failed: {getattr(response, 'status_code', None)} {getattr(response, 'text', '')}"
            for r in group:
                r["result"] = failure
            print(f"    {failure}")
            continue
        shipment_id = response.json()["notification"]["shipmentId"]
        if args.test_to:
            # not logged: a test must not count as the tiltak having been reminded
            for r in group:
                r.update({"send_time": send_time, "shipment_id": shipment_id, "result": f"test sent to {args.test_to}"})
            print(f"    test sent to {args.test_to}, shipment {shipment_id}")
            continue
        for r in group:
            tracker.logging_varlsing(org_number=r["org_number"], org_name=r["virksomhets_name"], app_name=r["app_name"],
                                     send_time=send_time, digitaliseringstiltak_report_id=r["digitaliseringstiltak_report_id"],
                                     shipment_id=shipment_id, recipientEmail=recipient, event_type="Varsling1Send")
            r.update({"send_time": send_time, "shipment_id": shipment_id, "result": "sent"})
        print(f"    sent, shipment {shipment_id}")

    for r in results:
        if not r["recipient"]:
            print(f"NO RECIPIENT: {r['digitaliseringstiltak_report_id']} tiltak {r['digitaliseringstiltak']} "
                  f"{r['virksomhets_name'] or r['org_number']} - skipped")
    for wanted in args.tiltak or []:
        if wanted.lower() not in matched_tiltak:
            print(f"Tiltak {wanted}: no open status form that passed the checks - see 'Not reminded' below")
    print(f"\n{len(results)} tiltak to remind, in {len(by_recipient)} emails"
          f"{f' (only {len(groups)} handled, --limit)' if len(groups) < len(by_recipient) else ''}. Not reminded: "
          + (", ".join(f"{reason} {count}" for reason, count in sorted(skipped.items())) or "none"))
    if results:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        kind = "sent" if args.send else "planned"
        log_file = OUTPUT_DIR / f"reminders_{kind}_{datetime.now():%Y%m%d_%H%M%S}.csv"
        write_csv(log_file, results)
        print(f"List written to {log_file}")
    if previews:
        preview_file = OUTPUT_DIR / f"reminders_preview_{datetime.now():%Y%m%d_%H%M%S}.txt"
        separator = "\n\n" + "=" * 70 + "\n\n"
        preview_file.write_text(separator.join(previews) + "\n", encoding="utf-8")
        print(f"Emails that would be sent written to {preview_file}")


if __name__ == "__main__":
    main()
