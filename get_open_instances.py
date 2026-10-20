"""Manual check of all RegVil instances in Altinn Storage that are not completed.

Not wired into app.py - run by hand (ENV is taken from .env, like get_data_from_storage.py):

    python get_open_instances.py
    python get_open_instances.py --app regvil-2025-status

For every open instance it reports who it was sent to and whether the recipient has
started, and flags problems:
  no_data_element             instance without form data (failed instantiation leftover)
  no_report_tag               form data has no report id tag, the flow cannot match it
  no_levert_blob              no <Skjema>Levert blob, so it was not created by the event flow
  no_notification             no Varsling1Send logged for it since it was created
  notification_not_delivered  the last notification has no receipt, or was not delivered
  duplicate_open              another open instance in the same app has the same report id
  superseded                  a newer instance (any app) exists for the same report id
  soft_deleted                instance is soft deleted but still listed
  overdue                     dueBefore has passed

Output: storage_export/<ENV>/open_instances.csv
"""
import argparse
import json
import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from clients.instance_client import get_meta_data_info
from config.config_loader import load_full_config
from config.utils import connect_blob, to_utc_aware
from get_data_from_storage import (
    APPS,
    BLOB_READ_WORKERS,
    CHAIN_TOLERANCE,
    ENV,
    OUTPUT_DIR,
    PATH_TO_CONFIG_FOLDER,
    EventLog,
    StorageReader,
    _get,
    expected_next_app,
    is_completed,
    is_test_report,
    write_csv,
)

DELIVERED = "Email_Delivered"
# An instance created this soon after a Downloaded blob was written came from that download.
SAME_ATTEMPT = timedelta(minutes=2)


def _parse(value: Optional[str]) -> Optional[datetime]:
    try:
        return to_utc_aware(value) if value else None
    except ValueError:
        return None


def _data_element(instance: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        return get_meta_data_info(instance.get("data") or [])
    except ValueError:
        return None


class Notifications:
    """The Varsling blobs in <ENV>/varsling/, named <report id>_<app>_<event>_<shipment id>.json."""

    def __init__(self, container):
        self.container = container
        prefix = f"{ENV}/varsling/"
        names = [blob.name for blob in container.list_blobs(name_starts_with=prefix) if blob.name.endswith(".json")]
        with ThreadPoolExecutor(BLOB_READ_WORKERS) as pool:
            blobs = list(pool.map(self._read, names))

        self.sent: Dict[tuple, List[Dict[str, Any]]] = {}  # (report id, app) -> sends
        self.receipts: Dict[str, Dict[str, Any]] = {}      # shipment id -> receipt blob
        for name, blob in zip(names, blobs):
            parts = name[len(prefix):-len(".json")].split("_")
            if blob is None or len(parts) < 4:
                continue
            report_id, app_name, event_type, shipment_id = parts[0], parts[1], parts[2], "_".join(parts[3:])
            if event_type.endswith("Send"):
                self.sent.setdefault((report_id, app_name), []).append({**blob, "shipment_id": shipment_id})
            elif "Recieved" in event_type or "Received" in event_type:
                self.receipts[shipment_id] = blob
        logging.info(f"OPEN:{sum(len(v) for v in self.sent.values())} notifications and "
                     f"{len(self.receipts)} receipts in varsling")

    def _read(self, name: str) -> Optional[Dict[str, Any]]:
        try:
            return json.loads(self.container.get_blob_client(name).download_blob().readall())
        except Exception as e:
            logging.error(f"OPEN:Error reading blob {name}: {e}")
            return None

    def since(self, report_id: Optional[str], app_name: str, created: Optional[datetime]) -> List[Dict[str, Any]]:
        sends = self.sent.get((report_id, app_name), [])
        if created:
            sends = [s for s in sends if (_parse(s.get("processed_timestamp")) or created) >= created - CHAIN_TOLERANCE]
        return sorted(sends, key=lambda s: s.get("processed_timestamp") or "")

    def delivery_status(self, shipment_id: str) -> Optional[str]:
        receipt = self.receipts.get(shipment_id)
        if not receipt:
            return None
        recipients = (receipt.get("shipment_status") or {}).get("recipients") or [{}]
        return recipients[0].get("status")


def possible_sources(app_name: str, org_number: Optional[str], created: Optional[datetime], configs, event_logs,
                     by_report: Dict[Optional[str], List[tuple]], completed_at: Dict[str, Optional[str]]) -> List[str]:
    """Downloaded skjemas that could have created this (empty) instance: same org, the next app
    after them is this app, downloaded/completed before it was created, and no working instance
    of this app was created for their report id in between. Best match first."""
    if not created:
        return []
    candidates = []
    for source_app, event_log in event_logs.items():
        for source_guid, blob in event_log.downloaded.items():
            if blob.get("org_number") != org_number:
                continue
            if expected_next_app(configs[source_app], source_app, blob.get("data") or {}) != app_name:
                continue
            downloaded_at = _parse(blob.get("processed_timestamp"))
            start = _parse(completed_at.get(source_guid)) or downloaded_at
            if not start or start > created + CHAIN_TOLERANCE:
                continue
            report_id = blob.get("digitaliseringstiltak_report_id")
            if is_test_report(report_id):
                continue
            served = any(item[0] == app_name and item[2] and item[4] and start <= item[4] < created
                         for item in by_report.get(report_id, []))
            if served:
                continue
            last_attempt = bool(downloaded_at) and downloaded_at - CHAIN_TOLERANCE <= created <= downloaded_at + SAME_ATTEMPT
            candidates.append((not last_attempt, created - start,
                               f"{source_app}:{source_guid} (report {report_id}, "
                               f"completed {completed_at.get(source_guid) or '?'}"
                               f"{', last attempt' if last_attempt else ''})"))
    return [text for *_, text in sorted(candidates)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Check RegVil instances in Altinn Storage that are not completed.")
    parser.add_argument("--app", choices=APPS, help="Only report this app (default: all)")
    args = parser.parse_args()
    app_names = [args.app] if args.app else APPS
    now = datetime.now(timezone.utc)

    configs = {app_name: load_full_config(PATH_TO_CONFIG_FOLDER, app_name, ENV) for app_name in APPS}
    readers = {app_name: StorageReader(configs[app_name]) for app_name in APPS}
    container = connect_blob()
    if not container:
        raise RuntimeError("OPEN:No blob connection - needed to check event_log and varsling")
    event_logs = {app_name: EventLog(container, app_name, configs[app_name]) for app_name in APPS}
    notifications = Notifications(container)

    # every instance of every app, to find newer instances for the same report id
    all_instances: List[tuple] = []
    for app_name in APPS:
        for instance in readers[app_name].fetch_all_instances():
            if (instance.get("status") or {}).get("isHardDeleted"):
                continue
            data_element = _data_element(instance)
            tags = (data_element or {}).get("tags") or []
            guid = instance["id"].split("/")[1]
            report_id = tags[0] if tags else event_logs[app_name].report_id_from_levert(guid)
            created = _parse(instance.get("created") or (data_element or {}).get("created"))
            all_instances.append((app_name, instance, data_element, report_id, created))

    by_report: Dict[Optional[str], List[tuple]] = {}
    for item in all_instances:
        by_report.setdefault(item[3], []).append(item)
    completed_at = {item[1]["id"].split("/")[1]: (item[1].get("process") or {}).get("ended") for item in all_instances}

    rows: List[Dict[str, Any]] = []
    for app_name, instance, data_element, report_id, created in all_instances:
        if app_name not in app_names or is_completed(instance) or is_test_report(report_id):
            continue
        party_id, guid = instance["id"].split("/")
        status = instance.get("status") or {}
        levert = event_logs[app_name].levert.get(guid)
        flags = []

        form = (levert or {}).get("data")
        if form is None and data_element:
            form = readers[app_name].fetch_form(instance, data_element)
        form = form or {}

        sources: List[str] = []
        if not data_element:
            flags.append("no_data_element")
            sources = possible_sources(app_name, instance["instanceOwner"].get("organisationNumber"), created,
                                       configs, event_logs, by_report, completed_at)
        elif not data_element.get("tags"):
            flags.append("no_report_tag")
        if not levert:
            flags.append("no_levert_blob")

        sends = notifications.since(report_id, app_name, created)
        last_send = sends[-1] if sends else None
        delivery = notifications.delivery_status(last_send["shipment_id"]) if last_send else None
        if not sends:
            flags.append("no_notification")
        elif delivery != DELIVERED:
            flags.append("notification_not_delivered")

        others = [item for item in by_report.get(report_id, []) if item[1]["id"] != instance["id"]] if report_id else []
        if any(item[0] == app_name and not is_completed(item[1]) for item in others):
            flags.append("duplicate_open")
        newer = [item for item in others if created and item[4] and item[4] > created]
        if newer:
            flags.append("superseded")
        if status.get("isSoftDeleted"):
            flags.append("soft_deleted")
        due_before = _parse(instance.get("dueBefore"))
        if due_before and due_before < now:
            flags.append("overdue")

        visible_after = _parse(instance.get("visibleAfter"))
        rows.append({
            "app_name": app_name,
            "instancePartyId": party_id,
            "instanceId": guid,
            "digitaliseringstiltak_report_id": report_id,
            "org_number": instance["instanceOwner"].get("organisationNumber"),
            "virksomhets_name": _get(form, "Prefill.AnsvarligVirksomhet.Navn"),
            "digitaliseringstiltak": _get(form, "Prefill.Tiltak.Nummer"),
            "tiltak_navn": _get(form, "Prefill.Tiltak.Tekst"),
            "created": created.isoformat() if created else None,
            "visibleAfter": instance.get("visibleAfter"),
            "is_visible": visible_after is None or visible_after <= now,
            "days_visible": (now - visible_after).days if visible_after and visible_after <= now else None,
            "dueBefore": instance.get("dueBefore"),
            "readStatus": status.get("readStatus"),
            # the form is created by the service owner; any later change is the recipient working on it
            "started_by_user": bool(data_element) and data_element.get("createdBy") != data_element.get("lastChangedBy"),
            "data_last_changed": (data_element or {}).get("lastChanged"),
            "notifications_sent": len(sends),
            "last_notification_send_time": (last_send or {}).get("sent_time"),
            "last_notification_recipient": (last_send or {}).get("recipientEmail"),
            "last_notification_delivery": delivery,
            "superseded_by": ", ".join(f"{item[0]}:{item[1]['id'].split('/')[1]}" for item in newer),
            "flags": "; ".join(flags),
            "possible_source_count": len(sources) if not data_element else None,
            "possible_source": " | ".join(sources),
        })

    rows.sort(key=lambda r: (r["app_name"], r["visibleAfter"] or ""))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if rows:
        write_csv(OUTPUT_DIR / "open_instances.csv", rows)

    for app_name in app_names:
        app_rows = [r for r in rows if r["app_name"] == app_name]
        visible = sum(1 for r in app_rows if r["is_visible"])
        started = sum(1 for r in app_rows if r["started_by_user"])
        flag_counts = Counter(flag for r in app_rows for flag in r["flags"].split("; ") if flag)
        print(f"{app_name}: {len(app_rows)} open ({visible} visible, {started} started by the recipient)")
        for flag, count in flag_counts.most_common():
            print(f"    {flag:<28} {count}")
    print(f"Output written to {OUTPUT_DIR / 'open_instances.csv'}")


if __name__ == "__main__":
    main()
