from typing import Any
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential
from pathlib import Path
import logging
from dotenv import load_dotenv
import os

from clients.instance_client import AltinnInstanceClient, get_meta_data_info
from config.config_loader import load_full_config

load_dotenv()
credential = DefaultAzureCredential()
client = SecretClient(
    vault_url=os.getenv("MASKINPORTEN_SECRET_VAULT_URL"), credential=credential
)
secret = client.get_secret(os.getenv("MASKINPORTEN_SECRET_NAME"))
secret_value = secret.value
def main() -> None:
    logging.info("Starting Altinn survey sending instance processing")
    path_to_config_folder = Path(__file__).parent / "config_files"
    config = load_full_config(path_to_config_folder, "regvil-2025-slutt", os.getenv("ENV"))
    regvil_instance_client = AltinnInstanceClient.init_from_config(
        config,
    )
    answer = input("Write DELETE to delete all instances: ")
    if answer != "DELETE":
        logging.info("Skipping deletion of all instances")
        print("Skipping deletion of all instances")
        return
    else:
        logging.info("Deleting all instances")
        print("Deleting all instances")
        instance_ids = regvil_instance_client.get_stored_instances_ids()
        for instance in instance_ids:
            partyID, instance_id = instance["instanceId"].split("/")
            logging.info(f"Deleting instance {instance_id} for party {partyID}")
            instance = regvil_instance_client.get_instance(partyID, instance_id)
            instance_meta = instance.json()
            instance_data = instance_meta.get("data")
            dataguid = get_meta_data_info(instance_data).get("id")
            tag = get_meta_data_info(instance_data).get("tags")
            if tag:
                tag_response = regvil_instance_client.delete_tag(partyID, instance_id, dataguid, tag[0])
                print(tag_response.status_code)
            instance_deleted = regvil_instance_client.delete_instance(partyID, instance_id)
            if instance_deleted.status_code in [200,201,204]:
                logging.info(f"Successfully deleted instance {instance_id}")
            else:
                logging.error(f"Failed to delete instance {instance_id}: {instance_deleted.text}")
        return "All instances deleted successfully"

if __name__ == "__main__":
    main()
