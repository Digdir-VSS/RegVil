from __future__ import annotations
from typing import Dict, Optional, Tuple, List
import requests
import logging
import json
import uuid
import datetime as dt
from unittest.mock import Mock

from auth.exchange_token_funcs import exchange_token
from config.config_loader import APIConfig

def get_meta_data_info(list_of_data_instance_meta_info: List[Dict[str, str]]) -> Dict[str, str]:
    if not list_of_data_instance_meta_info:
        raise ValueError("No instance metadata provided.")

    for instance in list_of_data_instance_meta_info:
        if (
            instance.get("dataType") in ["DataModel", "model"] and 
            instance.get("contentType") in ["application/xml", "application/json"]
        ):
            return instance
        else:
            continue

    raise ValueError("No instance with dataType='DataModel' and contentType='application/xml' or 'application/json' was found.")

def extract_instances_ids(data_storage_extract):
    instances = []
    for instance in data_storage_extract["instances"]:
        if instance.get("data", []):
            instance_data_meta_data = get_meta_data_info(instance["data"])


            instances.append(
            {"instanceOwnerPartyId": instance["instanceOwner"]["partyId"], 
            "organisationNumber": instance["instanceOwner"].get("organisationNumber", ""), 
            "personNumber": instance["instanceOwner"].get("personNumber", ""),
            "instanceId": instance["id"], 
            "dataGuid": instance_data_meta_data.get("id"),
            "tags": instance_data_meta_data.get("tags", [])}
        )
    return instances

def get_default_headers(bearer_token: str) -> Dict[str, str]:
    return {
            "accept": "application/json",
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json"
        }

def make_api_call(method: str, url: str, headers: Dict[str, str], data: Optional[Dict[str, str]] = None, params: Optional[Dict[str, str]] = None, files: Optional[Dict[str, str]] = None) -> Optional[requests.Response]:
    try:
        response = requests.request(method, url, headers=headers, data=data, params=params, files=files)
            
        if response.status_code in [200, 201, 204]:  # Success codes
            logging.info(f"API call successful: {method} {url}")
            return response
        elif response.status_code == 404:
            logging.warning(f"Resource not found: {method} {url}")
        elif response.status_code == 500:
            logging.warning(f"Error code {response.status_code} Error message {response.json()}")
        elif response.status_code == 403:
            logging.warning(f"Access denied: {method} {url}")
        elif response.status_code == 401:
            logging.warning(f"Unauthorized access - check authentication token")
        else:
            logging.warning(f"API call failed with status {response.status_code}: {response.text}")
        
        return None
            
    except requests.exceptions.ConnectionError:
        logging.error(f"Connection error when calling {url}")

    except requests.exceptions.Timeout:
        logging.error(f"Timeout when calling {url}")

    except requests.exceptions.RequestException as e:
        logging.error(f"Request failed: {str(e)}")

    except Exception as e:
        logging.error(f"Unexpected error in API call: {str(e)}")
        
    return None


def generate_mock_guid() -> str:
    return str(uuid.uuid4())

def mock_update_substatus(instanceOwnerPartyId: str, instanceGuid: str, digitaliseringstiltak_report_id: str) -> Mock:
    now_iso = dt.datetime.utcnow().isoformat() + "Z"
    # Construct mock response data
    response_data = {
        "instanceOwner": {
            "partyId": instanceOwnerPartyId
        },
        "id": f"{instanceOwnerPartyId}/{instanceGuid}",
        "status": {
            "substatus": {
                "label": "skjema_instance_created",
                "description": {"digitaliseringstiltak_report_id": digitaliseringstiltak_report_id}
            }
        },
        "lastChanged": now_iso,
        "lastChangedBy": "991825827"
    }

    mock_response = Mock()
    mock_response.status_code = 200  # OK
    mock_response.json.return_value = response_data
    mock_response.text = json.dumps(response_data)
    mock_response.headers = {
        "Content-Type": "application/json"
    }
    mock_response.ok = True
    mock_response.reason = "OK"
    return mock_response


def mock_post_new_instance(header: Dict[str, str], files: Dict[str, Tuple[str, str, str]]) -> Dict:
    # Parse instance and datamodel JSONs
    instance_content = json.loads(files["instance"][1])
    datamodel_content = json.loads(files["DataModel"][1])

    now_iso = dt.datetime.utcnow().isoformat() + "Z"
    instance_guid = generate_mock_guid()
    party_id = "51625403"  # Simulated party ID
    org_number = instance_content["instanceOwner"]["organisationNumber"]

    response_data = {
        "id": f"{party_id}/{instance_guid}",
        "instanceOwner": {
            "partyId": party_id,
            "organisationNumber": org_number,
            "party": {
                "partyId": party_id,
                "partyUuid": generate_mock_guid(),
                "partyTypeName": 2,
                "orgNumber": org_number,
                "unitType": "AS",
                "name": datamodel_content.get("Prefill", {}).get("AnsvarligVirksomhet", {}).get("Navn", None),
                "isDeleted": False
            }
        },
        "appId": instance_content.get("appId"),
        "org": instance_content.get("appId").split("/")[0],
        "dueBefore": instance_content.get("dueBefore"),
        "visibleAfter": instance_content.get("visibleAfter"),
        "status": {
            "isArchived": False,
            "isSoftDeleted": False,
            "isHardDeleted": False,
            "readStatus": 1,
            "substatus": None
        },
        "lastChangedBy": "991825827",
        "created": now_iso,
        "lastChanged": now_iso,
        "data": [
            {
                "id": generate_mock_guid(),
                "instanceGuid": instance_guid,
                "dataType": "DataModel",
                "contentType": "application/json",
                "created": now_iso,
                "lastChanged": now_iso,
                "lastChangedBy": "991825827"
            }
        ]
    }

        # Create mock response object
    mock_response = Mock()
    mock_response.status_code = 201  # Created
    mock_response.json.return_value = response_data
    mock_response.text = json.dumps(response_data)
    mock_response.headers = {
        "Content-Type": "application/json",
        "Location": f"/instances/{party_id}/{instance_guid}"
    }
    mock_response.ok = True
    mock_response.reason = "Created"
    
    return mock_response


class AltinnInstanceClient:

    def __init__(
        self,
        base_app_url: str,
        base_platfrom_url: str,
        application_owner_organisation: str,
        appname: str,
        maskinport_client_id: str,
        maskinport_kid: str,
        maskinport_scope: str,
        secret_value: str,
        maskinporten_endpoint: str,
    ):
        self.base_app_url = base_app_url
        self.base_platfrom_url = base_platfrom_url
        self.application_owner_organisation = application_owner_organisation
        self.appname = appname
        self.basePathApp = f"{self.base_app_url}/{self.application_owner_organisation}/{self.appname}/instances"
        self.basePathPlatform = f"{self.base_platfrom_url}"
                # Add token management
        self.maskinport_client_id = maskinport_client_id
        self.maskinport_kid = maskinport_kid
        self.maskinport_scope = maskinport_scope
        self.secret_value = secret_value
        self.maskinporten_endpoint = maskinporten_endpoint

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

    @classmethod
    def init_from_config(cls, api_config: APIConfig) -> AltinnInstanceClient:
        return cls(
            base_app_url=api_config.altinn_client.base_app_url,
            base_platfrom_url=api_config.altinn_client.base_platfrom_url,
            application_owner_organisation=api_config.altinn_client.application_owner_organisation,
            appname=api_config.app_config.app_name,
            maskinport_client_id=api_config.maskinporten_config_instance.client_id,
            maskinport_kid=api_config.maskinporten_config_instance.kid,
            maskinport_scope=api_config.maskinporten_config_instance.scope,
            secret_value=api_config.secret_value,
            maskinporten_endpoint=api_config.maskinporten_endpoint,
        )
    
    def get_instance(self, instanceOwnerPartyId: str, instance_id: str, header: Optional[Dict[str, str]] = None) -> Optional[requests.Response]:
        url = f"{self.basePathApp}/{instanceOwnerPartyId}/{instance_id}"
        return make_api_call(method="GET", url=url, headers=self._get_headers("application/json"))

    def get_instance_data(self, instanceOwnerPartyId: str, instance_id: str, dataGuid: str, header: Optional[Dict[str, str]] = None) -> Optional[requests.Response]:
        url = f"{self.basePathApp}/{instanceOwnerPartyId}/{instance_id}/data/{dataGuid}"
        return make_api_call(method="GET", url=url, headers=self._get_headers("application/json"))
    
    def get_active_instance(self, instanceOwnerPartyId: str, header: Optional[Dict[str, str]] = None) -> Optional[requests.Response]:
        url = f"{self.basePathApp}/{instanceOwnerPartyId}/active"
        return make_api_call(method="GET", url=url, headers=self._get_headers("application/json"))

    def post_new_instance(self, files: Dict[str, Tuple[str, str, str]], header: Optional[Dict[str, str]] = None) -> Optional[requests.Response]:
        url = f"{self.basePathApp}"
        return make_api_call(method="POST", url=url, headers=self._get_headers(), files=files)
    
    def mock_test_post_new_instance(self,  files: Dict[str, Tuple[str, str, str]], header: Optional[Dict[str, str]] = None) -> Dict:
        """Simulates an API response from Altinn after posting a new instance."""
        return mock_post_new_instance(header, files)
        
    def get_stored_instances_ids(self, header: Optional[Dict[str, str]] = None):
        url = f"{self.base_platfrom_url}"
        params = {
        'org': self.application_owner_organisation,
        'appId': f"{self.application_owner_organisation}/{self.appname}"
        }
        data_storage_instances = make_api_call(method="GET", url=url, headers=self._get_headers("application/json"), params=params)
        return extract_instances_ids(data_storage_instances.json())

    def instance_created(self, org_number: str, tag: str, header: Optional[Dict[str, str]] = None) -> bool:
        stored_instances = self.get_stored_instances_ids(self._get_headers("application/json"))
        for instance in stored_instances:
            if instance.get("organisationNumber") != org_number:
                continue
            if tag in instance.get("tags"):
                return True
        return False
    
    def complete_instance(self, instanceOwnerPartyId: str, instance_id: str, header: Optional[Dict[str, str]] = None) -> Optional[requests.Response]:
        url = f"{self.basePathApp}/{instanceOwnerPartyId}/{instance_id}/complete"
        return make_api_call(method="POST", url=url, headers=self._get_headers("application/json"))
    
    def update_substatus(self, instanceOwnerPartyId: str, instance_id: str, digitaliseringstiltak_report_id: str, header: Optional[Dict[str, str]] = None) -> Optional[requests.Response]:
        url = f"{self.basePathApp}/{instanceOwnerPartyId}/{instance_id}/substatus"
        payload = {
            "label": "skjema_instance_created",
            "description": json.dumps({"digitaliseringstiltak_report_id": digitaliseringstiltak_report_id})
        }
        return make_api_call(method="PUT", url=url, headers=self._get_headers(), data=json.dumps(payload))
    
    def tag_instance_data(self, instanceOwnerPartyId: str, instance_id: str, dataGuid: str, tag: str, header: Optional[Dict[str, str]] = None) -> Optional[requests.Response]:
        url = f"{self.basePathApp}/{instanceOwnerPartyId}/{instance_id}/data/{dataGuid}/tags"
        return make_api_call(method="POST", url=url, headers=self._get_headers("application/json"), data=json.dumps(tag))
    
    def mock_test_update_substatus(self, instanceOwnerPartyId: str, instanceGuid: str, digitaliseringstiltak_report_id: str, header: Optional[Dict[str, str]] = None):
        return mock_update_substatus(instanceOwnerPartyId, instanceGuid, digitaliseringstiltak_report_id)
    
    def delete_instance(self, instanceOwnerPartyId: str, instance_id: str, header: Optional[Dict[str, str]] = None) -> Optional[requests.Response]:
        url = f"{self.basePathApp}/{instanceOwnerPartyId}/{instance_id}?hard=true"
        # return url, self._get_headers("application/json")
        return make_api_call(method="DELETE", url=url, headers=self._get_headers("application/json"))