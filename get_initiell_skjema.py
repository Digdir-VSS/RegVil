from typing import Any, Dict, Tuple
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential
from pathlib import Path
import logging
import json
from dotenv import load_dotenv
import os

from clients.instance_client import AltinnInstanceClient, get_meta_data_info
from clients.instance_logging import InstanceTracker, get_reportid_from_blob
from config.config_loader import load_full_config

load_dotenv()

def is_valid_instance(meta_data: dict) -> bool:
    if meta_data:
        return (
            meta_data.get("createdBy") != meta_data.get("lastChangedBy")
        )
    else:
        return False

def write_to_json(data: Dict[str, Any], path_to_folder: Path, filename: str) -> None:
    with open(path_to_folder / filename, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=4)

credential = DefaultAzureCredential()
client = SecretClient(vault_url=os.getenv("MASKINPORTEN_SECRET_VAULT_URL"), credential=credential)
secret = client.get_secret(os.getenv("MASKINPORTEN_SECRET_NAME"))
secret_value = secret.value

def run(party_id: str, instance_id: str, app_name: str) -> Tuple[Dict[str, str], str]:
    path_to_config_folder = Path(__file__).parent / "config_files"
    config = load_full_config(path_to_config_folder, app_name, os.getenv("ENV"))


    regvil_instance_client = AltinnInstanceClient.init_from_config(config)
    tracker = InstanceTracker.from_directory(f"{os.getenv('ENV')}/event_log/")


    digitaliseringstiltak_report_id = get_reportid_from_blob(f"{os.getenv('ENV')}/event_log/",app_name, instance_id, config.app_config.tag["tag_instance"])

    instance_meta = regvil_instance_client.get_instance(party_id, instance_id)

    if not instance_meta:
        logging.error(f"Failed to fetch party id: {party_id} instance id: {instance_id}")
        return {}, 502
    if instance_meta.status_code not in [200, 201]:
        return {}, str(instance_meta.status_code)

    try:
        instance_meta_info = instance_meta.json()
    except ValueError:
        logging.error(f"Error processing party id: {party_id}, instance id {instance_id}")
        return {}, 502
    meta_data = get_meta_data_info(instance_meta_info.get("data"))

    if is_valid_instance(meta_data):
        instance_data = regvil_instance_client.get_instance_data(
                    party_id,
                    instance_id,
                    meta_data.get("id")
                )

        report_data = instance_data.json()           

        tracker.logging_instance(
                    instance_id,
                    instance_meta_info["instanceOwner"]["organisationNumber"],
                    digitaliseringstiltak_report_id,
                    instance_meta_info,
                    report_data,
                    config.app_config.tag["tag_download"]
                )
                    tracker.save_to_disk()
            
        logging.info(f"Successfully downloaded: OrgNumber {instance_meta_info['instanceOwner']['organisationNumber']} App name: {app_name} InstanceId: {instance_id}) DigireportId: {digitaliseringstiltak_report_id}")
        return {"org_number": instance_meta_info["instanceOwner"]["organisationNumber"], "digitaliseringstiltak_report_id": digitaliseringstiltak_report_id ,"dato": config.app_config.get_date(report_data), "app_name": config.workflow_dag.get_next(app_name), "prefill_data": report_data}, 200

    else:
        logging.warning(f"Already downloaded: {app_name} InstanceId: {instance_id} ReportId: {digitaliseringstiltak_report_id}")
        return {}, 204
