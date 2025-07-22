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
    config = load_full_config(path_to_config_folder, "regvil-2025-initiell", "test")
    test_prefill_data = load_in_json(
        Path(__file__).parent / "data" / "test_virksomheter_prefill_with_uuid.json"
    )

    regvil_instance_client = AltinnInstanceClient.init_from_config(
        config,
    )

    tracker = InstanceTracker.from_log_file(
        Path(__file__).parent / "data" / "instance_log" / "instance_log.json"
    )
    logging.info(f"Processing {len(test_prefill_data)} organizations")

    for prefill_data_row in test_prefill_data:
        config.app_config.validate_prefill_data(prefill_data_row)
        data_model = config.app_config.get_prefill_data(prefill_data_row)
        org_number = prefill_data_row["AnsvarligVirksomhet.Organisasjonsnummer"]
        report_id = prefill_data_row["digitaliseringstiltak_report_id"]

        logging.info(f"Processing org {org_number}, report {report_id}")

        if tracker.has_processed_instance(org_number, report_id):
            logging.info(
                f"Skipping org {org_number} and report {report_id} - already in instance log"
            )
            continue
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
            tracker.logging_instance(
                prefill_data_row["AnsvarligVirksomhet.Organisasjonsnummer"],
                prefill_data_row["digitaliseringstiltak_report_id"],
                created_instance.json(),
                "initiell_skjema_instance_created",
            )
            tracker.save_to_disk()
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