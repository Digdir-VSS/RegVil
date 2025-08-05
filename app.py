from flask import Flask, request
import logging

from get_initiell_skjema import run as download_skjema
from upload_single_skjema import run as upload_skjema
from send_warning import run as send_notification
import sys
logging.basicConfig(
    level=logging.DEBUG,  # Or INFO, WARNING, ERROR, depending on what you want
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

app = Flask(__name__)

def extract_ids_from_source(source_url: str):
    parts = source_url.split("/")
    return parts[-1], parts[-2], parts[-4]  # instance_id, party_id, app-name


@app.route("/httppost", methods=["POST"])
def handle_event():
    try:
        event = request.get_json()
        print(f"Received event: {event}")
        logging.info(f"Event type: {event.get('type')}")
        source_url = event.get("source")
        if event.get("type") == "app.instance.process.completed":

            instance_id, party_id, app_name = extract_ids_from_source(source_url)
            logging.info(
                f"Party ID: {party_id}, Instance ID: {instance_id}, App name: {app_name}"
            )
            ## IF CLOUD EVENT
            download_params, download_response = download_skjema(party_id=party_id, instance_id=instance_id, app_name=app_name)
            if not download_params:
                logging.error(f"Download failed for app name: {app_name} party id: {party_id} instance id: {instance_id}.")
                print(f"Download failed for app name: {app_name} party id: {party_id} instance id: {instance_id}.")
                return f"Download failed for app name: {app_name} party id: {party_id} instance id: {instance_id},", download_response
            
            if app_name == "regvil-2025-slutt":
                logging.info(f"Terminal app reached: {app_name}. No further processing.")
                print(f"Terminal app reached: {app_name}. No further processing.")
                return "Workflow complete – no further action.", 200

            result = upload_skjema(**download_params)
            if result == 200:
                notification_results = send_notification(**download_params)
                if notification_results == 200:
                    logging.info(f"Notification sent successfully for app name: {app_name} party id: {party_id} instance id: {instance_id}.")
                    print(f"Notification sent successfully for app name: {app_name} party id: {party_id} instance id: {instance_id}.")
                    return "Event received and processed. Notification sent", 200
                else:
                    logging.error(f"Notification failed for app name: {app_name} party id: {party_id} instance id: {instance_id}. Status code: {notification_results}")
                    print(f"Notification failed for app name: {app_name} party id: {party_id} instance id: {instance_id}. Status code: {notification_results}")
                    return "Event received and processed. Notification failed", 200
            else:
                return "Error in processing", result
            
        else:
            logging.info("Event type not handled.")
            return "Event type not handled", 204  
    except Exception as e:
        logging.error(f"Error: {e}")
        return f"Internal Server Error: {str(e)}", 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80, debug=True)
