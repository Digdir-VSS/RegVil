
from typing import Any, Dict
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential 
from pathlib import Path
import logging
import json

from clients.instance_client import AltinnInstanceClient, get_meta_data_info
from clients.instance_logging import InstanceTracker

def write_to_json(data: Dict[str, Any], path_to_folder: Path, filename: str) -> None:
    with open(path_to_folder / filename, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=4)

def load_in_json(path_to_json_file: Path) -> Dict[str, Any]:
    with open(path_to_json_file, 'r', encoding='utf-8') as file:
        return json.load(file)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename=Path(__file__).parent / "data" / "check_update_data_logging.log"
)
logger = logging.getLogger(__name__)

credential = DefaultAzureCredential()
client = SecretClient(vault_url="https://keyvaultvss.vault.azure.net/", credential=credential)
secret = client.get_secret("rapdigtest")
secret_value = secret.value

def main():
    maskinport_client = load_in_json(Path(__file__).parent / "data" / "maskinporten_config.json")
    maskinporten_endpoints = load_in_json(Path(__file__).parent / "data" / "maskinporten_endpoints.json")
    test_config_client_file = load_in_json(Path(__file__).parent / "data" / "test_config_client_file.json")
    maskinporten_endpoint = maskinporten_endpoints[test_config_client_file["environment"]]
    path_to_initiell_skjema_storage = Path(__file__).parent / "data" / "data_storage" / "initiell_skjema" 

    regvil_instance_client = AltinnInstanceClient.init_from_config(test_config_client_file, {"maskinport_client": maskinport_client, "secret_value": secret_value, "maskinporten_endpoint": maskinporten_endpoint})
    tracker = InstanceTracker.from_log_file(Path(__file__).parent / "data" / "instance_log" / "instance_log.json")

    list_initiell_skjema_created = tracker.get_events_from_log("initiell_skjema_instance_created")
    list_initiell_skjema_downloaded = tracker.get_events_from_log("initiell_skjema_instance_downloaded")

    downloaded_instance_ids = {event["instanceId"] for event in list_initiell_skjema_downloaded}
    pending_instances = [event for event in list_initiell_skjema_created if event["instanceId"] not in downloaded_instance_ids]
    
    for pending_instance in pending_instances:
        instance_meta = regvil_instance_client.get_instance(pending_instance["instancePartyId"], pending_instance["instanceId"])

        if not instance_meta:
            logger.warning(f"No instance metadata returned for {pending_instance['instanceId']}")
            continue

        try:
            instance_meta_info = instance_meta.json()
            meta_data = get_meta_data_info(instance_meta_info["data"])
            tags = meta_data["tags"]

            if tags == ["InitiellSkjemaLevert"] and meta_data["lastChangedBy"] == meta_data["createdBy"]:
                instance_data = regvil_instance_client.get_instance_data(
                    pending_instance["instancePartyId"],
                    pending_instance["instanceId"],
                    pending_instance["data_info"]["dataGuid"]
                )

                data_to_storage = {
                    "meta_info": {
                        "org_number": pending_instance["org_number"],
                        "instancePartyId": pending_instance["instancePartyId"],
                        "instanceId": pending_instance["instanceId"],
                        "dataGuid": pending_instance["data_info"]["dataGuid"],
                        "digitaliseringstiltak_report_id": pending_instance["digitaliseringstiltak_report_id"]
                    },
                    "data": instance_data.json()
                }

                party_id, instance_id = pending_instance['instanceId'].split("/")
                filename = f"initiellskjema_{pending_instance['org_number']}_{pending_instance['digitaliseringstiltak_report_id']}_{party_id}_{instance_id}.json"
                write_to_json(data_to_storage, path_to_initiell_skjema_storage, filename)

                response = regvil_instance_client.tag_instance_data(
                    pending_instance["instancePartyId"],
                    pending_instance["instanceId"],
                    pending_instance["data_info"]["dataGuid"],
                    "InitiellSkjemaDownloaded"
                )

                tracker.logging_instance(
                    pending_instance['org_number'],
                    pending_instance["digitaliseringstiltak_report_id"],
                    instance_meta_info,
                    "initiell_skjema_instance_downloaded"
                )
                tracker.save_to_disk()

                logger.info(f"Successfully downloaded and tagged: {filename} (HTTP {response.status_code})")

            else:
                logger.info(f"Already downloaded or invalid tags for: {pending_instance['digitaliseringstiltak_report_id']} - {pending_instance['instanceId']}")
        except Exception as e:
            logger.exception(f"Error processing instance {pending_instance['instanceId']}")
            raise


if __name__ == "__main__":
    main()