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
from config.config_loader import load_full_config
from config.utils import read_blob

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


def main() -> None:
    logging.info("Starting Altinn survey sending instance processing")
    path_to_config_folder = Path(__file__).parent / "config_files"
    config = load_full_config(path_to_config_folder, "regvil-2025-initiell", os.getenv("ENV"))
    test_prefill_data = read_blob(f"{os.getenv("ENV")}/test_virksomheter_prefill_with_uuid.json")

    regvil_instance_client = AltinnInstanceClient.init_from_config(
        config,
    )
    tracker = InstanceTracker.from_directory(f"{os.getenv("ENV")}/event_log/")
    logging.info(f"Processing {len(test_prefill_data)} organizations")


    for prefill_data_row in test_prefill_data:
        config.app_config.validate_prefill_data(prefill_data_row)
        data_model = config.app_config.get_prefill_data(prefill_data_row)
        org_number = prefill_data_row["AnsvarligVirksomhet.Organisasjonsnummer"]
        report_id = prefill_data_row["digitaliseringstiltak_report_id"]

        logging.info(f"Processing org {org_number}, report {report_id}")

        if regvil_instance_client.instance_created(
            org_number, config.app_config.tag["tag_instance"]
        ):
            logging.info(
                f"Skipping org {org_number} and report {report_id}- already in storage"
            )
            continue

        logging.info(
            f"Creating new instance for org {org_number} and report id {report_id}"
        )
        instance_data = {
            "appId": f"digdir/{config.app_config.app_name}",
            "instanceOwner": {
                "personNumber": None,
                "organisationNumber": data_model["Prefill"]["AnsvarligVirksomhet"][
                    "Organisasjonsnummer"
                ],
            },
            "dueBefore": config.app_config.dueBefore,
            "visibleAfter": config.app_config.visibleAfter,
        }


        files = {
            "instance": (
                "instance.json",
                json.dumps(instance_data, ensure_ascii=False),
                "application/json",
            ),
            "DataModel": (
                "datamodel.json",
                json.dumps(data_model, ensure_ascii=False),
                "application/json",
            ),
        }

        created_instance = regvil_instance_client.post_new_instance(files)

        if created_instance.status_code == 201:
            instance_meta_data = created_instance.json()
            instance_client_data_meta_data = get_meta_data_info(
                instance_meta_data["data"]
            )

            logging.info(
                f"Successfully created instance for org nr {org_number}/ report id {report_id}: {instance_meta_data['id']}"
            )
            party_id, instance_id = instance_meta_data.get("id").split("/")  # Extract instance ID and party ID from json
            #New code to handle instance data
            instance_data = regvil_instance_client.get_instance_data(
                party_id,
                instance_id,
                instance_client_data_meta_data.get('id')
            )
            if instance_data.status_code != 200:
                logging.error(
                    f"Failed to retrieve instance data for org nr {org_number}/ report id {report_id}: {instance_data.status_code}"
                )
                
            instance_data_file = instance_data.json()
            # Log the instance creation & save it
            tracker.logging_instance(
                instance_id,
                prefill_data_row["AnsvarligVirksomhet.Organisasjonsnummer"],
                prefill_data_row["digitaliseringstiltak_report_id"],
                instance_meta_data,
                instance_data_file,
                config.app_config.tag["tag_instance"],
            )


            tag_result = regvil_instance_client.tag_instance_data(
                instance_meta_data["instanceOwner"]["partyId"],
                instance_meta_data["id"],
                instance_client_data_meta_data["id"],
                config.app_config.tag["tag_instance"],
            )
            if tag_result.status_code == 201:
                logging.info(f"Successfully tagged instance for org {org_number}")
            else:
                logging.error(f"Failed to tag instance for org {org_number}")

        else:
            logging.error(
                f"Failed to create instance for org nr {org_number}/ report id {report_id}: Status {created_instance.status_code}"
            )
            try:
                error_details = created_instance.json()
                error_msg = error_details.get("error", "Unknown error")
            except Exception:
                error_msg = created_instance.text or "No error details"

                logging.warning(
                    f"API Error: Org {prefill_data_row['AnsvarligVirksomhet.Organisasjonsnummer']}, "
                    f"Report {prefill_data_row['digitaliseringstiltak_report_id']} - "
                    f"Status: {created_instance.status_code} - "
                    f"Error message: {error_msg}"
                )


if __name__ == "__main__":
    main()