"""Hard delete empty instances (no form data) listed in a CSV.

The CSV is ;-separated with at least the columns app_name;instancePartyId;instanceId,
so a filtered copy of storage_export/<ENV>/open_instances.csv works as it is.
ENV is taken from .env, like get_data_from_storage.py.

    python delete_empty_instances.py empty_instances.csv            # check only, nothing deleted
    python delete_empty_instances.py empty_instances.csv --delete   # delete

Every instance is fetched from Storage first and is only deleted if it belongs to the
given app, is not completed and has no DataModel data element. Anything else is skipped.
"""
import argparse
import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from clients.instance_client import make_api_call
from config.config_loader import load_full_config
from get_data_from_storage import APPS, ENV, OUTPUT_DIR, PATH_TO_CONFIG_FOLDER, StorageReader, is_completed, write_csv

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def check(reader: StorageReader, app_name: str, party_id: str, instance_id: str) -> Optional[str]:
    """None if the instance is safe to delete, otherwise the reason to skip it."""
    url = f"{reader.client.base_platfrom_url}/{party_id}/{instance_id}"
    response = make_api_call("GET", url, headers=reader.headers())
    if response is None:
        return "could not fetch instance"
    if response.status_code == 404:
        return "not found (already deleted?)"
    if response.status_code != 200:
        return f"could not fetch instance: {response.status_code}"
    instance = response.json()
    if instance.get("appId") != f"{reader.client.application_owner_organisation}/{app_name}":
        return f"belongs to {instance.get('appId')}, not {app_name}"
    if (instance.get("status") or {}).get("isHardDeleted"):
        return "already hard deleted"
    if is_completed(instance):
        return "instance is completed"
    if any(element.get("dataType") in ("DataModel", "model") for element in instance.get("data") or []):
        return "instance has form data"
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Hard delete empty instances listed in a CSV.")
    parser.add_argument("csv_file", type=Path, help="CSV with app_name;instancePartyId;instanceId")
    parser.add_argument("--delete", action="store_true", help="Actually delete (default: only check)")
    args = parser.parse_args()

    with open(args.csv_file, encoding="utf-8-sig") as file:
        targets = [(row["app_name"].strip(), row["instancePartyId"].strip(), row["instanceId"].strip())
                   for row in csv.DictReader(file, delimiter=";")]
    unknown = {app_name for app_name, _, _ in targets} - set(APPS)
    if unknown:
        raise ValueError(f"Unknown app_name in CSV: {', '.join(sorted(unknown))}")

    print(f"ENV={ENV}, {len(targets)} instances, {'DELETING' if args.delete else 'check only'}")
    readers: Dict[str, StorageReader] = {}
    results = []
    for app_name, party_id, instance_id in targets:
        if app_name not in readers:
            readers[app_name] = StorageReader(load_full_config(PATH_TO_CONFIG_FOLDER, app_name, ENV))
        reader = readers[app_name]

        reason = check(reader, app_name, party_id, instance_id)
        if reason:
            result = f"skipped: {reason}"
        elif not args.delete:
            result = "empty - would be deleted"
        else:
            response = reader.client.delete_instance(party_id, instance_id)
            if response is not None and response.status_code in (200, 204):
                result = "deleted"
            else:
                result = f"delete failed: {getattr(response, 'status_code', None)} {getattr(response, 'text', '')}"
        print(f"{app_name} {party_id}/{instance_id}: {result}")
        results.append({"app_name": app_name, "instancePartyId": party_id, "instanceId": instance_id, "result": result})

    if args.delete:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        log_file = OUTPUT_DIR / f"deleted_instances_{datetime.now():%Y%m%d_%H%M%S}.csv"
        write_csv(log_file, results)
        print(f"Result written to {log_file}")


if __name__ == "__main__":
    main()
