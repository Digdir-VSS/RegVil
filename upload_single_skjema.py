from typing import Any, Dict, Tuple
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential
from pathlib import Path
import json
import logging
from dotenv import load_dotenv
import os

from clients.instance_client import AltinnInstanceClient, get_meta_data_info
from clients.instance_logging import InstanceTracker
from config.type_dict_structure import DataModel
from config.config_loader import load_full_config, APIConfig

load_dotenv()

credential = DefaultAzureCredential()
client = SecretClient(
    vault_url=os.getenv("MASKINPORTEN_SECRET_VAULT_URL"), credential=credential
)
secret = client.get_secret(os.getenv("MASKINPORTEN_SECRET_NAME"))
secret_value = secret.value

def split_party_instance_id(party_instance_id: str) -> Tuple[str]:
     party_id, instance_id = party_instance_id.split("/")
     return party_id, instance_id

def create_payload(org_number: str, dato: str, api_config: APIConfig, prefill_data: DataModel) -> Dict[str, Tuple[str, str, str]]:
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
     

def load_in_json(path_to_json_file: Path) -> Any:
    with open(path_to_json_file, "r", encoding="utf-8") as file:
        return json.load(file)


def run(org_number: str, digitaliseringstiltak_report_id: str, dato: str, app_name: str, prefill_data: DataModel) -> None:

    logging.info("Starting Altinn survey sending instance processing")
    path_to_config_folder = Path(__file__).parent / "config_files"
    api_config = load_full_config(path_to_config_folder, app_name, os.getenv("ENV"))

    regvil_instance_client = AltinnInstanceClient.init_from_config(
        api_config,
    )

    tracker = InstanceTracker.from_directory(f"{os.getenv('ENV')}/event_log/")

    logging.info(f"Processing org {org_number}, report {digitaliseringstiltak_report_id}")

    if regvil_instance_client.instance_created(
        org_number, api_config.app_config.tag["tag_instance"]
        ):
        logging.warning(
                f"Skipping org {org_number} and report {digitaliseringstiltak_report_id}- already in storage"
            )
        return {
        "status": 200,
        "report_id":digitaliseringstiltak_report_id,
        "org_number": org_number,
        "app_name": api_config.app_config.app_name,
    }
    logging.info(
            f"Creating new instance for org {org_number} and report id {digitaliseringstiltak_report_id}"
        )
    
    files = create_payload(org_number, dato, api_config, prefill_data)
    created_instance = regvil_instance_client.post_new_instance(files)
    if created_instance.status_code == 201:
        instance_meta_data = created_instance.json()
        party_id, instance_id = split_party_instance_id(instance_meta_data["id"])
        instance_data_meta_data = get_meta_data_info(
                instance_meta_data.get("data")
            )

        logging.info(
                f"Successfully created instance for org nr {org_number}/ report id {digitaliseringstiltak_report_id}: {instance_meta_data['id']}"
            )
        tracker.logging_instance(
            instance_id,
            org_number,
            digitaliseringstiltak_report_id,
            instance_meta_data,
            instance_data_meta_data,
            api_config.app_config.tag["tag_instance"],
            )
        tracker.save_to_disk()
        tag_result = regvil_instance_client.tag_instance_data(
                party_id,
                instance_id,
                instance_data_meta_data["id"],
                api_config.app_config.tag["tag_instance"],
            )
        if tag_result.status_code == 201:
                logging.info(f"Successfully tagged instance for org number: {org_number} party id: {instance_meta_data['instanceOwner']['partyId']} instance id: {instance_meta_data['id']}")
        else:
                logging.warning(f"Failed to tag instance org number: {org_number} party id: {instance_meta_data['instanceOwner']['partyId']} instance id: {instance_meta_data['id']}")
        
        return {
        "status": 200,
        "instance_id": instance_id,
        "party_id": instance_meta_data["instanceOwner"]["partyId"],
        "digitaliseringstiltak_report_id":digitaliseringstiltak_report_id,
        "org_number": org_number,
        "app_name": api_config.app_config.app_name,
    }
    else:
        logging.warning(
                f"Failed to create instance for org nr {org_number}/ report id {digitaliseringstiltak_report_id}: Status {created_instance.status_code}"
            )
        try:
            error_details = created_instance.json()
            error_msg = error_details.get("error", "Unknown error")

        except Exception:
            error_msg = created_instance.text or "No error details"

        logging.error(
                    f"API Error: Org {org_number}, "
                    f"Report {digitaliseringstiltak_report_id} - "
                    f"Status: {created_instance.status_code} - "
                    f"Error message: {error_msg}"
                )
        return {
        "status": 500,
        "instance_id": instance_meta_data["id"],
        "party_id": instance_meta_data["instanceOwner"]["partyId"],
        "digitaliseringstiltak_report_id":digitaliseringstiltak_report_id,
        "org_number": org_number,
        "app_name": api_config.app_config.app_name,
    }