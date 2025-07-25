from typing import Any
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential
from pathlib import Path
import json
import logging
from dotenv import load_dotenv
import os

from clients.instance_client import AltinnInstanceClient, get_meta_data_info
from clients.instance_logging import InstanceTracker
from config.type_dict_structure import DataModel
from config.config_loader import load_full_config

load_dotenv()

credential = DefaultAzureCredential()
client = SecretClient(
    vault_url=os.getenv("MASKINPORTEN_SECRET_VAULT_URL"), credential=credential
)
secret = client.get_secret(os.getenv("MASKINPORTEN_SECRET_NAME"))
secret_value = secret.value


def load_in_json(path_to_json_file: Path) -> Any:
    with open(path_to_json_file, "r", encoding="utf-8") as file:
        return json.load(file)


def run(org_number: str, report_id: str, dato: str, app_name: str, prefill_data: DataModel) -> None:
    
    logging.info("Starting Altinn survey sending instance processing")
    path_to_config_folder = Path(__file__).parent / "config_files"
    app_config = load_full_config(path_to_config_folder, app_name, os.getenv("ENV"))

    regvil_instance_client = AltinnInstanceClient.init_from_config(
        app_config,
    )

    tracker = InstanceTracker.from_log_file(
        Path(__file__).parent / "data"  /os.getenv("ENV")/ "instance_log" / "instance_log.json"
    )

    logging.info(f"Processing org {org_number}, report {report_id}")

    if regvil_instance_client.instance_created(
        org_number, app_config.app_config.tag["tag_instance"]
        ):
        logging.info(
                f"Skipping org {org_number} and report {report_id}- already in storage"
            )

    logging.info(
            f"Creating new instance for org {org_number} and report id {report_id}"
        )
    instance_data = {
            "appId": f"digdir/{app_config.app_config.app_name}",
            "instanceOwner": {
                "personNumber": None,
                "organisationNumber": org_number,
            },
            "dueBefore": dato,
            "visibleAfter": None,
        }

    files = {
            "instance": (
                "instance.json",
                json.dumps(instance_data, ensure_ascii=False),
                "application/json",
            ),
            "DataModel": (
                "datamodel.json",
                json.dumps(prefill_data, ensure_ascii=False),
                "application/json",
            ),
        }

    created_instance = regvil_instance_client.post_new_instance(files)

    if created_instance.status_code == 201:
        instance_meta_data = created_instance.json()
        instance_data_meta_data = get_meta_data_info(
                instance_meta_data.get("data")
            )

        logging.info(
                f"Successfully created instance for org nr {org_number}/ report id {report_id}: {instance_meta_data['id']}"
            )
        tracker.logging_instance(
            org_number,
            report_id,
            created_instance.json(),
            app_config.app_config.tag["tag_instance"],
            )
        tracker.save_to_disk()
        tag_result = regvil_instance_client.tag_instance_data(
                instance_meta_data["instanceOwner"]["partyId"],
                instance_meta_data["id"],
                instance_data_meta_data["id"],
                app_config.app_config.tag["tag_instance"],
            )
        if tag_result.status_code == 201:
                logging.info(f"Successfully tagged instance for org number: {org_number} party id: {instance_meta_data['instanceOwner']['partyId']} instance id: {instance_meta_data['id']}")
        else:
                logging.warning(f"Failed to tag instance org number: {org_number} party id: {instance_meta_data['instanceOwner']['partyId']} instance id: {instance_meta_data['id']}")

    else:
        logging.warning(
                f"Failed to create instance for org nr {org_number}/ report id {report_id}: Status {created_instance.status_code}"
            )
        try:
            error_details = created_instance.json()
            error_msg = error_details.get("error", "Unknown error")

        except Exception:
            error_msg = created_instance.text or "No error details"

        logging.error(
                    f"API Error: Org {org_number}, "
                    f"Report {report_id} - "
                    f"Status: {created_instance.status_code} - "
                    f"Error message: {error_msg}"
                )