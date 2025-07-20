from flask import Flask, request, jsonify
import subprocess
import os
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

def extract_ids_from_source(source_url: str):
    parts = source_url.split("/")
    return parts[-1], parts[-2]  # instance_id, party_id

@app.route("/httppost", methods=["POST"])
def handle_event():
    try:
        event = request.get_json()
        logging.info(f"Event type: {event.get('type')}")
        source_url = event.get("source")

        instance_id, party_id = extract_ids_from_source(source_url)
        logging.info(f"Party ID: {party_id}, Instance ID: {instance_id}")
        return "Event received", 200

    except Exception as e:
        logging.error(f"Error: {e}")
        return f"Internal Server Error: {str(e)}", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)