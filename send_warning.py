from typing import Any, Dict
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential 
from pathlib import Path
import logging
from dotenv import load_dotenv
import os
import pytz
from config.type_dict_structure import DataModel
from clients.varsling_client import AltinnVarslingClient
from clients.instance_logging import InstanceTracker
from config.config_loader import load_full_config
from datetime import datetime, timezone, timedelta
from config.utils import parse_date
load_dotenv()

credential = DefaultAzureCredential()
client = SecretClient(
    vault_url=os.getenv("MASKINPORTEN_SECRET_VAULT_URL"), credential=credential
)
secret = client.get_secret(os.getenv("MASKINPORTEN_SECRET_NAME"))
secret_value = secret.value


def run(org_number: str, digitaliseringstiltak_report_id: str, dato: str, app_name: str, prefill_data: DataModel) -> str:
    logging.info("NOTIFICATION:Starting sending notifications for {app_name}")
    path_to_config_folder = Path(__file__).parent / "config_files"
    config = load_full_config(path_to_config_folder, app_name, os.getenv("ENV"))

    varsling_client = AltinnVarslingClient.init_from_config(config)
    recipient_email = prefill_data.get("Prefill").get("Kontaktperson").get("EPostadresse")
    org_name = prefill_data.get("Prefill").get("AnsvarligVirksomhet").get("Navn")  
    email_subject = config.app_config.emailSubject
    email_body = config.app_config.emailBody
    naive_dt = parse_date(dato)
    # naive_dt = datetime.strptime(dato, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    send_time = naive_dt.replace(tzinfo=timezone.utc)
    
    # send_time = datetime.fromisoformat(dato)
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
        appname=app_name
        )
    if not response:
        logging.error(f"NOTIFICATION:Failed to send notification to {org_number} {digitaliseringstiltak_report_id} {app_name}")
        return 500
    if response.status_code != 201:
        logging.error(f"NOTIFICATION:Failed to notify org number: {org_number} report_id: {digitaliseringstiltak_report_id} appname: {app_name}. Status: {response.text}")
        return response.status_code

    if response.status_code == 201:
        response_data = response.json()
        shipment_id = response_data["notification"]["shipmentId"]
        tracker = InstanceTracker.from_directory(f"{os.getenv('ENV')}/varsling/")
        tracker.logging_varlsing(org_number=org_number, org_name=org_name,app_name=app_name, send_time=send_time, digitaliseringstiltak_report_id=digitaliseringstiltak_report_id, shipment_id=shipment_id, recipientEmail=recipient_email, event_type="Varsling1Send")
        logging.info(f"NOTIFICATION:Notification sent successfully to {org_number} {digitaliseringstiltak_report_id} with shipment ID: {shipment_id}")
        return 200
    else:
        logging.warning(f"NOTIFICATION:Failed to notify org number: {org_number} report_id: {digitaliseringstiltak_report_id} appname: {app_name}")
        print(f"NOTIFICATION:Failed to notify org number: {org_number} report_id: {digitaliseringstiltak_report_id} appname: {app_name}")
        return 206
    
        