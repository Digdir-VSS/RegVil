import re
from typing import Any, Dict, List
import json
import datetime
import os
import shutil
from config.utils import chech_file_exists, write_blob, read_blob
import logging
class PrefillValidationError(Exception):
    pass


def get_reportid_from_blob(directory: str, appId: str, instance_id: str, event_type: str) -> Dict[str, Any]:
    if not chech_file_exists(directory+f"{appId}_{event_type}_{instance_id}.json"):
        logging.warning(f"File {appId}_{event_type}_{instance_id}.json does not exist.")
        return None
    json_data = read_blob(directory+f"{appId}_{event_type}_{instance_id}.json")
    return json_data["digitaliseringstiltak_report_id"]


class InstanceTracker:
    def __init__(self, log_file: Dict[str, Any], log_path: str = None):
        self.log_file = {}
        self.file_name = "" 
        self.log_path = log_path
        self.log_changes = {}
    
    @classmethod
    def from_directory(cls, path_to_json_dir: str):
        # Now expects a directory, not a file
        return cls({"organisations": {}}, log_path=path_to_json_dir)
    
      
    def logging_varlsing(self, org_number: str, org_name: str,app_name: str,send_time: str, digitaliseringstiltak_report_id: str, shipment_id: str, recipientEmail: str, event_type: str):
        if not org_number or not digitaliseringstiltak_report_id:
          logging.warning("Organization number and report ID cannot be empty. Shipment_id: {shipment_id}, org_number: {org_number}, digitaliseringstiltak_report_id: {digitaliseringstiltak_report_id}")
        
        instance_log_entry = {
            "event_type": event_type,
            "digitaliseringstiltak_report_id": digitaliseringstiltak_report_id, 
            "org_number": org_number,
            "virksomhets_name":org_name,
            "processed_timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            "sent_time": send_time,
            "app_name": app_name,
            "shipment_id": shipment_id, 
            "recipientEmail": recipientEmail
        }
        write_blob(self.log_path+f"{digitaliseringstiltak_report_id}_{app_name}_{event_type}_{shipment_id}.json",instance_log_entry)

    def logging_instance(self, instance_id: str,org_number: str, digitaliseringstiltak_report_id: str, instance_meta_data: dict, data_dict: dict ,event_type: str):
        if not org_number or not digitaliseringstiltak_report_id:
            logging.warning("Organization number and report ID cannot be empty. Instance_id: {instance_id}, org_number: {org_number}, digitaliseringstiltak_report_id: {digitaliseringstiltak_report_id}")
        if not instance_meta_data:
            logging.warning("Instance meta data cannot be empty. Instance_id: {instance_id}, org_number: {org_number}, digitaliseringstiltak_report_id: {digitaliseringstiltak_report_id}")
        if not data_dict:
            logging.warning("Data dictionary cannot be empty. Instance_id: {instance_id}, org_number: {org_number}, digitaliseringstiltak_report_id: {digitaliseringstiltak_report_id}")
        if org_number != instance_meta_data['instanceOwner'].get("organisationNumber"):
            logging.warning(f"Organization numbers do not match: {org_number} != {instance_meta_data['instanceOwner'].get('organisationNumber')}. Instance_id: {instance_id}, org_number: {org_number}, digitaliseringstiltak_report_id: {digitaliseringstiltak_report_id}")
        
        datamodel_metadata = get_meta_data_info(instance_meta_data["data"])
        app_id = instance_meta_data["appId"].split("/")[-1]
        instance_log_entry = {
            "event_type": event_type,
            "appId": app_id,
            "digitaliseringstiltak_report_id": digitaliseringstiltak_report_id, 
            "org_number": org_number,
            "virksomhets_name": instance_meta_data.get("instanceOwner").get("party").get("name"),
            "processed_timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            "instancePartyId": instance_meta_data['instanceOwner'].get("partyId"),
            "instanceId": instance_id,
            "instance_info.last_changed": instance_meta_data.get('lastChanged'),
            "instance_info.last_changed_by": instance_meta_data.get('lastChangedBy'),
            "instance_info.created": instance_meta_data.get('created'),
            "data_info.last_changed": datamodel_metadata.get('lastChanged'),
            "data_info.last_changed_by": datamodel_metadata.get('lastChangedBy'),
            "data_info.created": datamodel_metadata.get('created'), 
            "data_info.dataGuid": datamodel_metadata.get('id'),
            "data": data_dict
        } 
        write_blob( self.log_path+f"{app_id}_{event_type}_{instance_id}.json",instance_log_entry)

                            
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