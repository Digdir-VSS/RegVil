import os 
from pathlib import Path
from datetime import datetime
import pytz


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
    if tag:
        tag_response = regvil_instance_client.delete_tag(partyID, instance_id, dataguid, tag[0])
        print(tag_response.status_code)
    instance_deleted = regvil_instance_client.delete_instance(partyID, instance_id)
    if instance_deleted.status_code in [200,201,204]:
        print(f"Successfully deleted instance {instance_id}")
    else:
        print(f"Failed to delete instance {instance_id}: {instance_deleted.text}")

def cancel_notification(varlsing_client: AltinnVarslingClient, notification_id: str):
    response = varlsing_client.cancel_notification(notificantion_id=notification_id)
    if response == 200:
        print(f"Successfully cancelled notification!")

    else:
         
        print(f"Notification not cancelled!")
            
     

def reinstate(instance_id, party_id, app_name, isVisible):
        print(
                f"APP:Party ID: {party_id}, Instance ID: {instance_id}, App name: {app_name}"
            )

        download_params, download_response = download_skjema(
                party_id=party_id, instance_id=instance_id, app_name=app_name
            )
        if not download_params:
            print(
                    f"APP:Download failed for app name: {app_name} party id: {party_id} instance id: {instance_id}."
                )

        download_params["dato"] = isVisible
        download_params["app_name"] = app_name

        result = upload_skjema(**download_params)
        if result == 200:
                notification_results = send_notification(**download_params)

                if notification_results == 200:
                    print(
                        f"APP:Notification sent successfully for app name: {app_name} party id: {party_id} instance id: {instance_id}."
                    )
                else:
                    print(
                        f"APP:Notification failed for app name: {app_name} party id: {party_id} instance id: {instance_id}. Status code: {notification_results}"
                    )
        else:
            print("Error in processing", result)
        

def main():
    path_to_config_folder = Path(__file__).parent / "config_files"

    app_name = input("Enter the app name: [regvil-2025-initiell, regvil-2025-oppstart, regvil-2025-status, regvil-2025-slutt]  ")
    partyID = input("Please enter the Party Id: ")
    instance_id = input("Please enter a specific instance Id: ")
    notification_id = input("Please enter a specific notification Id: ")
    
    config = load_full_config(path_to_config_folder, app_name, os.getenv("ENV"))
    regvil_instance_client = AltinnInstanceClient.init_from_config(
        config,
    )
    regvil_varsling_client = AltinnVarslingClient.init_from_config(
        config,
    )
    VisibleAfter =  datetime.now(pytz.UTC).isoformat().replace('+00:00', 'Z') #, "visibleAfter": "2019-05-20T00:00:00Z" 
    reinstate(instance_id, partyID, app_name, VisibleAfter)
    delete(regvil_instance_client, partyID, instance_id)
    cancel_notification(regvil_varsling_client, notification_id)


if __name__ == "__main__":
     main()