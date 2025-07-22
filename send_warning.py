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

load_dotenv()

credential = DefaultAzureCredential()
client = SecretClient(
    vault_url=os.getenv("MASKINPORTEN_SECRET_VAULT_URL"), credential=credential
)
secret = client.get_secret(os.getenv("MASKINPORTEN_SECRET_NAME"))
secret_value = secret.value

def load_in_json(path_to_json_file: Path) -> Dict[str, Any]:
    with open(path_to_json_file, 'r', encoding='utf-8') as file:
        return json.load(file)

def main() -> None:
    logging.info("Starting Altinn survey sending instance processing")
    path_to_config_folder = Path(__file__).parent / "config_files"
    config = load_full_config(path_to_config_folder, "regvil-2025-initiell", "test")


    varsling_client = AltinnVarslingClient.init_from_config(config)
    recipient_email = "matthias.boeker@digdir.no"
    response = varsling_client.send_notification(
        recipient_email="matthias.boeker@digdir.no",
        subject="Test Varsling Email",
        body="Hello, this is a test varsling from our integration."
    )

    if response.status_code == 201:
        response_data = response.json()
        shipment_id = response_data["notification"]["shipmentId"]
        status = varsling_client.get_shipment_status(shipment_id)
        tracker = InstanceTracker.from_log_file(Path(__file__).parent / "data" / "instance_log" / "instance_log.json")
        tracker.logging_varlsing(org_number="311045407", org_name="TestVirksomhet", digitaliseringstiltak_report_id="abc-def-ghi-jkl-mno-pqr", shipment_id=status.json(), recipientEmail=recipient_email, event_type="Varsling1Send")
        tracker.save_to_disk()

if __name__ == "__main__":
    main()