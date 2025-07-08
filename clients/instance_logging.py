import re
from typing import Any, Dict, List
import json
import datetime
import os
import shutil

class PrefillValidationError(Exception):
    pass

def _write_json_file(log_data: Dict[str, Any], file_path: str) -> None:
    file_path_str = str(file_path)

    # 1. Load existing data
    if os.path.exists(file_path_str):
        backup_path = file_path_str.replace('.json', f'_backup_log.json')
        shutil.copy2(file_path_str, backup_path)
    
    with open(file_path_str, 'w', encoding='utf-8') as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)


class InstanceTracker:
    def __init__(self, log_file: Dict[str, Any], log_path: str = None):
        self.log_file = log_file
        self.log_changes = {} 
        self.log_path = log_path
    
    @classmethod
    def from_log_file(cls, path_to_json_file: str):
        try:
            with open(path_to_json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Ensure proper structure
            if "organisations" not in data:
                data["organisations"] = {}
            return cls(data, log_path=path_to_json_file)
        except FileNotFoundError:
            # File doesn't exist, start with proper structure
            data = {"organisations": {}}
            return cls(data, log_path=path_to_json_file)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in log file: {e}")

    def has_processed_instance(self, org_number: str, digitaliseringstiltak_report_id: str) -> bool:
        org_data = self.log_file.get("organisations", {}).get(org_number, {})
        events = org_data.get("events", [])
        for event in events:
            if (event.get("event_type") == "initiell_skjema_instance_created" and
                event.get("digitaliseringstiltak_report_id") == digitaliseringstiltak_report_id):
                return True
        return False
    
    def get_events_from_log(self, event_type: str) -> List[Dict[str, Any]]:
        all_look_up_events = []
        for _, meta_info in self.log_file["organisations"].items():
            look_up_events = [event for event in meta_info["events"] if event["event_type"] == event_type]
            all_look_up_events.extend(look_up_events)
        return all_look_up_events

        
    def logging_instance(self, org_number: str, digitaliseringstiltak_report_id: str, instance_meta_data: dict, event_type: str):
        if not org_number or not digitaliseringstiltak_report_id:
          raise ValueError("Organization number and report ID cannot be empty")
        
        if not instance_meta_data:
            raise ValueError("Instance meta data cannot be empty")

        if org_number != instance_meta_data['instanceOwner'].get("organisationNumber"):
            raise ValueError(f"Organization numbers do not match: {org_number} != {instance_meta_data['instanceOwner'].get('organisationNumber')}")
        
        datamodel_metadata = get_meta_data_info(instance_meta_data["data"])
        instance_log_entry = {
            "event_type": event_type,#"initiell_skjema_instance_created"
            "digitaliseringstiltak_report_id": digitaliseringstiltak_report_id, 
            "org_number": org_number,
            "virksomhets_name": instance_meta_data.get("instanceOwner").get("party").get("name"),
            "processed_timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            "instancePartyId": instance_meta_data['instanceOwner'].get("partyId"),
            "instanceId": instance_meta_data.get("id"),
            "instance_info": {
                "last_changed": instance_meta_data.get('lastChanged'),
                "last_changed_by": instance_meta_data.get('lastChangedBy'),
                "created": instance_meta_data.get('created'),
            },
            "data_info": {
                "last_changed": datamodel_metadata.get('lastChanged'),
                "last_changed_by": datamodel_metadata.get('lastChangedBy'),
                "created": datamodel_metadata.get('created'),
                "dataGuid": datamodel_metadata.get('id'),
            },
        }

            # Simplified - self.log_file["organisations"] already exists from initialization
        if org_number not in self.log_file["organisations"]:
            self.log_file["organisations"][org_number] = {"events": []}

        self.log_file["organisations"][org_number]["events"].append(instance_log_entry)
        self.log_changes[org_number] = instance_log_entry


    def save_to_disk(self) -> None:
        if not self.log_path:
            raise ValueError("No log file path set.")
        _write_json_file(self.log_file, self.log_path)
        
        # Clear changes after saving
        self.log_changes.clear()

                            
def get_meta_data_info(list_of_data_instance_meta_info: List[Dict[str, str]]) -> Dict[str, str]:
    if not list_of_data_instance_meta_info:
        raise ValueError("No instance metadata provided.")

    for instance in list_of_data_instance_meta_info:
        if (
            instance.get("dataType") == "DataModel" and 
            instance.get("contentType") in ["application/xml", "application/json"]
        ):
            return instance

    raise ValueError("No instance with dataType='DataModel' and contentType='application/xml' or 'application/json' was found.")

def get_required_key(record, key):
    if key not in record:
        raise KeyError(f"Missing required key: {key}")
    return record[key]

def transform_flat_to_nested_with_prefill(flat_record):
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
                "Kortnavn":  get_required_key(flat_record,"Tiltak.Kortnavn"),
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

def validate_prefill_data(prefill_data_row: Dict[str, Any]) -> bool:

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
        "Tiltak.Kortnavn",
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