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

INSTANCE_ID = "None"

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

%run exchange_token_funcs 

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

from typing import Any, Dict
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential 
from notebookutils.mssparkutils.credentials import getSecret
from pathlib import Path
import json
import os
import sys
import importlib
import importlib.util
import logging
import datetime as dt

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

def main():
    maskinporten_client = json.loads(mssparkutils.fs.head("file:/lakehouse/default/Files/test/maskinporten_config.json"))
    test_config_client_file = json.loads(mssparkutils.fs.head("file:/lakehouse/default/Files/test/test_config_client_file.json"))
    maskinporten_endpoints = json.loads(mssparkutils.fs.head("file:/lakehouse/default/Files/test/maskinporten_endpoints.json"))
    test_prefill_data = json.loads(mssparkutils.fs.head("file:/lakehouse/default/Files/test/test_virksomheter_prefill_with_uuid.json"))

    maskinporten_endpoint = maskinporten_endpoints[test_config_client_file["environment"]]

    regvil_instance_client = AltinnInstanceClient.init_from_config(test_config_client_file, {"maskinport_client": maskinporten_client, "secret_value": secret_value, "maskinporten_endpoint": maskinporten_endpoint})

    tracker = InstanceTracker.from_log_file("file:/lakehouse/default/Files/test/instance_log/instance_log.json")
    print(f"Processing {len(test_prefill_data)} organizations")

    for prefill_data_row in test_prefill_data[7:8]:
        validate_prefill_data(prefill_data_row)
        data_model = transform_flat_to_nested_with_prefill(prefill_data_row)
        org_number = prefill_data_row["AnsvarligVirksomhet.Organisasjonsnummer"]
        report_id = prefill_data_row["digitaliseringstiltak_report_id"]
        print(f"Processing org {org_number}, report {report_id}")

        if tracker.has_processed_instance(org_number, report_id, "initiell_skjema_instance_created"):
            logger.info(f"Skipping org {org_number} and report {report_id} - already in instance log")
            print(f"Skipping org {org_number} and report {report_id} - already in instance log")
            continue

        if regvil_instance_client.instance_created(org_number, test_config_client_file["tag"]):
            logger.info(f"Skipping org {org_number} and report {report_id}- already in storage")
            print(f"Skipping org {org_number} and report {report_id}- already in storage")
            continue
        
        print(f"Creating new instance for org {org_number} and report id {report_id}")

        instance_data = {"appId" : "digdir/regvil-2025-initiell",    
                "instanceOwner": {"personNumber": None,
                "organisationNumber": data_model["Prefill"]["AnsvarligVirksomhet"]["Organisasjonsnummer"]},
                "dueBefore":"2025-09-01T12:00:00Z",
                "visibleAfter": "2025-06-29T00:00:00Z"
        }
        files = {
                    'instance': ('instance.json', json.dumps(instance_data), 'application/json'),
                    'DataModel': ('datamodel.json', json.dumps(data_model), 'application/json')
        }

        created_instance = regvil_instance_client.post_new_instance(files) #add if 200 raise error then continue
        if not created_instance:
            continue 
        instance_meta_data = created_instance.json()

        instance_client_data_meta_data = get_meta_data_info(instance_meta_data["data"])

        if created_instance.status_code == 201:
                print(f"Successfully created instance for org nr {org_number}/ report id {report_id}: {instance_meta_data['id']}")
                logger.info(f"Successfully created instance for org nr {org_number}/ report id {report_id}: {instance_meta_data['id']}")
                tracker.logging_instance(prefill_data_row["AnsvarligVirksomhet.Organisasjonsnummer"], prefill_data_row["digitaliseringstiltak_report_id"], created_instance.json())
                tracker.save_to_disk()
                tag_result = regvil_instance_client.tag_instance_data(instance_meta_data["instanceOwner"]["partyId"], instance_meta_data["id"], instance_client_data_meta_data["id"], test_config_client_file["tag"])
                if tag_result.status_code == 201:
                    print(f"Successfully tagged instance for org {org_number}")
                else:
                    print(f"Failed to tag instance for org {org_number}")


        else:
                logger.error(f"Failed to create instance for org nr {org_number}/ report id {report_id}: Status {created_instance.status_code}")
                try:
                    error_details = created_instance.json()
                    error_msg = error_details.get('error', 'Unknown error')
                except:
                    error_msg = created_instance.text or 'No error details'
                    logger.warning(f"API Error: Org {prefill_data_row['AnsvarligVirksomhet.Organisasjonsnummer']}, "
                                    f"Report {prefill_data_row['digitaliseringstiltak_report_id']} - "
                                    f"Status: {created_instance.status_code} - "
                                    f"Error message: {error_msg}")
                

if __name__ == "__main__":
    main()


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
