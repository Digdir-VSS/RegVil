from typing import Any, Dict
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential
from pathlib import Path
import logging
import json
from dotenv import load_dotenv
import os

from clients.instance_client import AltinnInstanceClient, get_meta_data_info
from clients.instance_logging import InstanceTracker, find_event_by_instance_blob
from config.config_loader import load_full_config

load_dotenv()

def write_to_json(data: Dict[str, Any], path_to_folder: Path, filename: str) -> None:
    with open(path_to_folder / filename, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=4)

def load_in_json(path_to_json_file: Path) -> Dict[str, Any]:
    with open(path_to_json_file, 'r', encoding='utf-8') as file:
        return json.load(file)

credential = DefaultAzureCredential()
client = SecretClient(vault_url=os.getenv("MASKINPORTEN_SECRET_VAULT_URL"), credential=credential)
secret = client.get_secret(os.getenv("MASKINPORTEN_SECRET_NAME"))
secret_value = secret.value

def main():
    path_to_config_folder = Path(__file__).parent / "config_files"
    config = load_full_config(path_to_config_folder, "regvil-2025-initiell", os.getenv("ENV"))
    # path_to_initiell_skjema_storage = Path(__file__).parent / "data" / os.getenv("ENV") / "data_storage"

    regvil_instance_client = AltinnInstanceClient.init_from_config(config)
    tracker = InstanceTracker.from_directory(f"{os.getenv("ENV")}/event_log/")

    pending_instance = find_event_by_instance_blob(f"{os.getenv("ENV")}/event_log/","regvil-2025-initiell", "0a532b55-76b3-41f9-9b3c-58eee9eaea6f", config.app_config.tag["tag_instance"])

    instance_meta = regvil_instance_client.get_instance(pending_instance["instancePartyId"], f"{pending_instance['instancePartyId']}/{pending_instance['instanceId']}")

    if not instance_meta:
        logging.warning(f"No instance metadata returned for {pending_instance['instanceId']}")

    try:
        instance_meta_info = instance_meta.json()
        meta_data = get_meta_data_info(instance_meta_info["data"])
        # tags = meta_data["tags"]
        if True:
        #if tags == [config.app_config.tag["tag_instance"]] and meta_data["lastChangedBy"] == meta_data["createdBy"]:
            instance_data = regvil_instance_client.get_instance_data(
                    pending_instance["instancePartyId"],
                    f"{pending_instance['instancePartyId']}/{pending_instance['instanceId']}",
                    pending_instance["data_info.dataGuid"]
                )

            response = regvil_instance_client.tag_instance_data(
                    pending_instance["instancePartyId"],
                    f"{pending_instance['instancePartyId']}/{pending_instance['instanceId']}",
                    pending_instance["data_info.dataGuid"],
                    config.app_config.tag["tag_download"]
                )

            tracker.logging_instance(
                    pending_instance['org_number'],
                    pending_instance["digitaliseringstiltak_report_id"],
                    instance_meta_info,
                    instance_data.json(),
                    config.app_config.tag["tag_download"]
                )
            tracker.save_to_disk()

            logging.info(f"Successfully downloaded and tagged: {tracker.file_name} (HTTP {response.status_code})")

        else:
            logging.info(f"Already downloaded or invalid tags for: {pending_instance['digitaliseringstiltak_report_id']} - {pending_instance['instanceId']}")
    except Exception as e:
            logging.exception(f"Error processing instance {pending_instance['instanceId']}")
            raise


if __name__ == "__main__":
    main()