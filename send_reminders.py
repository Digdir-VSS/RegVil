from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential
from pathlib import Path
import logging
from dotenv import load_dotenv
import os
from datetime import datetime, timezone, timedelta
from clients.instance_client import AltinnInstanceClient, get_meta_data_info
from config.config_loader import load_full_config
from config.utils import list_blobs_with_prefix, read_blob
from send_warning import run as send_warning
load_dotenv()
credential = DefaultAzureCredential()
client = SecretClient(
    vault_url=os.getenv("MASKINPORTEN_SECRET_VAULT_URL"), credential=credential
)
secret = client.get_secret(os.getenv("MASKINPORTEN_SECRET_NAME"))
secret_value = secret.value
apps = ["regvil-2025-initiell", "regvil-2025-oppstart", "regvil-2025-status", "regvil-2025-slutt"]
def main() -> None:
    logging.info("Checking for instances that have not been answered")
    path_to_config_folder = Path(__file__).parent / "config_files"
    for app in apps:
        config = load_full_config(path_to_config_folder, app, os.getenv("ENV"))
        regvil_instance_client = AltinnInstanceClient.init_from_config(
            config,
        )
        logging.info("Checking for instances that have not been answered")
        print("Checking for instances that have not been answered")
        instance_ids = regvil_instance_client.get_stored_instances_ids()
        for instance in instance_ids:
            partyID, instance_id = instance["instanceId"].split("/")
            instance = regvil_instance_client.get_instance(partyID, instance_id)
            if instance.status_code == 200:
                instance_meta = instance.json()
                instance_data = instance_meta.get("data")
                dataguid = get_meta_data_info(instance_data).get("id")
                tag = get_meta_data_info(instance_data).get("tags")
                visibleAfter = instance_meta.get("visibleAfter")
                visibleAfterformated = datetime.fromisoformat(visibleAfter)
                if instance_meta.get("isHardDeleted"):
                    logging.info(f"Instance {instance_id} is already hard deleted.")
                    continue
                if instance_meta.get("isSoftDeleted"):
                    logging.warning(f"Instance {instance_id} is soft deleted.")
                    continue
                if visibleAfterformated > datetime.now(timezone.utc):
                    logging.info(f"Instance {instance_id} is not yet visible.")
                    continue
                if visibleAfterformated > datetime.now(timezone.utc) - timedelta(days=14):
                    logging.info(f"Instance {instance_id} is still within the 14-day visibility period.")
                    continue   
                if len(tag) == 0 :
                    logging.info(f"Instance {instance_id} has no tag. Probalby deleted.")
                    continue
                if instance_meta.get("status").get("createdBy") == instance_meta.get("status").get("lastChangedBy"):
                    data_response = regvil_instance_client.get_instance_data(partyID, instance_id, dataguid)
                    if data_response.status_code == 200:
                        data = data_response.json()
                        already_sent = list_blobs_with_prefix(f"{os.getenv("ENV")}/varsling/{tag[0]}_{app}")
                        for blob in already_sent:
                            json_file = read_blob(blob)
                            if datetime.fromisoformat(json_file["sent_time"]) >datetime.now(timezone.utc) - timedelta(days=14):
                                continue
                        org_number = data.get("Prefill").get("AnsvarligVirksomhet").get("Organisasjonsnummer")
                        dato = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                        logging.info(f"Instance {instance_id} is created by the same user as last changed. Instance not answered.")
                        file ={"org_number":org_number, "digitaliseringstiltak_report_id":tag[0], "dato":dato, "app_name":app, 
                        "prefill_data":data}
                        send_warning(**file)
                    else:
                        logging.error(f"Failed to get instance data for {instance_id} for party {partyID}: {data_response.text}")
                        continue
            else:
                logging.error(f"Failed to get instance {instance_id} for party {partyID}: {instance.text}")
                continue
    return "All reminders have been sent."

if __name__ == "__main__":
    main()
