import re
from typing import Any, Dict
import logging
from azure.storage.blob import BlobServiceClient
from azure.identity import DefaultAzureCredential, EnvironmentCredential
from dotenv import load_dotenv
import os
import json

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

def connect_blob():
    try:
        load_dotenv()

        if os.getenv("AZURE_CLIENT_ID"):
            # print("Using EnvironmentCredential for local dev")
            credential = EnvironmentCredential()
        else:
            # print("Using DefaultAzureCredential (includes managed identity in Azure)")
            credential = DefaultAzureCredential()

        blob_service_client = BlobServiceClient(os.getenv('BLOB_STORAGE_ACCOUNT_URL'), credential=credential)
        container_client = blob_service_client.get_container_client("regvil-blob-container")
        
        return container_client

    except Exception as e:
        logging.error(f"Error connecting to Azure Blob Storage: {e}")
        return None
    
def blob_exists(file: str) -> bool:
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
    if not directory.endswith('/'):
        directory += '/'
    try:
        blobs = container_client.list_blobs(name_starts_with=directory)
        return any(blob.name.startswith(directory) for blob in blobs)
    except Exception as e:
        logging.error(f"Error checking existence of directory {directory}: {e}")
        return False