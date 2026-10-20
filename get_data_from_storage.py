"""Manual export of all RegVil instances straight from Altinn Storage.

Not wired into app.py - run by hand:

    python get_data_from_storage.py                      # all apps, completed instances
    python get_data_from_storage.py --app regvil-2025-oppstart
    python get_data_from_storage.py --include-open       # also instances not yet submitted

For every app it:
  1. pages through Storage (/storage/api/v1/instances) and collects every instance,
  2. downloads the form (DataModel element) from Storage and parses it,
  3. formats one row per instance in the column layout of the app's table,
  4. checks the event_log blobs written by the event flow:
     - every completed instance in Storage has a <Skjema>Downloaded blob, and the
       downloaded data matches Storage (reconciliation.csv),
     - every <Skjema>Downloaded blob, except for slutt, is followed by a
       <Skjema>Levert blob for the next instance of the same report id (chain.csv).

Output is written to storage_export/<ENV>/. Uploading to the database is not
implemented yet.
"""
import argparse
import csv
import json
import logging
import os
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from dotenv import load_dotenv

from clients.instance_client import AltinnInstanceClient, get_meta_data_info, make_api_call
from config.config_loader import APIConfig, load_full_config
from config.utils import connect_blob, to_utc_aware

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Must match the Maskinporten secret in .env (MASKINPORTEN_SECRET_NAME), or the token request fails.
ENV = os.getenv("ENV", "prod")
APPS = [
    "regvil-2025-initiell",
    "regvil-2025-oppstart",
    "regvil-2025-status",
    "regvil-2025-slutt",
]
PATH_TO_CONFIG_FOLDER = Path(__file__).parent / "config_files"
OUTPUT_DIR = Path(__file__).parent / "storage_export" / ENV

# Altinn tokens are short lived; get a new one this often instead of on every call.
TOKEN_REFRESH_SECONDS = 60
BLOB_READ_WORKERS = 16
# A Levert blob is written right after the Downloaded blob of the previous skjema;
# allow for small clock differences when pairing them.
CHAIN_TOLERANCE = timedelta(minutes=1)

# Report ids used for testing in production (ZZZ, ZZZa, ZZZb under tiltak 41): not real forms.
TEST_REPORT_ID_PREFIX = "ZZZ"


def is_test_report(report_id: Optional[str]) -> bool:
    return bool(report_id) and report_id.upper().startswith(TEST_REPORT_ID_PREFIX)

# Form fields that are lists in the data model. In XML a list with a single
# element looks like a plain child, so these are always forced to lists.
LIST_FIELDS = {
    "Leveranser",
    "HindringerLikert",
    "DrivereLikert",
    "AndreMaal",
    "AndreVirksomheter",
    "AndreKontaktpersoner",
}

# Columns that are expected to differ between Storage and the event_log blob
# (set at processing time, or changed by Altinn after the download happened).
NOT_COMPARED = {
    "event_type",
    "processed_timestamp",
    "instance_info_last_changed",
    "instance_info_last_changed_by",
    "endret_av",
    "endret",
}

METADATA_COLUMNS = [
    "org_number",
    "virksomhets_name",
    "processed_timestamp",
    "instancePartyId",
    "instanceId",
    "visibleAfter",
    "instance_info_last_changed",
    "instance_info_last_changed_by",
    "instance_info_created",
    "data_info_last_changed",
    "data_info_last_changed_by",
    "data_info_created",
    "data_info_dataGuid",
]

INITIELL_COLUMNS = [
    "event_type", "digitaliseringstiltak_report_id",
    "digitaliseringstiltak", "kapitell", "omrade", "tiltak_navn",
    *METADATA_COLUMNS,
    "TiltakKortnavn",
    "Kontaktperson_FulltNavn",
    "Kontaktperson_EPostadresse",
    "Kontaktperson_Telefonnummer",
    "ErTiltakPaabegynt",
    "DatoPaabegynt",
    "DatoForventetOppstart",
    "endret_av", "endret",
]

OPPSTART_COLUMNS = [
    "event_type", "digitaliseringstiltak_report_id",
    "digitaliseringstiltak", "omrade", "kapitell", "tiltak_navn",
    *METADATA_COLUMNS,
    "ForventetSluttdato",
    "HarKostnadsestimat",
    "Kostnadsestimat",
    "HarFinansiering",
    "Finansieringskilder",
    "endret_av", "endret",
]

STATUS_COLUMNS = [
    "event_type", "digitaliseringstiltak_report_id",
    "digitaliseringstiltak", "omrade", "kapitell", "tiltak_navn",
    *METADATA_COLUMNS,
    "ErArbeidAvsluttet",
    "TiltakStatus",
    "ForsinkelseTiltakBeskrivelse",
    "Nettside",
    "endret_av", "endret",
    "HindringerBeskrivelse",
    "DrivereBeskrivelse",
]

SLUTT_COLUMNS = [
    "event_type", "digitaliseringstiltak_report_id",
    "digitaliseringstiltak", "omrade", "kapitell", "tiltak_navn",
    *METADATA_COLUMNS,
    "TiltakArbeidBeskrivelse",
    "LaerdommerBeskrivelse",
    "endret_av", "endret",
]


# ---------------------------------------------------------------- Storage access

class StorageReader:
    def __init__(self, config: APIConfig):
        self.config = config
        self.client = AltinnInstanceClient.init_from_config(config)
        self._headers: Optional[Dict[str, str]] = None
        self._fetched_at = 0.0

    def headers(self) -> Dict[str, str]:
        if not self._headers or time.monotonic() - self._fetched_at > TOKEN_REFRESH_SECONDS:
            self._headers = self.client._get_headers("application/json")
            self._fetched_at = time.monotonic()
        return dict(self._headers)

    def fetch_all_instances(self) -> List[Dict[str, Any]]:
        """All instances of the app, following Storage's continuation links."""
        org = self.client.application_owner_organisation
        url = self.client.base_platfrom_url
        params: Optional[Dict[str, str]] = {"org": org, "appId": f"{org}/{self.client.appname}"}
        instances: List[Dict[str, Any]] = []
        while url:
            response = make_api_call("GET", url, headers=self.headers(), params=params)
            if response is None or response.status_code != 200:
                raise RuntimeError(f"STORAGE:Failed to list instances for {self.client.appname}: "
                                   f"{getattr(response, 'status_code', None)} {getattr(response, 'text', '')}")
            page = response.json()
            instances.extend(page.get("instances", []))
            url = page.get("next")
            params = None  # the next link already carries the query and continuation token
        logging.info(f"STORAGE:{self.client.appname}: {len(instances)} instances in Storage")
        return instances

    def fetch_form(self, instance: Dict[str, Any], data_element: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        url = f"{self.client.base_platfrom_url}/{instance['id']}/data/{data_element['id']}"
        headers = self.headers()
        headers["accept"] = data_element.get("contentType") or "*/*"
        response = make_api_call("GET", url, headers=headers)
        if response is None or response.status_code != 200:
            logging.error(f"STORAGE:Failed to download form for {instance['id']}: "
                          f"{getattr(response, 'status_code', None)}")
            return None
        if data_element.get("contentType") == "application/json":
            return response.json()
        return xml_to_dict(response.content)


# ---------------------------------------------------------------- XML parsing

def _local_name(tag: str) -> str:
    return tag.split("}")[-1]


def _element_to_value(element: ET.Element) -> Any:
    if element.attrib.get("{http://www.w3.org/2001/XMLSchema-instance}nil") == "true":
        return None
    children = list(element)
    if not children:
        text = (element.text or "").strip()
        if text == "":
            return None
        if text in ("true", "false"):
            return text == "true"
        return text

    result: Dict[str, Any] = {}
    for child in children:
        name = _local_name(child.tag)
        value = _element_to_value(child)
        if name in result:
            if not isinstance(result[name], list):
                result[name] = [result[name]]
            result[name].append(value)
        elif name in LIST_FIELDS:
            result[name] = [value]
        else:
            result[name] = value
    return result


def xml_to_dict(xml_bytes: bytes) -> Dict[str, Any]:
    """Altinn XML data model -> the same dict shape the app API returns as JSON."""
    root = ET.fromstring(xml_bytes)
    return _element_to_value(root) or {}


# ---------------------------------------------------------------- Formatting

def _get(data: Optional[Dict[str, Any]], path: str) -> Any:
    for key in path.split("."):
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def prefill_columns(form: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "digitaliseringstiltak": _get(form, "Prefill.Tiltak.Nummer"),
        "omrade": _get(form, "Prefill.Maal.Tekst"),
        "kapitell": _get(form, "Prefill.Kapittel.Tekst"),
        "tiltak_navn": _get(form, "Prefill.Tiltak.Tekst"),
        "virksomhets_name": _get(form, "Prefill.AnsvarligVirksomhet.Navn"),
        "endret_av": None,
        "endret": None,
    }


def metadata_columns(config: APIConfig, instance: Dict[str, Any], data_element: Dict[str, Any],
                     report_id: Optional[str]) -> Dict[str, Any]:
    party_id, instance_guid = instance["id"].split("/")
    return {
        "event_type": config.app_config.tag["tag_download"],
        "digitaliseringstiltak_report_id": report_id,
        "org_number": instance["instanceOwner"].get("organisationNumber"),
        "processed_timestamp": datetime.now(timezone.utc).isoformat(),
        "instancePartyId": party_id,
        "instanceId": instance_guid,
        "visibleAfter": instance.get("visibleAfter"),
        "instance_info_last_changed": instance.get("lastChanged"),
        "instance_info_last_changed_by": instance.get("lastChangedBy"),
        "instance_info_created": instance.get("created"),
        "data_info_last_changed": data_element.get("lastChanged"),
        "data_info_last_changed_by": data_element.get("lastChangedBy"),
        "data_info_created": data_element.get("created"),
        "data_info_dataGuid": data_element.get("id"),
    }


def format_initiell(form: Dict[str, Any]) -> Dict[str, Any]:
    initiell = form.get("Initiell") or {}
    return {
        **prefill_columns(form),
        "TiltakKortnavn": initiell.get("TiltakKortnavn"),
        "Kontaktperson_FulltNavn": _get(initiell, "Kontaktperson.FulltNavn"),
        "Kontaktperson_EPostadresse": _get(initiell, "Kontaktperson.EPostadresse"),
        "Kontaktperson_Telefonnummer": _get(initiell, "Kontaktperson.Telefonnummer"),
        "ErTiltakPaabegynt": initiell.get("ErTiltaketPaabegynt"),
        "DatoPaabegynt": initiell.get("DatoPaabegynt"),
        "DatoForventetOppstart": initiell.get("DatoForventetOppstart"),
    }


def format_oppstart(form: Dict[str, Any]) -> Dict[str, Any]:
    oppstart = form.get("Oppstart") or {}
    return {
        **prefill_columns(form),
        "ForventetSluttdato": oppstart.get("ForventetSluttdato"),
        "HarKostnadsestimat": oppstart.get("HarKostnadsestimat"),
        "Kostnadsestimat": oppstart.get("Kostnadsestimat"),
        "HarFinansiering": oppstart.get("HarFinansiering"),
        "Finansieringskilder": oppstart.get("Finansieringskilder"),
    }


def format_status(form: Dict[str, Any]) -> Dict[str, Any]:
    status = form.get("Status") or {}
    return {
        **prefill_columns(form),
        "ErArbeidAvsluttet": status.get("ErArbeidAvsluttet"),
        "TiltakStatus": status.get("TiltakStatus"),
        "ForsinkelseTiltakBeskrivelse": status.get("ForsinkelseTiltakBeskrivelse"),
        "Nettside": status.get("Nettside"),
        "HindringerBeskrivelse": status.get("HindringerBeskrivelse"),
        "DrivereBeskrivelse": status.get("DrivereBeskrivelse"),
    }


def format_slutt(form: Dict[str, Any]) -> Dict[str, Any]:
    slutt = form.get("Slutt") or {}
    return {
        **prefill_columns(form),
        "TiltakArbeidBeskrivelse": slutt.get("TiltakArbeidBeskrivelse"),
        "LaerdommerBeskrivelse": slutt.get("LaerdommerBeskrivelse"),
    }


# app_name -> (column order, form formatter)
FORMATS: Dict[str, tuple[List[str], Callable[[Dict[str, Any]], Dict[str, Any]]]] = {
    "regvil-2025-initiell": (INITIELL_COLUMNS, format_initiell),
    "regvil-2025-oppstart": (OPPSTART_COLUMNS, format_oppstart),
    "regvil-2025-status": (STATUS_COLUMNS, format_status),
    "regvil-2025-slutt": (SLUTT_COLUMNS, format_slutt),
}


def build_row(app_name: str, metadata: Dict[str, Any], form: Dict[str, Any]) -> Dict[str, Any]:
    columns, formatter = FORMATS[app_name]
    row = {**metadata, **formatter(form)}
    return {column: row.get(column) for column in columns}


# ---------------------------------------------------------------- Event log

class EventLog:
    """The Downloaded and Levert blobs the event flow writes to <ENV>/event_log/ for one app."""

    def __init__(self, container, app_name: str, config: APIConfig):
        self.container = container
        self.app_name = app_name
        self.download_prefix = f"{ENV}/event_log/{app_name}_{config.app_config.tag['tag_download']}_"
        self.levert_prefix = f"{ENV}/event_log/{app_name}_{config.app_config.tag['tag_instance']}_"
        self.downloaded = self._read_all(self.download_prefix)  # instance guid -> blob
        self.levert = self._read_all(self.levert_prefix)        # instance guid -> blob
        logging.info(f"STORAGE:{app_name}: {len(self.downloaded)} Downloaded and "
                     f"{len(self.levert)} Levert blobs in event_log")

    def _read(self, name: str) -> Optional[Dict[str, Any]]:
        try:
            return json.loads(self.container.get_blob_client(name).download_blob().readall())
        except Exception as e:
            logging.error(f"STORAGE:Error reading blob {name}: {e}")
            return None

    def _read_all(self, prefix: str) -> Dict[str, Dict[str, Any]]:
        names = [blob.name for blob in self.container.list_blobs(name_starts_with=prefix)
                 if blob.name.endswith(".json")]
        with ThreadPoolExecutor(BLOB_READ_WORKERS) as pool:
            blobs = pool.map(self._read, names)
        return {name[len(prefix):-len(".json")]: blob for name, blob in zip(names, blobs) if blob is not None}

    def report_id_from_levert(self, instance_guid: str) -> Optional[str]:
        return (self.levert.get(instance_guid) or {}).get("digitaliseringstiltak_report_id")


def row_from_event_log(app_name: str, blob: Dict[str, Any]) -> Dict[str, Any]:
    metadata = {key.replace(".", "_"): value for key, value in blob.items() if key != "data"}
    row = build_row(app_name, metadata, blob.get("data") or {})
    # the event flow takes the name from the party register, not from the form
    row["virksomhets_name"] = blob.get("virksomhets_name")
    return row


def _normalise(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip().casefold()


def compare_rows(storage_row: Dict[str, Any], logged_row: Dict[str, Any]) -> List[str]:
    differences = []
    for column, value in storage_row.items():
        if column in NOT_COMPARED:
            continue
        if _normalise(value) != _normalise(logged_row.get(column)):
            differences.append(f"{column}: storage={value!r} event_log={logged_row.get(column)!r}")
    return differences


# ---------------------------------------------------------------- Chain check

def expected_next_app(config: APIConfig, app_name: str, data: Dict[str, Any]) -> Optional[str]:
    """Same decision as get_initiell_skjema.run: which skjema follows the downloaded one."""
    if app_name == "regvil-2025-status" and _get(data, "Status.ErArbeidAvsluttet") is False:
        return app_name
    if app_name == "regvil-2025-oppstart" and not _get(data, "Initiell.ErTiltaketPaabegynt"):
        return app_name
    next_app = config.workflow_dag.get_next(app_name)
    return None if next_app in (None, "END") else next_app


def _timestamp(blob: Dict[str, Any]) -> Optional[datetime]:
    value = blob.get("processed_timestamp")
    try:
        return to_utc_aware(value) if value else None
    except ValueError:
        return None


def _day(value: Optional[str]) -> Optional[str]:
    return value.split("T")[0] if value else None


def check_chain(app_names: List[str], configs: Dict[str, APIConfig], event_logs: Dict[str, "EventLog"],
                storage_ended: Dict[str, Dict[str, Optional[str]]]) -> List[Dict[str, Any]]:
    """Pair every Downloaded blob with the Levert blob of the next skjema (same report id,
    written after the download). Each Levert blob is used for at most one download."""
    levert_by_key: Dict[tuple, List[tuple]] = {}
    for app_name, event_log in event_logs.items():
        for guid, blob in event_log.levert.items():
            key = (app_name, blob.get("digitaliseringstiltak_report_id"))
            levert_by_key.setdefault(key, []).append((_timestamp(blob), guid, blob))
    for candidates in levert_by_key.values():
        candidates.sort(key=lambda item: item[0] or datetime.min.replace(tzinfo=timezone.utc))
    used: set = set()

    downloads = []
    for app_name in app_names:
        for guid, blob in event_logs[app_name].downloaded.items():
            downloads.append((_timestamp(blob), app_name, guid, blob))
    downloads.sort(key=lambda item: item[0] or datetime.min.replace(tzinfo=timezone.utc))

    results = []
    for downloaded_at, app_name, guid, blob in downloads:
        report_id = blob.get("digitaliseringstiltak_report_id")
        if is_test_report(report_id):
            continue
        next_app = expected_next_app(configs[app_name], app_name, blob.get("data") or {})
        completed_at = storage_ended.get(app_name, {}).get(guid)
        result = {
            "date": _day(completed_at or blob.get("processed_timestamp")),
            "app_name": app_name,
            "instanceId": guid,
            "instancePartyId": blob.get("instancePartyId"),
            "org_number": blob.get("org_number"),
            "virksomhets_name": blob.get("virksomhets_name"),
            "digitaliseringstiltak_report_id": report_id,
            "completed_at": completed_at,
            "downloaded_at": blob.get("processed_timestamp"),
            "expected_next_app": next_app,
            "next_instanceId": None,
            "next_levert_at": None,
            "next_instance_in_storage": None,
            "status": "ok",
        }
        if next_app is None:
            result["status"] = "end_of_workflow"
        elif not report_id:
            result["status"] = "download_without_report_id"
        else:
            match = None
            for levert_at, next_guid, levert_blob in levert_by_key.get((next_app, report_id), []):
                if (app_name, next_app, next_guid) in used or next_guid == guid:
                    continue
                if downloaded_at and levert_at and levert_at < downloaded_at - CHAIN_TOLERANCE:
                    continue
                match = (levert_at, next_guid, levert_blob)
                break
            if match:
                used.add((app_name, next_app, match[1]))
                result["next_instanceId"] = match[1]
                result["next_levert_at"] = match[2].get("processed_timestamp")
                if next_app in storage_ended:
                    result["next_instance_in_storage"] = match[1] in storage_ended[next_app]
            else:
                result["status"] = "missing_next_instance"
        results.append(result)
    return results


# ---------------------------------------------------------------- Run

def is_completed(instance: Dict[str, Any]) -> bool:
    return bool((instance.get("process") or {}).get("ended"))


def export_app(app_name: str, config: APIConfig, event_log: Optional[EventLog],
               include_open: bool) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Optional[str]]]:
    reader = StorageReader(config)
    rows: List[Dict[str, Any]] = []
    reconciliation: List[Dict[str, Any]] = []
    storage_ended: Dict[str, Optional[str]] = {}  # instance guid -> process ended (completed) timestamp

    for instance in reader.fetch_all_instances():
        party_id, instance_guid = instance["id"].split("/")
        process_ended = (instance.get("process") or {}).get("ended")
        storage_ended[instance_guid] = process_ended
        completed = is_completed(instance)
        status = instance.get("status") or {}
        if status.get("isHardDeleted") or (not completed and not include_open):
            continue
        if not instance.get("data"):
            logging.warning(f"STORAGE:{app_name}: instance {instance['id']} has no data elements")
            continue

        data_element = get_meta_data_info(instance["data"])
        tags = data_element.get("tags") or []
        report_id = tags[0] if tags else (event_log.report_id_from_levert(instance_guid) if event_log else None)
        if is_test_report(report_id):
            continue

        form = reader.fetch_form(instance, data_element)
        if form is None:
            continue

        row = build_row(app_name, metadata_columns(config, instance, data_element, report_id), form)
        rows.append(row)

        if not event_log:
            continue
        downloaded_blob = event_log.downloaded.get(instance_guid)
        differences = compare_rows(row, row_from_event_log(app_name, downloaded_blob)) if downloaded_blob else []
        reconciliation.append({
            "date": _day(process_ended or data_element.get("lastChanged")),
            "app_name": app_name,
            "instancePartyId": party_id,
            "instanceId": instance_guid,
            "org_number": row.get("org_number"),
            "virksomhets_name": row.get("virksomhets_name"),
            "digitaliseringstiltak_report_id": report_id,
            "completed": completed,
            "completed_at": process_ended,
            "downloaded_at": downloaded_blob.get("processed_timestamp") if downloaded_blob else None,
            "isSoftDeleted": status.get("isSoftDeleted"),
            "has_levert_blob": instance_guid in event_log.levert,
            # get_initiell_skjema skips instances the user never changed (createdBy == lastChangedBy)
            "changed_by_user": data_element.get("createdBy") != data_element.get("lastChangedBy"),
            # the event flow only downloads completed instances
            "missing_downloaded_blob": completed and downloaded_blob is None,
            "differences": " | ".join(differences),
        })

    return rows, reconciliation, storage_ended


def problems_by_date(reconciliation: List[Dict[str, Any]], chain: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Problem counts per day and app, so a period where the event flow failed stands out."""
    counts: Dict[tuple, int] = {}
    for r in reconciliation:
        if r["missing_downloaded_blob"]:
            key = (r["date"], r["app_name"], "missing_downloaded_blob")
            counts[key] = counts.get(key, 0) + 1
    for r in chain:
        if r["status"] in ("missing_next_instance", "download_without_report_id"):
            key = (r["date"], r["app_name"], r["status"])
            counts[key] = counts.get(key, 0) + 1
    return [{"date": date, "app_name": app_name, "problem": problem, "count": count}
            for (date, app_name, problem), count in sorted(counts.items(), key=lambda item: (item[0][0] or "", item[0][1:]))]


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    columns: List[str] = []
    for row in rows:
        columns.extend(column for column in row if column not in columns)
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export RegVil instances from Altinn Storage.")
    parser.add_argument("--app", choices=APPS, help="Only export this app (default: all)")
    parser.add_argument("--include-open", action="store_true",
                        help="Also export instances that are not submitted yet")
    args = parser.parse_args()
    app_names = [args.app] if args.app else APPS

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    configs = {app_name: load_full_config(PATH_TO_CONFIG_FOLDER, app_name, ENV) for app_name in APPS}
    container = connect_blob()
    if not container:
        logging.warning("STORAGE:No blob connection - the event_log checks are skipped")
    # the chain check needs the Levert blobs of every app, also when only one app is exported
    event_logs = {app_name: EventLog(container, app_name, configs[app_name]) for app_name in APPS} if container else {}

    all_reconciliation: List[Dict[str, Any]] = []
    storage_ended: Dict[str, Dict[str, Optional[str]]] = {}
    for app_name in app_names:
        rows, reconciliation, storage_ended[app_name] = export_app(
            app_name, configs[app_name], event_logs.get(app_name), args.include_open)
        all_reconciliation.extend(reconciliation)

        with open(OUTPUT_DIR / f"{app_name}.json", "w", encoding="utf-8") as file:
            json.dump(rows, file, ensure_ascii=False, indent=4)
        if rows:
            write_csv(OUTPUT_DIR / f"{app_name}.csv", rows)

        missing = sum(1 for r in reconciliation if r["missing_downloaded_blob"])
        differing = sum(1 for r in reconciliation if r["differences"])
        print(f"{app_name}: {len(rows)} rows exported, {missing} completed instances without "
              f"Downloaded blob, {differing} with differences to the event_log")

    by_date = lambda r: r["date"] or ""
    if all_reconciliation:
        write_csv(OUTPUT_DIR / "reconciliation.csv", sorted(all_reconciliation, key=by_date))

    if event_logs:
        chain = sorted(check_chain(app_names, configs, event_logs, storage_ended), key=by_date)
        if chain:
            write_csv(OUTPUT_DIR / "chain.csv", chain)
        for app_name in app_names:
            app_chain = [r for r in chain if r["app_name"] == app_name]
            missing = sum(1 for r in app_chain if r["status"] == "missing_next_instance")
            print(f"{app_name}: {len(app_chain)} Downloaded blobs, {missing} without a following Levert blob")

        problems = problems_by_date(all_reconciliation, chain)
        if problems:
            write_csv(OUTPUT_DIR / "problems_by_date.csv", problems)
            print("\nProblems per day:")
            for p in problems:
                print(f"  {p['date']}  {p['app_name']:<22} {p['problem']:<28} {p['count']}")

    print(f"Output written to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
