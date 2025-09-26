import re

from typing import Any, Dict, Optional, Tuple
import logging
import pytz
from azure.storage.blob import BlobServiceClient
from azure.identity import DefaultAzureCredential, EnvironmentCredential
from dotenv import load_dotenv
import os
import json
from datetime import datetime, date
import isodate
from .type_dict_structure import DataModel, Prefill
from datetime import datetime, timezone, timedelta


class PrefillValidationError(Exception):
    pass


def get_required_key(record, key):
    if key not in record:
        raise KeyError(f"Missing required key: {key}")
    return record[key]


def transform_initiell_data_to_nested_with_prefill(flat_record) -> Prefill:
    return {
        "Prefill": {
            "AnsvarligDepartement": {
                "Navn": get_required_key(flat_record, "AnsvarligDepartement.Navn"),
                "Organisasjonsnummer": get_required_key(
                    flat_record, "AnsvarligDepartement.Organisasjonsnummer"
                ),
            },
            "AnsvarligVirksomhet": {
                "Navn": get_required_key(flat_record, "AnsvarligVirksomhet.Navn"),
                "Organisasjonsnummer": get_required_key(
                    flat_record, "AnsvarligVirksomhet.Organisasjonsnummer"
                ),
            },
            "Kontaktperson": {
                "FulltNavn": get_required_key(flat_record, "Kontaktperson.FulltNavn"),
                "Telefonnummer": get_required_key(
                    flat_record, "Kontaktperson.Telefonnummer"
                ),
                "EPostadresse": get_required_key(
                    flat_record, "Kontaktperson.EPostadresse"
                ),
            },
            "Tiltak": {
                "Nummer": get_required_key(flat_record, "Tiltak.Nummer"),
                "Tekst": get_required_key(flat_record, "Tiltak.Tekst"),
                "ErDeltiltak": get_required_key(flat_record, "Tiltak.ErDeltiltak"),
            },
            "Kapittel": {
                "Nummer": get_required_key(flat_record, "Kapittel.Nummer"),
                "Tekst": get_required_key(flat_record, "Kapittel.Tekst"),
            },
            "Maal": {
                "Nummer": get_required_key(flat_record, "Maal.Nummer"),
                "Tekst": get_required_key(flat_record, "Maal.Tekst"),
            },
            "Godkjenning": {
                "SkalGodkjennes": get_required_key(
                    flat_record, "Godkjenning.SkalGodkjennes"
                ),
                "Godkjenner": {
                    "FulltNavn": get_required_key(flat_record, "Godkjenning.FulltNavn"),
                    "Telefonnummer": get_required_key(
                        flat_record, "Godkjenning.Telefonnummer"
                    ),
                    "EPostadresse": get_required_key(
                        flat_record, "Godkjenning.EPostadresse"
                    ),
                },
            },
        }
    }


def validate_initiell_prefill_data(prefill_data_row: Dict[str, Any]) -> bool:

    # 1. Check if all fields are present and not empty
    all_fields = [
        "AnsvarligDepartement.Navn",
        "AnsvarligDepartement.Organisasjonsnummer",
        "AnsvarligVirksomhet.Navn",
        "AnsvarligVirksomhet.Organisasjonsnummer",
        "Kontaktperson.FulltNavn",
        "Kontaktperson.Telefonnummer",
        "Kontaktperson.EPostadresse",
        "Tiltak.Nummer",
        "Tiltak.Tekst",
        "Tiltak.ErDeltiltak",
        "Kapittel.Nummer",
        "Kapittel.Tekst",
        "Maal.Nummer",
        "Maal.Tekst",
        "digitaliseringstiltak_report_id",
    ]

    # Check if

    # Check all fields are present and not empty
    for field in all_fields:
        if field not in prefill_data_row:
            raise PrefillValidationError(f"Missing field: {field}")
        value = prefill_data_row[field]

        # Special handling for boolean field
        if field == "Tiltak.ErDeltiltak":
            if value is None:
                raise PrefillValidationError(f"Field {field} cannot be None")
            continue

        # For all other fields, check not empty
        if value is None or (isinstance(value, str) and not value.strip()):
            raise PrefillValidationError(f"Field {field} cannot be None")

    # 2. Validate Organisasjonsnummer (Norwegian org number - 9 digits)
    org_numbers = [
        "AnsvarligDepartement.Organisasjonsnummer",
        "AnsvarligVirksomhet.Organisasjonsnummer",
    ]

    for field in org_numbers:
        org_number = str(prefill_data_row[field])
        if not _is_valid_org_number(org_number):
            raise PrefillValidationError(
                f"Invalid organisation number format in {field}: {org_number} (must be 9 digits)"
            )
    # 4. Validate email
    email = prefill_data_row["Kontaktperson.EPostadresse"]
    if not _is_valid_email(str(email)):
        raise PrefillValidationError(f"Invalid email format: {email}")

    # 5. Validate phone number
    phone = prefill_data_row["Kontaktperson.Telefonnummer"]
    if not _is_valid_phone(str(phone)):
        raise PrefillValidationError(f"Invalid phone number format: {phone}")

    # 6. Validate string fields that should be numbers as strings
    number_string_fields = ["Tiltak.Nummer", "Kapittel.Nummer", "Maal.Nummer"]

    for field in number_string_fields:
        value = prefill_data_row[field]
        if not isinstance(value, str):
            raise PrefillValidationError(
                f"Field {field} must be string, got {type(value)}"
            )

        # Check if it contains at least some numeric content (allow formats like "2.1.4")
        if not re.search(r"\d", value):
            raise PrefillValidationError(f"Field {field} must contain numbers: {value}")

    # 7. Validate boolean field
    tiltak_er_deltiltak = prefill_data_row["Tiltak.ErDeltiltak"]
    if not isinstance(tiltak_er_deltiltak, bool):
        raise PrefillValidationError(
            f"Field Tiltak.ErDeltiltak must be boolean, got {type(tiltak_er_deltiltak)}"
        )
    return True


def _is_valid_org_number(org_number):
    """
    Validates a Norwegian organization number using modulus 11 algorithm.

    Args:
        org_number (str): The organization number to validate

    Returns:
        bool: True if valid, False otherwise
    """
    # Remove any spaces or formatting
    org_number = org_number.replace(" ", "").replace("-", "")
    # Check if it's exactly 9 digits
    if len(org_number) != 9 or not org_number.isdigit():
        return False
    # Convert to list of integers
    digits = [int(d) for d in org_number]
    # Weights for the first 8 digits (from left to right)
    weights = [3, 2, 7, 6, 5, 4, 3, 2]
    # Calculate sum of products
    product_sum = sum(digit * weight for digit, weight in zip(digits[:8], weights))
    remainder = product_sum % 11
    if remainder == 0:
        control_digit = 0
    elif remainder == 1:
        return False
    else:
        control_digit = 11 - remainder
    return control_digit == digits[8]


def _is_valid_uuid(uuid_string: str) -> bool:
    """Validate UUID format"""
    if not isinstance(uuid_string, str):
        return False
    uuid_pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    return re.match(uuid_pattern, uuid_string.lower()) is not None


def _is_valid_email(email: str) -> bool:
    """Validate email format"""
    if not isinstance(email, str):
        return False
    email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(email_pattern, email) is not None


def _is_valid_phone(phone: str) -> bool:
    """Validate Norwegian phone number format"""
    if not isinstance(phone, str):
        return False
    # Remove spaces and common separators
    cleaned = re.sub(r"[\s\-\(\)]", "", phone)
    # Norwegian format: +47 followed by 8 digits, or just 8 digits
    return re.match(r"^(\+47)?[0-9]{8}$", cleaned) is not None


def connect_blob():
    try:
        load_dotenv()

        if os.getenv("AZURE_CLIENT_ID"):
            # print("Using EnvironmentCredential for local dev")
            credential = EnvironmentCredential()
        else:
            # print("Using DefaultAzureCredential (includes managed identity in Azure)")
            credential = DefaultAzureCredential()

        blob_service_client = BlobServiceClient(
            os.getenv("BLOB_STORAGE_ACCOUNT_URL"), credential=credential
        )
        container_client = blob_service_client.get_container_client(
            os.getenv("BLOB_CONTAINER_NAME")
        )

        return container_client

    except Exception as e:
        logging.error(f"Error connecting to Azure Blob Storage: {e}")
        return None


def chech_file_exists(file: str) -> bool:
    container_client = connect_blob()
    if not container_client:
        return False
    try:
        blob_client = container_client.get_blob_client(file)
        return blob_client.exists()
    except Exception as e:
        logging.error(f"Error checking existence of blob {file}: {e}")
        return False


def read_blob(file):
    container_client = connect_blob()
    if not container_client:
        return None
    try:
        blob_client = container_client.get_blob_client(file)
        blob_data = blob_client.download_blob().readall()
        return json.loads(blob_data)
    except Exception as e:
        logging.error(f"Error reading blob {file}: {e}")
        return None


def write_blob(file: str, data: Dict[str, str]) -> bool:
    container_client = connect_blob()
    if not container_client:
        return False
    try:
        blob_client = container_client.get_blob_client(file)
        blob_client.upload_blob(json.dumps(data), overwrite=True)
        return True
    except Exception as e:
        logging.error(f"Error writing blob {file}: {e}")
        return False


def blob_directory_exists(directory: str) -> bool:
    container_client = connect_blob()
    if not container_client:
        return False
    if not directory.endswith("/"):
        directory += "/"
    try:
        blobs = container_client.list_blobs(name_starts_with=directory)
        return any(blob.name.startswith(directory) for blob in blobs)
    except Exception as e:
        logging.error(f"Error checking existence of directory {directory}: {e}")
        return False


def list_blobs_with_prefix(prefix: str) -> list[str]:
    container_client = connect_blob()
    if not container_client:
        return []
    try:
        blob_list = container_client.list_blobs(name_starts_with=prefix)
        return [blob.name for blob in blob_list]
    except Exception as e:
        logging.error(f"Error listing blobs with prefix {prefix}: {e}")
        return []


def to_utc_aware(dt_str: str) -> datetime:
    # Accepts ISO 8601 strings like '2025-07-30T08:00:00Z' or '2024-01-31'
    try:
        if dt_str.endswith("Z"):
            dt_str = dt_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(dt_str)
    except ValueError:
        raise ValueError(f"Invalid datetime format: {dt_str}")

    if dt.tzinfo is None:
        return pytz.UTC.localize(dt)
    return dt.astimezone(pytz.UTC)


def get_today_date() -> str:
    return (
        datetime.now(pytz.UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )


def check_date_before(reference_date: str, compare_date: str):
    if not reference_date:
        raise ValueError("Reference date string is empty")
    if not compare_date:
        raise ValueError("Comapre date string is empty")
    ref = to_utc_aware(reference_date)
    comp = to_utc_aware(compare_date)
    return ref < comp


def add_time_delta(base_date_str: str, time_delta_str: str):
    if not time_delta_str:
        raise ValueError("Timedelta string is empty")
    base_date = to_utc_aware(base_date_str)
    time_delta = isodate.parse_duration(time_delta_str)
    result = base_date + time_delta
    return result.isoformat().replace("+00:00", "Z")

def next_deadline(d: date) -> date:
        """Find the closest coming 1st Feb or 1st Sep after or equal to given date."""
        year = d.year
        feb = date(year, 1, 17)
        sep = date(year, 8, 17)

        if d < feb:
            return feb
        elif d < sep:
            return sep
        else:
            return date(year + 1, 1, 17)
        
def next_eval_date(date_str: str, status: dict | None) -> date:
    given_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    cutoff_date = date(2025, 12, 1)

    # def next_deadline(d: date) -> date:
    #     """Find the closest coming 1st Feb or 1st Sep after or equal to given date."""
    #     year = d.year
    #     feb = date(year, 1, 17)
    #     sep = date(year, 8, 17)

    #     if d < feb:
    #         return feb
    #     elif d < sep:
    #         return sep
    #     else:
    #         return date(year + 1, 1, 17)

    # Case 1: status is None and before cutoff
    if status is None and given_date < cutoff_date:
        return given_date

    # Case 2: status is None and after/equal cutoff → next deadline
    if status is None:
        return next_deadline(given_date)

    # Case 3: status is not None
    nd = next_deadline(date.today())
    if given_date < nd:
        return given_date
    else:
        return nd
    
def get_initiell_date(reported_data: DataModel, time_delta: str) -> Optional[str]:
    initiell = reported_data.get("Initiell")
    if initiell.get("ErTiltaketPaabegynt"):
        if check_date_before(initiell.get("DatoPaabegynt"), get_today_date()):
            return add_time_delta(get_today_date(), time_delta)
        return initiell.get("DatoPaabegynt")
    else:
        return initiell.get("DatoForventetOppstart")


def get_oppstart_date(reported_data: DataModel, time_delta: str) -> str:
    oppstart = reported_data.get("Oppstart")
    initiell = reported_data.get("Initiell")
    if not initiell.get("ErTiltaketPaabegynt") and not check_date_before(initiell.get("DatoForventetOppstart"), get_today_date()):
        return initiell.get("DatoForventetOppstart")
            
    else:
        status = reported_data.get("Status")
        next_date = next_eval_date(initiell.get("DatoPaabegynt"), status)
        return next_date.strftime("%Y-%m-%d")
        # result_date = add_time_delta(oppstart.get("ForventetSluttdato"), time_delta)
        # if check_date_before(result_date, get_today_date()):
        #     return get_today_date()
        # return result_date


def get_status_date(
    reported_data: DataModel, time_delta: Optional[str]
) -> Optional[str]:
    oppstart = reported_data.get("Oppstart")
    status = reported_data.get("Status")

    if status.get("ErArbeidAvsluttet"):
        return get_today_date()
    else:
        if oppstart.get("ForventetSluttdato") is None:
            next_date = next_deadline(date.today())
        else:
            next_date = next_eval_date(oppstart.get("ForventetSluttdato"),status)
        
        return next_date.strftime("%Y-%m-%d")


def get_slutt_date(
    reported_data: DataModel, time_delta: Optional[str]
) -> Optional[str]:
    return None


def create_payload(
    org_number: str, dato: str, api_config, prefill_data: DataModel
) -> Dict[str, Tuple[str, str, str]]:
    instance_data = {
        "appId": f"digdir/{api_config.app_config.app_name}",
        "instanceOwner": {
            "personNumber": None,
            "organisationNumber": org_number,
        },
        "dueBefore": None,
        "visibleAfter": dato,
    }
    files = {
        "instance": (
            "instance.json",
            json.dumps(instance_data, ensure_ascii=False),
            "application/json",
        ),
        "DataModel": (
            "datamodel.json",
            json.dumps(prefill_data, ensure_ascii=False),
            "application/json",
        ),
    }
    return files


def split_party_instance_id(party_instance_id: str) -> Tuple[str]:
    party_id, instance_id = party_instance_id.split("/")
    return party_id, instance_id


def is_before_time_delta(date: str, time_delta: Optional[int]=None) -> bool:
    if time_delta is None:
        time_delta = 0
    naive_dt = datetime.strptime(date, "%Y-%m-%d")
    formated_date = naive_dt.replace(tzinfo=timezone.utc)
    return formated_date < datetime.now(pytz.UTC) - timedelta(days=time_delta)

def parse_date(date_str: str) -> datetime:
    # Case 1: full ISO with Z (UTC)
    if "T" in date_str and date_str.endswith("Z"):
        return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    
    # Case 2: plain date (no time info) → assume midnight UTC
    elif len(date_str) == 10:
        return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    
    # Fallback: try more general parsing
    else:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))