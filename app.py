from flask import Flask, request
import json
from azure.storage.blob import BlobServiceClient
from azure.identity import DefaultAzureCredential, EnvironmentCredential
import logging
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

def extract_ids_from_source(source_url: str):
    parts = source_url.split("/")
    return parts[-1], parts[-2]  # instance_id, party_id

@app.route("/httppost", methods=["POST"])
def handle_event():
    try:
        load_dotenv()

        if os.getenv("AZURE_CLIENT_ID"):
            print("Using EnvironmentCredential for local dev")
            credential = EnvironmentCredential()
        else:
            print("Using DefaultAzureCredential (includes managed identity in Azure)")
            credential = DefaultAzureCredential()

        event = request.get_json()
        logging.info(f"Event type: {event.get('type')}")
        source_url = event.get("source")
        instance_id, party_id = extract_ids_from_source(source_url)

        blob_service_client = BlobServiceClient(os.getenv('BLOB_STORAGE_ACCOUNT_URL'), credential=credential)
        container_client = blob_service_client.get_container_client("regvil-blob-container")
        blob_client = container_client.get_blob_client(f"{party_id}_{instance_id}.json")
        blob_client.upload_blob(json.dumps({"party_id": party_id, "instance_id": instance_id}),overwrite=True)
        logging.info("Data uploaded to blob")

        logging.info(f"Party ID: {party_id}, Instance ID: {instance_id}")
        return "Event received", 200

    except Exception as e:
        logging.error(f"Error: {e}")
        return f"Internal Server Error: {str(e)}", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)