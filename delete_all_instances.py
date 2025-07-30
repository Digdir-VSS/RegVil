from typing import Any
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential
from pathlib import Path
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
    path_to_config_folder = Path(__file__).parent / "config_files"
    config = load_full_config(path_to_config_folder, "regvil-2025-initiell", os.getenv("ENV"))
    regvil_instance_client = AltinnInstanceClient.init_from_config(
        config,
    )
    answer = input("Write DELETE to delete all instances: ")
    if answer != "DELETE":
        print("Skipping deletion of all instances")
        return
    else:
        print("Deleting all instances")
        instance_ids = regvil_instance_client.get_stored_instances_ids()
        for instance in instance_ids:
            partyID, instance_id = instance["instanceId"].split("/")
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
=======
            print(f"Deleting instance {instance_id} for party {partyID}")
>>>>>>> bf24d3f (remove logging)
=======
>>>>>>> cb06886 (fix bug delete tag)
=======
>>>>>>> e4bb5a93a160f4c9eb7643faac18364d7ccc1b74
            instance = regvil_instance_client.get_instance(partyID, instance_id)
            instance_meta = instance.json()
            instance_data = instance_meta.get("data")
            print(f"Deleting orgnumber {instance_meta.get('instanceOwner').get('organisationNumber')} instance {instance_id} for party {partyID}")
            dataguid = get_meta_data_info(instance_data).get("id")
            tag = get_meta_data_info(instance_data).get("tags")
            print(tag)
            if tag:
                delete_tag = regvil_instance_client.delete_tag(partyID, instance_id, dataguid, tag[0])
                print(delete_tag.status_code)
            instance = regvil_instance_client.get_instance(partyID, instance_id)
            instance_meta = instance.json()
            instance_data = instance_meta.get("data")
            tag = get_meta_data_info(instance_data).get("tags")
            print(tag)
            
            instance_deleted = regvil_instance_client.delete_instance(partyID, instance_id)
            if instance_deleted.status_code in [200,201,204]:
                print(f"Successfully deleted instance {instance_id}")
            else:
                print(f"Failed to delete instance {instance_id}: {instance_deleted.text}")
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
            print("=====================\n")
=======
>>>>>>> bf24d3f (remove logging)
=======
            print("=====================\n")
>>>>>>> cb06886 (fix bug delete tag)
=======
            print("=====================\n")
>>>>>>> e4bb5a93a160f4c9eb7643faac18364d7ccc1b74
        return "All instances deleted successfully"

if __name__ == "__main__":
    main()
