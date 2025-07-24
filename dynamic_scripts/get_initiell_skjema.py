from typing import Any, Dict
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential
from pathlib import Path
import logging
import json
from dotenv import load_dotenv
import os

from clients.instance_client import AltinnInstanceClient, get_meta_data_info
from clients.instance_logging import InstanceTracker, find_event_by_instance
from config.config_loader import load_full_config

load_dotenv()

def is_valid_instance(meta_info: dict, tag_expected: str) -> bool:
    meta_data = get_meta_data_info(meta_info["data"])
    return (
        meta_data.get("tags") == [tag_expected] and
        meta_data.get("createdBy") != meta_data.get("lastChangedBy")
    )

def write_to_json(data: Dict[str, Any], path_to_folder: Path, filename: str) -> None:
    with open(path_to_folder / filename, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=4)

credential = DefaultAzureCredential()
client = SecretClient(vault_url=os.getenv("MASKINPORTEN_SECRET_VAULT_URL"), credential=credential)
secret = client.get_secret(os.getenv("MASKINPORTEN_SECRET_NAME"))
secret_value = secret.value

def run(party_id: str, instance_id: str, app_name: str) -> Dict[str, str]:
    path_to_config_folder = Path(__file__).parent.parent / "config_files"
    config = load_full_config(path_to_config_folder, app_name, os.getenv("ENV"))
    path_to_initiell_skjema_storage = Path(__file__).parent.parent / "data" / os.getenv("ENV") / "data_storage"

    regvil_instance_client = AltinnInstanceClient.init_from_config(config)
    tracker = InstanceTracker.from_log_file(Path(__file__).parent.parent / "data" /os.getenv("ENV") / "instance_log" / "instance_log.json")

    pending_instance = find_event_by_instance(tracker.log_file, instance_id, config.app_config.tag["tag_instance"])

    instance_meta = regvil_instance_client.get_instance(party_id, instance_id)

    if not instance_meta:
        logging.error(f"Failed to fetch instance: {instance_meta.status_code if instance_meta else 'No response'}")
        return None
    try:
        instance_meta_info = instance_meta.json()
        meta_data = get_meta_data_info(instance_meta_info["data"])
        tags = meta_data.get("tags")
        created_by = meta_data.get("createdBy")
        last_changed_by = meta_data.get("lastChangedBy")

        if is_valid_instance(meta_data, config.app_config.tag["tag_instance"]):
            instance_data = regvil_instance_client.get_instance_data(
                    party_id,
                    instance_id,
                    meta_data["id"]
                )
            if not instance_data:
                logging.error(f"Failed to fetch instance data for Party Id: {party_id} Instance id: {instance_id} and DataGuid: {meta_data['id']}")
                return None
            
            report_data = instance_data.json()
            data_to_storage = {
                    "meta_info": {
                        "org_number": instance_meta_info["instanceOwner"]["organisationNumber"],
                        "instancePartyId": party_id,
                        "instanceId": instance_id,
                        "dataGuid": meta_data["id"],
                        "digitaliseringstiltak_report_id": pending_instance["digitaliseringstiltak_report_id"]
                    },
                    "data": report_data
                }

            filename = f"initiellskjema_{instance_meta_info['instanceOwner']['organisationNumber']}_{pending_instance['digitaliseringstiltak_report_id']}_{party_id}_{instance_id}.json"
            write_to_json(data_to_storage, path_to_initiell_skjema_storage, filename) #change to azure data blob function

            response = regvil_instance_client.tag_instance_data(
                    party_id,
                    instance_id,
                    meta_data["id"],
                    config.app_config.tag["tag_download"]
                )

            tracker.logging_instance(
                    instance_meta_info["instanceOwner"]["organisationNumber"],
                    pending_instance["digitaliseringstiltak_report_id"],
                    instance_meta_info,
                    config.app_config.tag["tag_download"]
                )
            tracker.save_to_disk()
            logging.info(f"Successfully downloaded and tagged: {filename} (HTTP {response.status_code})")
            return {"dato": None, "next_app_name": config.workflow_dag.get_next(app_name)} #Write logic to get dato out of download

        else:
            logging.warning(f"Already downloaded or invalid tags for: {pending_instance['digitaliseringstiltak_report_id']} - {pending_instance['instanceId']}")
            return None
    except Exception as e:
            logging.exception(f"Error processing party id: {party_id}, instance id {instance_id}")
            raise