from flask import Flask, request
import logging
import azure.functions as func

from get_initiell_skjema import run as download_skjema
from upload_single_skjema import run as upload_skjema

app = Flask(__name__)

def extract_ids_from_source(source_url: str):
    parts = source_url.split("/")
    return parts[-1], parts[-2], parts[-4]  # instance_id, party_id, app-name


@app.route("/httppost", methods=["POST"])
def handle_event():
    try:
        event = request.get_json()
        logging.info(f"Event type: {event.get('type')}")
        source_url = event.get("source")

        instance_id, party_id, app_name = extract_ids_from_source(source_url)
        logging.info(
            f"Party ID: {party_id}, Instance ID: {instance_id}, App name: {app_name}"
        )
        ## IF CLOUD EVENT
        download_params, download_response = download_skjema(party_id=party_id, instance_id=instance_id, app_name=app_name)
        if not download_params:
            logging.error(f"Download failed or skipped for app name: {app_name} party id: {party_id} instance id: {instance_id}. Skipping download.")
            return download_response
        
        if app_name == "regvil-2025-slutt":
            logging.info(f"Terminal app reached: {app_name}. No further processing.")
            return "Workflow complete – no further action.", 200

        result = upload_skjema(**download_params)
        return result
        
    except Exception as e:
        logging.error(f"Error: {e}")
        return f"Internal Server Error: {str(e)}", 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
