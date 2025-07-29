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


def run(org_number: str, digitaliseringstiltak_report_id: str, dato: str, app_name: str, prefill_data: DataModel) -> str:

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
        return 204
    
    logging.info(
            f"Creating new instance for org {org_number} and report id {digitaliseringstiltak_report_id}"
        )
    
    files = create_payload(org_number, dato, api_config, prefill_data)
    created_instance = regvil_instance_client.post_new_instance(files)
    if not created_instance:
        logging.error(f"Failed to send out report id {digitaliseringstiltak_report_id} instance to OrgNumber {org_number}")
        return 502
    
    if created_instance.status_code not in [200, 201]:
        logging.error(created_instance.text)
        return created_instance.status_code

    try:
        instance_meta_data = created_instance.json()
    except ValueError:
        logging.error(f"Failed to send out report id {digitaliseringstiltak_report_id} instance to OrgNumber {org_number}")
        return 502
    
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
            return 206
    logging.info(f"Successfully send out instance id: {instance_id}, party id {party_id}, report id: {digitaliseringstiltak_report_id} to app name {app_name} Orgnumber: {org_number}")
    return 200