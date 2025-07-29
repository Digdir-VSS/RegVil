from __future__ import annotations
import json
import uuid
import re
from typing import Optional, Dict, Any

from auth.exchange_token_funcs import exchange_token 
from clients.instance_client import make_api_call
from config.config_loader import APIConfig
from datetime import datetime, timezone

def validate_email(email: str) -> str:
    email_regex = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    if re.match(email_regex, email):
        return email
    else:
        raise ValueError(f"Invalid email format: {email}")


class AltinnVarslingClient:
    def __init__(self, base_url: str, maskinport_client_id: str, maskinport_kid: str, maskinport_scope: str, secret_value: str, maskinporten_endpoint: str, appname: str):
        self.base_url = base_url
        self.secret_value = secret_value
        self.maskinport_client_id = maskinport_client_id
        self.maskinport_kid = maskinport_kid
        self.maskinport_scope = maskinport_scope
        self.secret_value = secret_value
        self.maskinporten_endpoint = maskinporten_endpoint
        self.appname = appname
    
    @classmethod
    def init_from_config(cls, api_config: APIConfig) -> AltinnVarslingClient:
        return cls(
            base_url=api_config.altinn_client.base_varsling_url,
            maskinport_client_id=api_config.maskinporten_config_instance.client_id,
            maskinport_kid=api_config.maskinporten_config_instance.kid,
            maskinport_scope=api_config.maskinporten_config_varsling.scope,
            secret_value=api_config.secret_value,
            maskinporten_endpoint=api_config.maskinporten_endpoint,
            appname=api_config.app_config.app_name
        )

    def _get_headers(self, content_type: Optional[str] = None) -> Dict[str, str]:
        """Get fresh headers with new token"""
        token = exchange_token(
            maskinporten_endpoint=self.maskinporten_endpoint,
            secret=self.secret_value,
            client_id=self.maskinport_client_id,
            kid=self.maskinport_kid,
            scope=self.maskinport_scope,
        )
        headers = {"accept": "application/json", "Authorization": f"Bearer {token}"}
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def send_notification(self, 
                          recipient_email: str, 
                          subject: str, 
                          body: str, 
                          send_time: str, 
                          senders_reference: Optional[str] = None, 
                          sendingTimePolicy: Optional[str] = "Daytime") -> Dict[str, Any]:
        
    # "org_number": instance_meta_info["instanceOwner"]["organisationNumber"], 
    # "digitaliseringstiltak_report_id": digitaliseringstiltak_report_id ,
    # "dato": config.app_config.get_date(report_data), 
    # "app_name": config.workflow_dag.get_next(app_name), 
    # "prefill_data": report_data

        idempotency_id = str(uuid.uuid4())
        if not senders_reference:
            senders_reference = f"{idempotency_id}-notif"
        
        if not subject or not subject.strip():
            raise ValueError("Subject must not be empty")

        if not body or not body.strip():
            raise ValueError("Body must not be empty")
        if not send_time:
            send_time = datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")

        payload = {
            "sendersReference": senders_reference,
            "requestedSendTime": send_time,
            "idempotencyId": idempotency_id,
            "recipient": {
                "recipientEmail": {
                    "emailAddress": validate_email(recipient_email),
                    "emailSettings": {
                        "subject": subject,
                        "body": body,
                        "contentType": "Plain",
                        "sendingTimePolicy": sendingTimePolicy
                    }
                }
            }
        }
        response = make_api_call("POST", f"{self.base_url}/future/orders", headers=self._get_headers(content_type="application/json"), data=json.dumps(payload))
        return response

    def get_shipment_status(self, shipment_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/future/shipment/{shipment_id}"
        return make_api_call("GET", url=url, headers=self._get_headers())
