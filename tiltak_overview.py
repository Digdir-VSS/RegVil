"""Overview of every digitaliseringstiltak through the RegVil process.

Not wired into app.py - run by hand (ENV is taken from .env):

    python tiltak_overview.py

Every tiltak (1-123, deltiltak like 11a, 11b, ...) is followed by its report id through
initiell -> oppstart (again while not started) -> status (every April and October, until
finished) -> slutt. All instances in Storage, open and completed, are included; answers
are taken from the Downloaded blobs the event flow wrote, so forms are only downloaded
from Storage for tiltak the event flow has never logged.

Output in storage_export/<ENV>/:
  tiltak_timeline.csv  one row per instance, per tiltak in time order
  tiltak_overview.csv  one row per tiltak: where it is now, what comes next, and issues:
      missing_next:<step>        last completed form was not followed by the next one
      missing_status_round:<r>   a status round between the first one and now has no form
      several_open               more than one open form at the same time
      empty_instance             a form without data (failed instantiation)
      no_instances               the tiltak number has no forms at all
"""
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config.config_loader import load_full_config
from config.utils import connect_blob
from get_data_from_storage import (
    APPS,
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
from get_open_instances import _data_element, _parse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

TILTAK_NUMBERS = range(1, 124)
STEP = {app_name: app_name.replace("regvil-2025-", "") for app_name in APPS}
STATE_RANK = {"completed": 0, "open": 1, "empty": 2}


def tiltak_sort_key(number: Optional[str]) -> tuple:
    match = re.fullmatch(r"(\d+)(.*)", str(number or "").strip())
    return (int(match.group(1)), match.group(2)) if match else (10_000, str(number))


def round_label(moment: Optional[datetime]) -> Optional[str]:
    """Status is sent every April and October: first half of the year is the April round."""
    if not moment:
        return None
    return f"{moment.year}-04" if moment.month <= 6 else f"{moment.year}-10"


def rounds_between(first: str, last: str) -> List[str]:
    rounds, current = [], first
    while current <= last:
        rounds.append(current)
        year, month = current.split("-")
        current = f"{year}-10" if month == "04" else f"{int(year) + 1}-04"
    return rounds


def answer_summary(app_name: str, data: Dict[str, Any]) -> Optional[str]:
    if not data:
        return None
    step = STEP[app_name]
    if step in ("initiell", "oppstart"):
        if _get(data, "Initiell.ErTiltaketPaabegynt"):
            started = f"påbegynt {_get(data, 'Initiell.DatoPaabegynt') or ''}".strip()
            if step == "oppstart":
                started += f", forventet slutt {_get(data, 'Oppstart.ForventetSluttdato') or '?'}"
            return started
        return f"ikke påbegynt, forventet oppstart {_get(data, 'Initiell.DatoForventetOppstart') or '?'}"
    if step == "status":
        if _get(data, "Status.ErArbeidAvsluttet"):
            return "avsluttet"
        return f"pågår ({_get(data, 'Status.TiltakStatus') or '?'})"
    return f"avsluttet {_get(data, 'Slutt.DatoAvsluttet') or ''}".strip()


def main() -> None:
    now = datetime.now(timezone.utc)
    configs = {app_name: load_full_config(PATH_TO_CONFIG_FOLDER, app_name, ENV) for app_name in APPS}
    readers = {app_name: StorageReader(configs[app_name]) for app_name in APPS}
    container = connect_blob()
    if not container:
        raise RuntimeError("OVERVIEW:No blob connection - needed for the event_log")
    event_logs = {app_name: EventLog(container, app_name, configs[app_name]) for app_name in APPS}

    # ------------------------------------------------ every instance, with its report id
    instances: List[Dict[str, Any]] = []
    for app_name in APPS:
        for instance in readers[app_name].fetch_all_instances():
            status = instance.get("status") or {}
            if status.get("isHardDeleted"):
                continue
            party_id, guid = instance["id"].split("/")
            data_element = _data_element(instance)
            tags = (data_element or {}).get("tags") or []
            downloaded = event_logs[app_name].downloaded.get(guid)
            levert = event_logs[app_name].levert.get(guid)
            report_id = (tags[0] if tags else None) \
                or (downloaded or {}).get("digitaliseringstiltak_report_id") \
                or (levert or {}).get("digitaliseringstiltak_report_id")
            if not data_element:
                state = "empty"
            elif status.get("isSoftDeleted"):
                state = "soft_deleted"
            else:
                state = "completed" if is_completed(instance) else "open"
            instances.append({
                "app_name": app_name,
                "instance": instance,
                "data_element": data_element,
                "party_id": party_id,
                "guid": guid,
                "report_id": report_id,
                "org_number": instance["instanceOwner"].get("organisationNumber"),
                "created": _parse(instance.get("created") or (data_element or {}).get("created")),
                "visible_after": _parse(instance.get("visibleAfter")),
                "completed_at": (instance.get("process") or {}).get("ended"),
                "state": state,
                # answers of completed forms, as downloaded by the event flow
                "answers": (downloaded or {}).get("data") or {},
                "prefill": ((downloaded or levert or {}).get("data") or {}).get("Prefill"),
            })

    # ------------------------------------------------ tiltak info (Prefill) per report id
    prefill: Dict[str, Dict[str, Any]] = {}
    for item in instances:
        if item["report_id"] and item["prefill"] and item["report_id"] not in prefill:
            prefill[item["report_id"]] = item["prefill"]
    for item in instances:
        report_id = item["report_id"]
        if report_id and report_id not in prefill and item["data_element"]:
            form = readers[item["app_name"]].fetch_form(item["instance"], item["data_element"]) or {}
            if form.get("Prefill"):
                prefill[report_id] = form["Prefill"]

    by_report: Dict[Optional[str], List[Dict[str, Any]]] = {}
    for item in instances:
        by_report.setdefault(item["report_id"], []).append(item)
    for items in by_report.values():
        items.sort(key=lambda i: i["created"] or i["visible_after"] or now)

    # ------------------------------------------------ timeline
    timeline: List[Dict[str, Any]] = []
    overview: List[Dict[str, Any]] = []
    current_round = round_label(now)

    for report_id, items in by_report.items():
        if is_test_report(report_id):
            continue
        info = prefill.get(report_id) or {}
        tiltak = {
            "digitaliseringstiltak": _get(info, "Tiltak.Nummer"),
            "digitaliseringstiltak_report_id": report_id,
            "tiltak_navn": _get(info, "Tiltak.Tekst"),
            "virksomhets_name": _get(info, "AnsvarligVirksomhet.Navn"),
            "org_number": items[0]["org_number"],
        }
        for item in items:
            timeline.append({
                **tiltak,
                "step": STEP[item["app_name"]],
                "round": round_label(item["visible_after"] or item["created"]) if STEP[item["app_name"]] == "status" else None,
                "instancePartyId": item["party_id"],
                "instanceId": item["guid"],
                "created": item["created"].isoformat() if item["created"] else None,
                "visibleAfter": item["instance"].get("visibleAfter"),
                "completed_at": item["completed_at"],
                "state": item["state"],
                "answer": answer_summary(item["app_name"], item["answers"]) if item["state"] == "completed" else None,
            })

        # ------------------------------------------------ overview row
        real = [i for i in items if i["state"] in ("open", "completed")]
        issues = []
        if any(i["state"] == "empty" for i in items):
            issues.append("empty_instance")
        open_items = [i for i in real if i["state"] == "open"]
        if len(open_items) > 1:
            issues.append("several_open")

        def steps(app_name: str) -> List[Dict[str, Any]]:
            return [i for i in real if i["app_name"] == app_name]

        status_rounds: Dict[str, str] = {}
        for item in steps("regvil-2025-status"):
            label = round_label(item["visible_after"] or item["created"])
            if label not in status_rounds or STATE_RANK[item["state"]] < STATE_RANK[status_rounds[label]]:
                status_rounds[label] = item["state"]

        completed = [i for i in real if i["state"] == "completed"]
        last_completed = max(completed, key=lambda i: i["completed_at"] or "") if completed else None
        next_expected = None
        if last_completed:
            next_app = expected_next_app(configs[last_completed["app_name"]], last_completed["app_name"],
                                         last_completed["answers"])
            if next_app:
                next_expected = STEP[next_app]
                ended = _parse(last_completed["completed_at"])
                followed = any(i["app_name"] == next_app and i is not last_completed
                               and (not ended or not i["created"] or i["created"] >= ended) for i in real)
                if not followed and last_completed["answers"]:
                    issues.append(f"missing_next:{next_expected}")
            else:
                next_expected = "ferdig"

        finished = any(i["state"] == "completed" for i in steps("regvil-2025-slutt")) or \
            any(_get(i["answers"], "Status.ErArbeidAvsluttet") for i in steps("regvil-2025-status"))
        if status_rounds and not finished:
            for label in rounds_between(min(status_rounds), current_round):
                if label not in status_rounds:
                    issues.append(f"missing_status_round:{label}")

        latest = items[-1]
        waiting = open_items[-1] if open_items else None
        initiell = steps("regvil-2025-initiell")
        oppstart = steps("regvil-2025-oppstart")
        slutt = steps("regvil-2025-slutt")
        overview.append({
            **tiltak,
            "initiell": (initiell[-1]["completed_at"] or initiell[-1]["state"]) if initiell else None,
            "oppstart": f"{len(oppstart)} form(s), last {oppstart[-1]['state']}" if oppstart else None,
            "status_rounds": ", ".join(f"{label}: {state}" for label, state in sorted(status_rounds.items())),
            "slutt": (slutt[-1]["completed_at"] or slutt[-1]["state"]) if slutt else None,
            "current_step": STEP[latest["app_name"]],
            "current_state": latest["state"],
            "last_answer": answer_summary(last_completed["app_name"], last_completed["answers"]) if last_completed else None,
            "waiting_for": STEP[waiting["app_name"]] if waiting else None,
            "waiting_visible_after": waiting["instance"].get("visibleAfter") if waiting else None,
            "next_expected": next_expected,
            "last_activity": max((i["completed_at"] or (i["created"].isoformat() if i["created"] else "")) for i in items),
            "issues": "; ".join(issues),
        })

    # ------------------------------------------------ tiltak numbers without any forms
    covered = {tiltak_sort_key(row["digitaliseringstiltak"])[0] for row in overview}
    for number in TILTAK_NUMBERS:
        if number not in covered:
            overview.append({"digitaliseringstiltak": str(number), "issues": "no_instances"})

    timeline.sort(key=lambda r: (tiltak_sort_key(r["digitaliseringstiltak"]), r["digitaliseringstiltak_report_id"] or "",
                                 r["created"] or ""))
    overview.sort(key=lambda r: (tiltak_sort_key(r["digitaliseringstiltak"]), r.get("digitaliseringstiltak_report_id") or ""))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(OUTPUT_DIR / "tiltak_timeline.csv", timeline)
    write_csv(OUTPUT_DIR / "tiltak_overview.csv", overview)

    tracked = [r for r in overview if r.get("digitaliseringstiltak_report_id")]
    print(f"{len(tracked)} tiltak tracked, {len(timeline)} forms")
    for step in ("initiell", "oppstart", "status", "slutt"):
        print(f"  currently at {step:<9} {sum(1 for r in tracked if r.get('current_step') == step)}")
    issue_counts: Dict[str, int] = {}
    for row in overview:
        for issue in filter(None, (row.get("issues") or "").split("; ")):
            kind = issue.split(":")[0]
            issue_counts[kind] = issue_counts.get(kind, 0) + 1
    for kind, count in sorted(issue_counts.items()):
        print(f"  {kind:<22} {count}")
    print(f"Output written to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
