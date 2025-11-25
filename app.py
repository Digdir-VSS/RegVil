from flask import Flask, request, jsonify
import logging
import os
from dotenv import load_dotenv

from get_initiell_skjema import run as download_skjema
from upload_single_skjema import run as upload_skjema
from send_warning import run as send_notification
from send_reminders import run as run_reminder_job
from send_seasonal_reminders import run as run_seasonal_reminder_job

load_dotenv()

app = Flask(__name__)


def extract_ids_from_source(source_url: str):
    parts = source_url.split("/")
    return parts[-1], parts[-2], parts[-4]  # instance_id, party_id, app-name

@app.route("/health")
def health():
    return "ok", 200

@app.route("/httppost", methods=["POST"])
def handle_event():
    try:
        event = request.get_json()
        logging.info(f"APP:Event type: {event.get('type')}")
        source_url = event.get("source")
        if event.get("type") == "app.instance.process.completed":

            instance_id, party_id, app_name = extract_ids_from_source(source_url)
            logging.info(
                f"APP:Party ID: {party_id}, Instance ID: {instance_id}, App name: {app_name}"
            )
            ## IF CLOUD EVENT
            download_params, download_response = download_skjema(
                party_id=party_id, instance_id=instance_id, app_name=app_name
            )
            if not download_params:
                logging.error(
                    f"APP:Download failed for app name: {app_name} party id: {party_id} instance id: {instance_id}."
                )
                return (
                    f"APP:Download failed for app name: {app_name} party id: {party_id} instance id: {instance_id},",
                    download_response,
                )

            if app_name == "regvil-2025-slutt":
                logging.info(
                    f"APP:Terminal app reached: {app_name}. No further processing."
                )
                return "Workflow complete - no further action.", 200

            result = upload_skjema(**download_params)
            if result == 200:
                notification_results = send_notification(**download_params)
                if notification_results == 200:
                    logging.info(
                        f"APP:Notification sent successfully for app name: {app_name} party id: {party_id} instance id: {instance_id}."
                    )
                    return "Event received and processed. Notification sent", 200
                else:
                    logging.error(
                        f"APP:Notification failed for app name: {app_name} party id: {party_id} instance id: {instance_id}. Status code: {notification_results}"
                    )

                    return "Event received and processed. Notification failed", 200
            else:
                return "Error in processing", result
        else:
            logging.info("APP:Event type not handled.")
            return "Event type not handled", 204
    except Exception as e:
        logging.error(f"APP:Error: {e}")
        return f"Internal Server Error: {str(e)}", 500


@app.route("/send_reminder", methods=["POST"])
def send_reminder():
    try:
        api_key = request.headers.get("X-Api-Key")
        if api_key != os.getenv("REMINDER_API_KEY"):
            return jsonify({"status": "unauthorized", "reminders": []}), 401
        result, status_code = run_reminder_job()
        return jsonify({"status": "success", "reminders": result}), str(status_code)

    except Exception as e:
        logging.exception("APP:Error while processing send_reminder request")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/send_seasonal_reminder", methods=["POST"])
def send_seasonal_reminder():
    try:
        api_key = request.headers.get("X-Api-Key")
        email_subject = request.headers.get("subject")
        email_body = request.headers.get("email")
        if api_key != os.getenv("REMINDER_API_KEY"):
            return jsonify({"status": "unauthorized", "reminders": []}), 401
        result, status_code = run_seasonal_reminder_job(email_subject, email_body)
        return jsonify({"status": "success", "reminders": result}), str(status_code)

    except Exception as e:
        logging.exception("APP:Error while processing send_reminder request")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
