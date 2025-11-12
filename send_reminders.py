from typing import List
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential
from pathlib import Path
import logging
from dotenv import load_dotenv
import os
from datetime import datetime, timezone, timedelta
from clients.instance_client import AltinnInstanceClient, get_meta_data_info
from config.config_loader import load_full_config
from config.utils import list_blobs_with_prefix, read_blob, parse_date
from send_warning import run as send_warning
import pytz

load_dotenv()
credential = DefaultAzureCredential()
client = SecretClient(
    vault_url=os.getenv("MASKINPORTEN_SECRET_VAULT_URL"), credential=credential
)
secret = client.get_secret(os.getenv("MASKINPORTEN_SECRET_NAME"))
secret_value = secret.value
apps = [
    "regvil-2025-initiell",
    "regvil-2025-oppstart",
    "regvil-2025-status",
    "regvil-2025-slutt",
]

def get_latest_notification_date(tag: List[str], app: str) -> bool:
        already_sent = list_blobs_with_prefix(
                    f"{os.getenv('ENV')}/varsling/{tag[0]}_{app}"
                )
        notification_dates = []
        for blob in already_sent:
            blob_content = read_blob(blob)
            if blob_content["event_type"] == "Varsling1Send":
                notification_dates.append(datetime.fromisoformat(blob_content["sent_time"]))
        return notification_dates

def check_instance_active(instance_id, instance_meta, tag) -> bool:
    if instance_meta.get("isHardDeleted"):
        logging.info(f"Instance {instance_id} is already hard deleted.")
        return False
    if instance_meta.get("isSoftDeleted"):
        logging.info(f"Instance {instance_id} is soft deleted.")
        return False    
               
    if len(tag) == 0:
        logging.info(f"Instance {instance_id} has no tag. Probably deleted.")
        return False
    return True 


def run() -> None:
    logging.info("Checking for instances that have not been answered")
    path_to_config_folder = Path(__file__).parent / "config_files"
    sent_reminders = []
    for app in apps:
        config = load_full_config(path_to_config_folder, app, os.getenv("ENV"))
        regvil_instance_client = AltinnInstanceClient.init_from_config(
            config,
        )
        logging.info("Checking for instances that have not been answered")
        instance_ids = regvil_instance_client.fetch_instances_by_completion(instance_complete=False)
        for instance in instance_ids:
            partyID, instance_id = instance["instanceId"].split("/")
            inst_resp  = regvil_instance_client.get_instance(partyID, instance_id)
            if inst_resp.status_code != 200:
                continue

            instance_meta = inst_resp.json()
            instance_data = get_meta_data_info(instance_meta.get("data"))

            date_created = instance_data.get("created")
            visibleAfter = instance_meta.get("visibleAfter")
            visibleAfterformated = parse_date(visibleAfter)
            dateCreatedFormated = parse_date(date_created)
            dataguid = instance_data.get("id")
            tag = instance_data.get("tags")

            data_resp = regvil_instance_client.get_instance_data(partyID, instance_id, dataguid)
            if data_resp.status_code != 200:
                continue

            data = data_resp.json()
            if not check_instance_active(instance_id, instance_meta, tag):
                continue

            if dateCreatedFormated > datetime.now(pytz.UTC) - timedelta(days=14):
                logging.info(f"Instance {instance_id} is not older than 14 days and will not be processed.")
                continue
            if visibleAfterformated > datetime.now(pytz.UTC) - timedelta(days=14):
                logging.info(
                    f"Instance {instance_id} is still within the 14-day visibility period."
                )
                continue
                
            send_notifications_times = get_latest_notification_date(tag, app)
            if not send_notifications_times:
                continue

            if max(send_notifications_times)+ timedelta(days=14) > datetime.now(timezone.utc):
                continue

            org_number = (
                data.get("Prefill")
                    .get("AnsvarligVirksomhet")
                    .get("Organisasjonsnummer")
            )
            dato = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            logging.info(
                    f"Instance {instance_id} is created by the same user as last changed. Instance not answered."
                )
            file = {
                    "org_number": org_number,
                    "digitaliseringstiltak_report_id": tag[0],
                    "dato": dato,
                    "app_name": app,
                    "prefill_data": data,
                }
            send_warning(**file)
            sent_reminders.append({
                    "org_number": org_number,
                    "party_id": partyID,
                    "instance_id": instance_id,
                    "org_name":data.get("Prefill").get("AnsvarligVirksomhet").get("Navn"),
                    "digitaliseringstiltak_report_id": tag[0],
                    "dato": dato,
                    "app_name": app,
                })

    if sent_reminders:
        status_code = 201
    else:
        status_code = 200
    return sent_reminders, status_code