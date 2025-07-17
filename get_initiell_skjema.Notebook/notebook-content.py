# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "9fbcae95-6f3d-4f21-96dd-b0a98150a56d",
# META       "default_lakehouse_name": "RegVil_Lakehouse",
# META       "default_lakehouse_workspace_id": "a9ae54b0-c5c4-4737-aa47-73797fa29580",
# META       "known_lakehouses": [
# META         {
# META           "id": "9fbcae95-6f3d-4f21-96dd-b0a98150a56d"
# META         }
# META       ]
# META     },
# META     "environment": {
# META       "environmentId": "cfc485be-bcb5-412e-9356-f6b9743f7fd5",
# META       "workspaceId": "5cce3fd5-2dac-41a7-a0e4-acfd383bdb8f"
# META     }
# META   }
# META }

# PARAMETERS CELL ********************

instance_id = "392dd633-0997-486a-9832-f1593849684c"
party_id = "51531148"

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

%run instance_client

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

%run instance_logging

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

from typing import Dict
from notebookutils.mssparkutils.credentials import getSecret
from pathlib import Path
import logging
import json

def write_to_json(data: Dict[str, Any], path_to_folder: Path, filename: str) -> None:
    full_path = f"{path_to_folder.rstrip('/')}/{filename}"
    json_str = json.dumps(data, ensure_ascii=False, indent=4)
    mssparkutils.fs.put(full_path, json_str, overwrite=True)

secret_value = getSecret("https://keyvaultvss.vault.azure.net/", "rapdigtest")

log_filename = f"/lakehouse/default/Files/test/logs/processing_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def main(instance_id, party_id):
    path_to_initiell_skjema_storage = "file:/lakehouse/default/Files/test/returned_instances"
    maskinporten_client = json.loads(mssparkutils.fs.head("file:/lakehouse/default/Files/test/maskinporten_config.json"))
    test_config_client_file = json.loads(mssparkutils.fs.head("file:/lakehouse/default/Files/test/test_config_client_file.json"))
    maskinporten_endpoints = json.loads(mssparkutils.fs.head("file:/lakehouse/default/Files/test/maskinporten_endpoints.json"))
    test_prefill_data = json.loads(mssparkutils.fs.head("file:/lakehouse/default/Files/test/test_virksomheter_prefill_with_uuid.json"))

    maskinporten_endpoint = maskinporten_endpoints[test_config_client_file["environment"]]

    regvil_instance_client = AltinnInstanceClient.init_from_config(test_config_client_file, {"maskinport_client": maskinporten_client, "secret_value": secret_value, "maskinporten_endpoint": maskinporten_endpoint})
    tracker = InstanceTracker.from_log_file("file:/lakehouse/default/Files/test/instance_log/instance_log.json")

    list_initiell_skjema_created = tracker.get_events_from_log("initiell_skjema_instance_created")
    pending_instance = find_event_by_instance(tracker.log_file, instance_id, "initiell_skjema_instance_created")
    instance_meta = regvil_instance_client.get_instance(pending_instance["instancePartyId"], pending_instance["instanceId"])

    if not instance_meta:
        logger.warning(f"No instance metadata returned for {pending_instance['instanceId']}")

    try:
        instance_meta_info = instance_meta.json()
        meta_data = get_meta_data_info(instance_meta_info["data"])
        tags = meta_data["tags"]

        if tags == ["InitiellSkjemaLevert"] and meta_data["lastChangedBy"] != meta_data["createdBy"]:
            instance_data = regvil_instance_client.get_instance_data(
                    pending_instance["instancePartyId"],
                    pending_instance["instanceId"],
                    pending_instance["data_info"]["dataGuid"]
                )

            data_to_storage = {
                    "meta_info": {
                        "org_number": pending_instance["org_number"],
                        "instancePartyId": pending_instance["instancePartyId"],
                        "instanceId": pending_instance["instanceId"],
                        "dataGuid": pending_instance["data_info"]["dataGuid"],
                        "digitaliseringstiltak_report_id": pending_instance["digitaliseringstiltak_report_id"]
                    },
                    "data": instance_data.json()
                }

            party_id, instance_id = pending_instance['instanceId'].split("/")
            filename = f"initiellskjema_{pending_instance['org_number']}_{pending_instance['digitaliseringstiltak_report_id']}_{party_id}_{instance_id}.json"
            write_to_json(data_to_storage, path_to_initiell_skjema_storage, filename)

            response = regvil_instance_client.tag_instance_data(
                    pending_instance["instancePartyId"],
                    pending_instance["instanceId"],
                    pending_instance["data_info"]["dataGuid"],
                    "InitiellSkjemaDownloaded"
                )

            tracker.logging_instance(
                    pending_instance['org_number'],
                    pending_instance["digitaliseringstiltak_report_id"],
                    instance_meta_info,
                    "initiell_skjema_instance_downloaded"
                )
            tracker.save_to_disk()

            logger.info(f"Successfully downloaded and tagged: {filename} (HTTP {response.status_code})")

        else:
                logger.info(f"Already downloaded or invalid tags for: {pending_instance['digitaliseringstiltak_report_id']} - {pending_instance['instanceId']}")
    except Exception as e:
            logger.exception(f"Error processing instance {pending_instance['instanceId']}")
            raise


if __name__ == "__main__":
    main(instance_id, party_id)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
