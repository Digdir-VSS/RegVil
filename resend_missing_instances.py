"""Create the next skjema for downloads where the event flow failed to create it.

Uses the chain.csv written by get_data_from_storage.py (rows with status
missing_next_instance) and the data in the <Skjema>Downloaded blob, i.e. exactly
what the event flow downloaded from the previous skjema. Nothing is re-downloaded
and no tags are touched.

    python resend_missing_instances.py                 # show what would be sent
    python resend_missing_instances.py --diagnose      # compare against payloads that worked
    python resend_missing_instances.py --send          # create the instances and notify
    python resend_missing_instances.py --send --instance regvil-2025-oppstart:<instance guid>
"""
import argparse
import csv
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from config.config_loader import load_full_config
from config.utils import connect_blob, to_utc_aware
from get_data_from_storage import APPS, ENV, OUTPUT_DIR, PATH_TO_CONFIG_FOLDER, EventLog, expected_next_app

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def read_missing_from_chain() -> List[tuple]:
    with open(OUTPUT_DIR / "chain.csv", encoding="utf-8-sig") as file:
        return [(row["app_name"], row["instanceId"]) for row in csv.DictReader(file, delimiter=";")
                if row["status"] == "missing_next_instance"]


# ---------------------------------------------------------------- Diagnosis

def _signature(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "object"
    text = str(value).strip()
    if text == "":
        return "empty string"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}(T.*)?", text):
        return "date string"
    if re.fullmatch(r"-?\d+([.,]\d+)?", text):
        return "numeric string"
    return "text"


def _signatures(data: Any, path: str = "", found: Optional[Dict[str, set]] = None) -> Dict[str, set]:
    """path -> value signatures; list items share one path (Leveranser[].Beskrivelse)."""
    found = {} if found is None else found
    if path:
        found.setdefault(path, set()).add(_signature(data))
    if isinstance(data, dict):
        for key, value in data.items():
            _signatures(value, f"{path}.{key}" if path else key, found)
    elif isinstance(data, list):
        for item in data:
            _signatures(item, f"{path}[]", found)
    return found


def diagnose(failing: List[Dict[str, Any]], event_logs: Dict[str, EventLog]) -> None:
    for next_app in sorted({item["next_app"] for item in failing if item["next_app"]}):
        created = event_logs[next_app].levert.values()
        known: Dict[str, set] = {}
        for blob in created:
            for path, signatures in _signatures(blob.get("data") or {}).items():
                known.setdefault(path, set()).update(signatures)

        first_failure = min(to_utc_aware(item["downloaded_at"]) for item in failing
                            if item["next_app"] == next_app and item["downloaded_at"])
        created_since = sum(1 for blob in created if blob.get("processed_timestamp")
                            and to_utc_aware(blob["processed_timestamp"]) >= first_failure)
        print(f"\n{next_app}: {len(created)} instances created successfully in total, "
              f"{created_since} since the first failure ({first_failure:%Y-%m-%d %H:%M})")
        if created_since == 0:
            print("  -> nothing has been created since then: points to the app (deploy, config), not the data")

        for item in failing:
            if item["next_app"] != next_app:
                continue
            print(f"  {item['app_name']} {item['instanceId']} (report {item['report_id']}):")
            unusual = []
            for path, signatures in _signatures(item["data"]).items():
                if path not in known:
                    unusual.append(f"{path}: never present in a payload that worked")
                elif not signatures <= known[path]:
                    unusual.append(f"{path}: {', '.join(sorted(signatures - known[path]))} "
                                   f"(worked with: {', '.join(sorted(known[path]))})")
            for line in unusual or ["no field differs in type from payloads that worked"]:
                print(f"    {line}")


# ---------------------------------------------------------------- Run

def main() -> None:
    parser = argparse.ArgumentParser(description="Create missing next skjema instances.")
    parser.add_argument("--instance", action="append",
                        help="<app name>:<instance guid> of the downloaded skjema (default: all missing in chain.csv)")
    parser.add_argument("--diagnose", action="store_true", help="Compare the payloads with ones that worked")
    parser.add_argument("--send", action="store_true", help="Create the instances and send notifications")
    args = parser.parse_args()

    targets = [tuple(value.split(":", 1)) for value in args.instance] if args.instance else read_missing_from_chain()
    if not targets:
        print("Nothing to resend")
        return

    configs = {app_name: load_full_config(PATH_TO_CONFIG_FOLDER, app_name, ENV) for app_name in APPS}
    container = connect_blob()
    event_logs = {app_name: EventLog(container, app_name, configs[app_name]) for app_name in APPS}

    items = []
    for app_name, instance_guid in targets:
        blob = event_logs[app_name].downloaded.get(instance_guid)
        if not blob:
            print(f"{app_name} {instance_guid}: no Downloaded blob, skipped")
            continue
        data = blob.get("data") or {}
        next_app = expected_next_app(configs[app_name], app_name, data)
        try:
            dato = configs[app_name].app_config.get_date(data)
        except Exception as e:
            dato = None
            print(f"{app_name} {instance_guid}: could not compute visibleAfter: {e}")
        items.append({
            "app_name": app_name,
            "instanceId": instance_guid,
            "org_number": blob.get("org_number"),
            "report_id": blob.get("digitaliseringstiltak_report_id"),
            "downloaded_at": blob.get("processed_timestamp"),
            "next_app": next_app,
            "dato": dato,
            "data": data,
        })
        print(f"{app_name} {instance_guid}: org {blob.get('org_number')} report "
              f"{blob.get('digitaliseringstiltak_report_id')} -> {next_app}, visibleAfter {dato}")
    if args.diagnose:
        diagnose(items, event_logs)
        debug_dir = OUTPUT_DIR / "resend_payloads"
        debug_dir.mkdir(parents=True, exist_ok=True)
        for item in items:
            with open(debug_dir / f"{item['app_name']}_{item['instanceId']}.json", "w", encoding="utf-8") as file:
                json.dump(item["data"], file, ensure_ascii=False, indent=4)
        print(f"\nPayloads written to {debug_dir}")

    if not args.send:
        return

    # imported here: these modules fetch the Maskinporten secret when imported
    from upload_single_skjema import run as upload_skjema
    from send_warning import run as send_notification

    for item in items:
        if not item["next_app"] or not item["report_id"] or not item["dato"]:
            print(f"{item['instanceId']}: missing next app, report id or date - not sent")
            continue
        params = {
            "org_number": item["org_number"],
            "digitaliseringstiltak_report_id": item["report_id"],
            "dato": item["dato"],
            "app_name": item["next_app"],
            "prefill_data": item["data"],
        }
        result = upload_skjema(**params)
        print(f"{item['instanceId']}: upload {result}")
        if result != 200:
            continue
        next_config = configs[item["next_app"]].app_config
        notification = send_notification(**params, email_subject=next_config.emailSubject,
                                         email_body=next_config.emailBody)
        print(f"{item['instanceId']}: notification {notification}")


if __name__ == "__main__":
    main()
