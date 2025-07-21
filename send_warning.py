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

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename=Path(__file__).parent / "data" / "altinn_varsling_logging.log"
)
logger = logging.getLogger(__name__)

credential = DefaultAzureCredential()
client = SecretClient(
    vault_url=os.getenv("MASKINPORTEN_SECRET_VAULT_URL"), credential=credential
)
secret = client.get_secret(os.getenv("MASKINPORTEN_SECRET_NAME"))
secret_value = secret.value

def load_in_json(path_to_json_file: Path) -> Dict[str, Any]:
    with open(path_to_json_file, 'r', encoding='utf-8') as file:
        return json.load(file)

def main():
    maskinport_client = load_in_json(Path(__file__).parent / "data" / "maskinporten_config.json")
    maskinporten_endpoints = load_in_json(Path(__file__).parent / "data" / "maskinporten_endpoints.json")
    test_config_client_file = load_in_json(Path(__file__).parent / "data" / "test_config_client_file.json")
    maskinporten_endpoint = maskinporten_endpoints[test_config_client_file["environment"]]


    varsling_client = AltinnVarslingClient(
    base_url=test_config_client_file["base_varsling_url"],
    maskinport_client=maskinport_client,
    secret_value=secret_value,
    maskinporten_endpoint= maskinporten_endpoint
)
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
        print(tracker.log_changes)
        tracker.save_to_disk()

if __name__ == "__main__":
    main()