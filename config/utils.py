import re
from typing import Any, Dict, Optional
from datetime import datetime, timezone
import logging
import isodate

from .type_dict_structure import DataModel

class PrefillValidationError(Exception):
    pass

def get_required_key(record, key):
    if key not in record:
        raise KeyError(f"Missing required key: {key}")
    return record[key]

def transform_initiell_data_to_nested_with_prefill(flat_record):
    return {
        "Prefill": {
            "AnsvarligDepartement": {
                "Navn": get_required_key(flat_record,"AnsvarligDepartement.Navn"),
                "Organisasjonsnummer":  get_required_key(flat_record,"AnsvarligDepartement.Organisasjonsnummer")
            },
            "AnsvarligVirksomhet": {
                "Navn":  get_required_key(flat_record,"AnsvarligVirksomhet.Navn"),
                "Organisasjonsnummer":  get_required_key(flat_record,"AnsvarligVirksomhet.Organisasjonsnummer")
            },
            "Kontaktperson": {
                "FulltNavn":  get_required_key(flat_record,"Kontaktperson.FulltNavn"),
                "Telefonnummer":  get_required_key(flat_record,"Kontaktperson.Telefonnummer"),
                "EPostadresse":  get_required_key(flat_record,"Kontaktperson.EPostadresse")
            },
            "Tiltak": {
                "Nummer": get_required_key(flat_record,"Tiltak.Nummer"),
                "Tekst":  get_required_key(flat_record,"Tiltak.Tekst"),
                "ErDeltiltak":  get_required_key(flat_record,"Tiltak.ErDeltiltak")
            },
            "Kapittel": {
                "Nummer":  get_required_key(flat_record,"Kapittel.Nummer"),
                "Tekst":  get_required_key(flat_record,"Kapittel.Tekst")
            },
            "Maal": {
                "Nummer":  get_required_key(flat_record,"Maal.Nummer"),
                "Tekst":  get_required_key(flat_record,"Maal.Tekst")
            }
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
        "digitaliseringstiltak_report_id"
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
        "AnsvarligVirksomhet.Organisasjonsnummer"
    ]
    
    for field in org_numbers:
        org_number = str(prefill_data_row[field])
        if not _is_valid_org_number(org_number):
            raise PrefillValidationError(f"Invalid organisation number format in {field}: {org_number} (must be 9 digits)")
    
    # 3. Validate digitaliseringstiltak_report_id (UUID)
    report_id = prefill_data_row["digitaliseringstiltak_report_id"]
    if not _is_valid_uuid(str(report_id)):
        raise PrefillValidationError(f"Invalid UUID format for digitaliseringstiltak_report_id: {report_id}")
    
    # 4. Validate email
    email = prefill_data_row["Kontaktperson.EPostadresse"]
    if not _is_valid_email(str(email)):
        raise PrefillValidationError(f"Invalid email format: {email}")
    
    # 5. Validate phone number
    phone = prefill_data_row["Kontaktperson.Telefonnummer"] 
    if not _is_valid_phone(str(phone)):
        raise PrefillValidationError(f"Invalid phone number format: {phone}")
    
    # 6. Validate string fields that should be numbers as strings
    number_string_fields = [
        "Tiltak.Nummer",
        "Tiltak.Tekst", 
        "Kapittel.Nummer",
        "Kapittel.Tekst",
        "Maal.Nummer", 
        "Maal.Tekst"
    ]
    
    for field in number_string_fields:
        value = prefill_data_row[field]
        if not isinstance(value, str):
            raise PrefillValidationError(f"Field {field} must be string, got {type(value)}")
        
        # Check if it contains at least some numeric content (allow formats like "2.1.4")
        if not re.search(r'\d', value):
            raise PrefillValidationError(f"Field {field} must contain numbers: {value}")
    
    # 7. Validate boolean field
    tiltak_er_deltiltak = prefill_data_row["Tiltak.ErDeltiltak"]
    if not isinstance(tiltak_er_deltiltak, bool):
        raise PrefillValidationError(f"Field Tiltak.ErDeltiltak must be boolean, got {type(tiltak_er_deltiltak)}")
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
    org_number = org_number.replace(' ', '').replace('-', '')
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
    uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    return re.match(uuid_pattern, uuid_string.lower()) is not None


def _is_valid_email(email: str) -> bool:
    """Validate email format"""
    if not isinstance(email, str):
        return False
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(email_pattern, email) is not None


def _is_valid_phone(phone: str) -> bool:
    """Validate Norwegian phone number format"""
    if not isinstance(phone, str):
        return False
    # Remove spaces and common separators
    cleaned = re.sub(r'[\s\-\(\)]', '', phone)
    # Norwegian format: +47 followed by 8 digits, or just 8 digits
    return re.match(r'^(\+47)?[0-9]{8}$', cleaned) is not None


def get_today_date():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")

def check_date_before(reference_date: str, compare_date: str):
    if not reference_date:
        raise ValueError("Reference date string is empty")
    if not compare_date:
        raise ValueError("Comapre date string is empty")
    return datetime.fromisoformat(reference_date) < datetime.fromisoformat(compare_date)

def add_time_delta(base_date_str: str, time_delta_str: str):
    if not time_delta_str:
        raise ValueError("Timedelta string is empty")
    base_date = datetime.fromisoformat(base_date_str)
    time_delta = isodate.parse_duration(time_delta_str)
    result = base_date + time_delta
    return result.isoformat().replace("+00:00", "Z")

def get_initiell_date(reported_data: DataModel, time_delta: Optional[str]) -> Optional[str]:
    initiell = reported_data.get("Initiell")
    if initiell.get("ErTiltaketPaabegynt"):
        initell_date = add_time_delta(initiell.get("DatoPaabegynt"), time_delta)
        if check_date_before(initell_date, get_today_date()):
            return add_time_delta(get_today_date(), time_delta)
        return add_time_delta(initiell.get("DatoPaabegynt"), time_delta)
    else:
        if initiell.get("VetOppstartsDato"):
            return add_time_delta(initiell.get("DatoForventetOppstart"), time_delta)
        else: 
            return add_time_delta(get_today_date(), time_delta)
        
def get_oppstart_date(reported_data: DataModel, time_delta: str) -> str:
    oppstart = reported_data.get("Oppstart")
    result_date = add_time_delta(oppstart.get("ForventetSluttdato"), time_delta)
    if check_date_before(result_date, get_today_date()):
        return get_today_date()
    return result_date

def get_status_date(reported_data: DataModel, time_delta: Optional[str]) -> Optional[str]:
    oppstart = reported_data.get("Oppstart")
    status = reported_data.get("Status")    
    if status.get("ErArbeidAvsluttet"):
        return get_today_date()
    else:
        return oppstart.get("ForventetSluttdato")

