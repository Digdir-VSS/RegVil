"""Send the notification for open instances that never got one.

Reads the rows flagged no_notification in storage_export/<ENV>/open_instances.csv (from
get_open_instances.py, so run that first), or any ;-separated CSV with the columns
app_name;instancePartyId;instanceId. ENV is taken from .env.

    python send_missing_notifications.py                    # show what would be sent
    python send_missing_notifications.py --send             # send
    python send_missing_notifications.py my_list.csv --send

Send time is taken from the instance's own visibleAfter in Storage: instances that are
already visible are notified now (+1 minute), the others are scheduled for exactly the
moment they become visible. Before sending, every instance is checked again in Storage
and in the varsling log, so running it twice does not notify anybody twice.
Sent notifications are logged as Varsling1Send, like send_warning.py, so
notification_status.py picks them up.
"""
import argparse
import csv
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from clients.instance_client import make_api_call
from clients.instance_logging import InstanceTracker
from clients.varsling_client import AltinnVarslingClient
from config.config_loader import load_full_config
from config.utils import connect_blob
from get_data_from_storage import APPS, ENV, OUTPUT_DIR, PATH_TO_CONFIG_FOLDER, StorageReader, _get, is_completed, write_csv
from get_open_instances import Notifications, _data_element, _parse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Rows with these flags are not notified: nobody should be sent to an old, deleted or broken form.
BLOCKING_FLAGS = {"superseded", "soft_deleted", "no_data_element", "duplicate_open"}


def _format(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def send_time_for(visible_after: Optional[datetime], now: datetime) -> str:
    if visible_after is None or visible_after <= now:
        return _format(now + timedelta(minutes=1))
    return _format(visible_after)


def read_targets(csv_file: Path) -> list[Dict[str, str]]:
    with open(csv_file, encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file, delimiter=";"))
    if rows and "flags" in rows[0]:
        rows = [row for row in rows if "no_notification" in row["flags"].split("; ")]
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Notify open instances that never got a notification.")
    parser.add_argument("csv_file", type=Path, nargs="?", default=OUTPUT_DIR / "open_instances.csv",
                        help="CSV with app_name;instancePartyId;instanceId (default: open_instances.csv)")
    parser.add_argument("--send", action="store_true", help="Actually send (default: only show)")
    args = parser.parse_args()

    targets = read_targets(args.csv_file)
    print(f"ENV={ENV}, {len(targets)} instances, {'SENDING' if args.send else 'check only'}")
    if not targets:
        return

    configs = {app_name: load_full_config(PATH_TO_CONFIG_FOLDER, app_name, ENV) for app_name in APPS}
    readers = {app_name: StorageReader(configs[app_name]) for app_name in APPS}
    container = connect_blob()
    if not container:
        raise RuntimeError("NOTIFY:No blob connection - needed to check for earlier notifications")
    notifications = Notifications(container)
    tracker = InstanceTracker.from_directory(f"{ENV}/varsling/")
    now = datetime.now(timezone.utc)

    results = []
    for target in targets:
        app_name = target["app_name"].strip()
        party_id, instance_id = target["instancePartyId"].strip(), target["instanceId"].strip()
        result: Dict[str, Any] = {"app_name": app_name, "instancePartyId": party_id, "instanceId": instance_id}
        results.append(result)

        def skip(reason: str) -> None:
            result["result"] = f"skipped: {reason}"
            print(f"{app_name} {party_id}/{instance_id}: {result['result']}")

        if app_name not in APPS:
            skip("unknown app_name")
            continue
        blocking = BLOCKING_FLAGS & set(target.get("flags", "").split("; "))
        if blocking:
            skip(f"flagged {', '.join(sorted(blocking))}")
            continue

        reader = readers[app_name]
        response = make_api_call("GET", f"{reader.client.base_platfrom_url}/{party_id}/{instance_id}",
                                 headers=reader.headers())
        if response is None or response.status_code != 200:
            skip(f"could not fetch instance: {getattr(response, 'status_code', None)}")
            continue
        instance = response.json()
        status = instance.get("status") or {}
        if instance.get("appId") != f"{reader.client.application_owner_organisation}/{app_name}":
            skip(f"belongs to {instance.get('appId')}")
            continue
        if is_completed(instance) or status.get("isSoftDeleted") or status.get("isHardDeleted"):
            skip("completed or deleted")
            continue
        data_element = _data_element(instance)
        tags = (data_element or {}).get("tags") or []
        report_id = tags[0] if tags else (target.get("digitaliseringstiltak_report_id") or "").strip()
        if not data_element or not report_id:
            skip("no form data or no report id")
            continue

        created = _parse(instance.get("created") or data_element.get("created"))
        if notifications.since(report_id, app_name, created):
            skip("already notified")
            continue

        form = reader.fetch_form(instance, data_element) or {}
        recipient = _get(form, "Prefill.Kontaktperson.EPostadresse")
        org_name = _get(form, "Prefill.AnsvarligVirksomhet.Navn")
        org_number = instance["instanceOwner"].get("organisationNumber")
        if not recipient:
            skip("no Prefill.Kontaktperson.EPostadresse in the form")
            continue

        send_time = send_time_for(_parse(instance.get("visibleAfter")), now)
        result.update({
            "digitaliseringstiltak_report_id": report_id,
            "org_number": org_number,
            "virksomhets_name": org_name,
            "visibleAfter": instance.get("visibleAfter"),
            "send_time": send_time,
            "recipient": recipient,
        })
        plan = f"report {report_id}, {recipient}, visibleAfter {instance.get('visibleAfter')} -> send {send_time}"

        if not args.send:
            result["result"] = "would be sent"
            print(f"{app_name} {party_id}/{instance_id}: {plan}")
            continue

        app_config = configs[app_name].app_config
        response = AltinnVarslingClient.init_from_config(configs[app_name]).send_notification(
            recipient_email=recipient,
            subject=app_config.emailSubject,
            body=app_config.emailBody,
            send_time=send_time,
            appname=app_name,
        )
        if response is None or response.status_code != 201:
            result["result"] = f"failed: {getattr(response, 'status_code', None)} {getattr(response, 'text', '')}"
            print(f"{app_name} {party_id}/{instance_id}: {result['result']}")
            continue
        shipment_id = response.json()["notification"]["shipmentId"]
        tracker.logging_varlsing(org_number=org_number, org_name=org_name, app_name=app_name, send_time=send_time,
                                 digitaliseringstiltak_report_id=report_id, shipment_id=shipment_id,
                                 recipientEmail=recipient, event_type="Varsling1Send")
        result.update({"shipment_id": shipment_id, "result": "sent"})
        print(f"{app_name} {party_id}/{instance_id}: sent ({plan}), shipment {shipment_id}")

    if args.send:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        log_file = OUTPUT_DIR / f"sent_notifications_{datetime.now():%Y%m%d_%H%M%S}.csv"
        write_csv(log_file, results)
        print(f"Result written to {log_file}")


if __name__ == "__main__":
    main()
