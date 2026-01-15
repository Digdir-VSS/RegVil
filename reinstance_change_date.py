import os 
from pathlib import Path
from datetime import datetime
import pytz
import pandas as pd
import numpy as np
import json

from clients.varsling_client import AltinnVarslingClient
from clients.instance_client import AltinnInstanceClient, get_meta_data_info
from config.config_loader import load_full_config

from get_initiell_skjema import run as download_skjema
from upload_single_skjema import run as upload_skjema
from send_warning import run as send_notification

def delete(regvil_instance_client: AltinnInstanceClient, partyID: str, instance_id: str):
    print(f"Deleting instance {instance_id} for party {partyID}")
    instance = regvil_instance_client.get_instance(partyID, instance_id)
    instance_meta = instance.json()
    instance_data = instance_meta.get("data")
    dataguid = get_meta_data_info(instance_data).get("id")
    tag = get_meta_data_info(instance_data).get("tags")
    deleted = None
    if tag:
        tag_response = regvil_instance_client.delete_tag(partyID, instance_id, dataguid, tag[0])
        print(tag_response.status_code)
    instance_deleted = regvil_instance_client.delete_instance(partyID, instance_id)
    if instance_deleted.status_code in [200,201,204]:
        print(f"Successfully deleted instance {instance_id}")
        deleted = instance_deleted.status_code
    else:
        print(f"Failed to delete instance {instance_id}: {instance_deleted.text}")
        deleted = instance_deleted.text
    return {"deleted": deleted}

def cancel_notification(varlsing_client: AltinnVarslingClient, notification_id: str):
    response = varlsing_client.cancel_notification(notificantion_id=notification_id)
    notification_cancelled = None
    if response.status_code == 200:
        print(f"Successfully cancelled notification!")
        notification_cancelled = response.status_code
    else:
        print(f"Notification not cancelled!")
        notification_cancelled = response.text
    return {"notification_cancelled": notification_cancelled}
     

def reinstate(instance_id, party_id, app_name, isVisible, email_subject, email_body):
        print(
                f"APP:Party ID: {party_id}, Instance ID: {instance_id}, App name: {app_name}"
            )
        reinstance = {}
        download_params, download_response = download_skjema(
                party_id=party_id, instance_id=instance_id, app_name=app_name
            )
        if not download_params:
            print(
                    f"APP:Download failed for app name: {app_name} party id: {party_id} instance id: {instance_id}."
                )
            reinstance["instance_downloaded"] = download_response.text
            reinstance["instance_downloaded_status_code"] = download_response.status_code
        download_params["dato"] = isVisible
        download_params["app_name"] = app_name

        result = upload_skjema(**download_params)
        download_params["email_subject"] = email_subject
        download_params["email_body"] = email_body
        reinstance["notification_send"] = None
        if result == 200:
                notification_results = send_notification(**download_params)
                reinstance["notification_send"] = notification_results
                if notification_results == 200:
                    print(
                        f"APP:Notification sent successfully for app name: {app_name} party id: {party_id} instance id: {instance_id}."
                    )
                    reinstance = {"app name": {app_name}, "party id": {party_id}, "instance_id": {instance_id}, "success": "success"}
                else:
                    print(
                        f"APP:Notification failed for app name: {app_name} party id: {party_id} instance id: {instance_id}. Status code: {notification_results}"
                    )
                    reinstance = {"app name": {app_name}, "party id": {party_id}, "instance_id": {instance_id}, "success": str(notification_results)}
        else:
            print("Error in processing", result)
        
        return reinstance
        

def main():
    path_to_config_folder = Path(__file__).parent / "config_files"
    path_to_instance_info = Path(__file__).parent / "data" / "reinstansiering_wrong_here.csv"
    path_to_logging = Path(__file__).parent / "data" 
    instances = pd.read_csv(path_to_instance_info,  sep=";", engine="python")
    instances = instances.replace(np.nan, None)
    for instance in instances.to_dict(orient="records"):
        app_name = "regvil-2025-status"
        partyID = instance["instancePartyId"] #input("Please enter the Party Id: ")
        instance_id = instance["instanceId"] #input("Please enter a specific instance Id: ")
        notification_id = instance["shipmentId"] #input("Please enter a specific notification Id: ")
        digitaliseringstiltak_report_id = instance["digitaliseringstiltak_report_id"]
        log_entry = {
            "party_id": partyID,
            "digitaliseringstiltak_report_id": digitaliseringstiltak_report_id,
            "instance_id": instance_id,
            "notification_id": notification_id,
            "app_name": app_name,
            "timestamp": datetime.now(tz=pytz.UTC).isoformat()
        }
            
        config = load_full_config(path_to_config_folder, app_name, os.getenv("ENV"))
        regvil_instance_client = AltinnInstanceClient.init_from_config(
                config,
            )
        
        regvil_varsling_client = AltinnVarslingClient.init_from_config(
                config,
            )
        dt = datetime(2026, 4, 14, 0, 0, 0, tzinfo=pytz.UTC)
        VisibleAfter = dt.isoformat().replace('+00:00', 'Z')
        print(f"Reinstansiere: partyID {partyID}/ isntanceID {instance_id} to data {VisibleAfter}")

        logging_reinstance = reinstate(instance_id, partyID, app_name, VisibleAfter, email_subject=config.app_config.emailSubject, email_body=config.app_config.emailBody)
        if logging_reinstance:
            log_entry["reinstance"] = logging_reinstance

        logging_deleted = delete(regvil_instance_client, partyID, instance_id)
        if logging_deleted:
            log_entry["deletion"] = logging_deleted

        if notification_id:
            logging_notification = cancel_notification(regvil_varsling_client, notification_id)
            if logging_notification:
                log_entry["cancel_notification"] = logging_notification
        safe_instance_id = instance_id.replace("/", "_")
        log_file = path_to_logging / f"{partyID}__{safe_instance_id}.json"

        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(log_entry, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
     main()