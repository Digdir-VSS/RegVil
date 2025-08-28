from typing import Any, Dict
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential 
from pathlib import Path
import json
import logging
from dotenv import load_dotenv
import os
import pytz
from clients.varsling_client import AltinnVarslingClient
from clients.instance_logging import InstanceTracker
from config.config_loader import load_full_config
from config.utils import read_blob
from datetime import datetime, timezone, timedelta
load_dotenv()

credential = DefaultAzureCredential()
client = SecretClient(
    vault_url=os.getenv("MASKINPORTEN_SECRET_VAULT_URL"), credential=credential
)
secret = client.get_secret(os.getenv("MASKINPORTEN_SECRET_NAME"))
secret_value = secret.value
env = os.getenv("ENV")

def main():
    logging.info("NOTIFICATION:Starting sending notifications for regvil-2025-initiell")
    path_to_config_folder = Path(__file__).parent / "config_files"
    config = load_full_config(path_to_config_folder, "regvil-2025-initiell", env)


    varsling_client = AltinnVarslingClient.init_from_config(config)
    test_prefill_data = read_blob(f"{env}/virksomheter_prefill_with_uuid.json")
    
    for prefill_data_row in test_prefill_data:
        config.app_config.validate_prefill_data(prefill_data_row)
        recipient_email = prefill_data_row["Kontaktperson.EPostadresse"]
        org_number = prefill_data_row["AnsvarligVirksomhet.Organisasjonsnummer"]
        report_id = prefill_data_row["digitaliseringstiltak_report_id"]
        email_subject = config.app_config.emailSubject
        email_body = config.app_config.emailBody
        send_time = datetime.fromisoformat(config.app_config.visibleAfter)
        if send_time < datetime.now(pytz.UTC):
            now = datetime.now(pytz.UTC).isoformat(timespec="microseconds")        
            dt = datetime.fromisoformat(now)
            send_time = dt + timedelta(minutes=1)
        send_time = send_time.isoformat(timespec="microseconds").replace("+00:00", "Z")
        response = varsling_client.send_notification(
        recipient_email=recipient_email,
        subject = email_subject,
        body=email_body,
        send_time=send_time,
        appname=config.app_config.app_name
        )
        if not response:
            logging.error(f"NOTIFICATION:Failed to send notification to {recipient_email} for org number {org_number} and report ID {report_id}")
            continue
        if response.status_code != 201:
            logging.error(f"NOTIFICATION:Failed to send notification to {recipient_email} for org number {org_number} and report ID {report_id}. Status code: {response.text}")
            continue
        if response.status_code == 201:
            response_data = response.json()
            shipment_id = response_data["notification"]["shipmentId"]
            tracker = InstanceTracker.from_directory(f"{os.getenv('ENV')}/varsling/")
            tracker.logging_varlsing(
                org_number=org_number,
                org_name=prefill_data_row["AnsvarligVirksomhet.Navn"],
                app_name=config.app_config.app_name,
                send_time = send_time,
                digitaliseringstiltak_report_id=report_id,
                shipment_id=shipment_id,
                recipientEmail=recipient_email,
                event_type="Varsling1Send"
            ) 
            logging.info(f"NOTIFICATION:Notification sent successfully to {org_number} {report_id} with shipment ID: {shipment_id}")
        else:
            logging.warning(f"NOTIFICATION:Failed to notify org number: {org_number} report_id: {report_id} appname: {config.app_config.app_name}")
            print(f"NOTIFICATION:Failed to notify org number: {org_number} report_id: {report_id} appname: {config.app_config.app_name}")
    logging.info(f"NOTIFICATION:Successfully send out all notifications")


if __name__ == "__main__":
    main()
