from config.utils import connect_blob, chech_file_exists, read_blob
from dotenv import load_dotenv
import os
from config.config_loader import load_full_config
from clients.varsling_client import AltinnVarslingClient
from clients.instance_logging import InstanceTracker
import logging
from pathlib import Path
load_dotenv()

def main():
    connection = connect_blob()
    directory = f"{os.getenv('ENV')}/varsling/"
    send_blobs = connection.list_blobs(name_starts_with=directory)
    for blob in send_blobs:
        name = blob.name
        if "_Varsling1Send_" not in name:
            continue

        # Extract parts
        base = os.path.splitext(name)[0]
        parts = base.split('_')
        if len(parts) < 4:
            continue

        report_id = parts[0]
        app_name = parts[1]
        shipment_id = parts[3]
        
        # Construct the expected 'Recieved' filename
        recieved_blob_name = f"{report_id}_{app_name}_Varsling1Recieved_{shipment_id}.json"

        # Check if the Recieved file already exists

        if not chech_file_exists(recieved_blob_name):
            path_to_config_folder = Path(__file__).parent / "config_files"
            config = load_full_config(path_to_config_folder, app_name, os.getenv("ENV"))

            varsling_client = AltinnVarslingClient.init_from_config(config)
            response = varsling_client.get_shipment_status(shipment_id=shipment_id)
            if not response:
                logging.error(f"Failed to get shipment status for {shipment_id} and {report_id[len(directory):]}")
                continue
            if response.status_code != 200:
                logging.error(f"Failed to get shipment status for {shipment_id}: {response.text}")
                continue    
            if response.json().get("status") == "Order_Completed":
                sent_blob_name = f"{report_id}_{app_name}_Varsling1Send_{shipment_id}.json"
                sent_blob = read_blob(sent_blob_name)
                org_name = sent_blob.get("org_name")
                org_number = sent_blob.get("org_number")
                send_time = sent_blob.get("send_time")
                recipient_email = sent_blob.get("recipientEmail")
                tracker = InstanceTracker.from_directory(f"{os.getenv('ENV')}/varsling/")
                tracker.logging_varlsing(
                    org_number=org_number,
                    org_name=org_name,
                    app_name=app_name,
                    send_time=send_time,
                    digitaliseringstiltak_report_id=report_id[len(directory):],
                    shipment_id=shipment_id,
                    recipientEmail=recipient_email,
                    event_type="Varsling1Recieved",
                    shipment_status= response.json()
                )
                if response.json().get("recipients")[0].get("status")== "Email_Delivered":
                    logging.info(f"Marked as received: {recieved_blob_name}")
                    print(f"Marked as received: {recieved_blob_name}")
                else:
                    logging.warning(f"Shipment {shipment_id} not delivered to {recipient_email}. Status: {response.json().get("recipients")[0].get("status")}")
                    print(f"Shipment {shipment_id} not delivered to {recipient_email}. Status: {response.json().get("recipients")[0].get("status")}")



if __name__ == "__main__":
    main()

