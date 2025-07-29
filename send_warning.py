from typing import Any, Dict
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential 
from pathlib import Path
import json
import logging
from dotenv import load_dotenv
import os

from clients.varsling_client import AltinnVarslingClient
from clients.instance_logging import InstanceTracker
from config.config_loader import load_full_config
import time
load_dotenv()

credential = DefaultAzureCredential()
client = SecretClient(
    vault_url=os.getenv("MASKINPORTEN_SECRET_VAULT_URL"), credential=credential
)
secret = client.get_secret(os.getenv("MASKINPORTEN_SECRET_NAME"))
secret_value = secret.value
env = os.getenv("ENV")
# def load_in_json(path_to_json_file: Path) -> Dict[str, Any]:
#     with open(path_to_json_file, 'r', encoding='utf-8') as file:
#         return json.load(file)

def run(app_name, env) -> None:
    logging.info("Starting Altinn survey sending instance processing")
    path_to_config_folder = Path(__file__).parent / "config_files"
    config = load_full_config(path_to_config_folder, app_name, env)
    
    varsling_client = AltinnVarslingClient.init_from_config(config)
    print(varsling_client.base_url,
        varsling_client.appname)
run(app_name="regvil-2025-initiell", env=os.getenv("ENV"))
#     response = varsling_client.send_notification(
#         recipient_email=recipient_email,
#         subject = email_subject,
#         body=email_body
#     )

#     if response.status_code == 201:
#         response_data = response.json()
#         shipment_id = response_data["notification"]["shipmentId"]
#         status = varsling_client.get_shipment_status(shipment_id)
#         print(shipment_id,"\n",status.json(),"\n",response_data)
#         # tracker = InstanceTracker.from_directory(f"{os.getenv("ENV")}/varsling/")
#         # tracker.logging_varlsing(org_number="311045407", org_name="TestVirksomhet", digitaliseringstiltak_report_id="abc-def-ghi-jkl-mno-pqr", shipment_id=shipment_id, recipientEmail=recipient_email, event_type="Varsling1Send")

# recipient_email = "ignacio.cuervo.torre@digdir.no"
# email_subject = "Test Varsling"
# email_body = "This is a test email for Altinn Varsling."
# org_nummer = "311045407"
# digitaliseringstiltak_report_id = "abc-def-ghi-jkl-mno-pqr"
# app_name = "regvil-2025-initiell"

# "org_number": instance_meta_info["instanceOwner"]["organisationNumber"], 
# "digitaliseringstiltak_report_id": digitaliseringstiltak_report_id ,
# "dato": config.app_config.get_date(report_data), 
# "app_name": config.workflow_dag.get_next(app_name), 
# "prefill_data": report_data
# run(recipient_email,email_subject, email_body)