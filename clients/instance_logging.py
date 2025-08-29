import re
from typing import Any, Dict, List
import json
import datetime
import os
import shutil
from config.utils import chech_file_exists, write_blob, read_blob
import logging
class PrefillValidationError(Exception):
    pass


def get_reportid_from_blob(directory: str, appId: str, instance_id: str, event_type: str) -> Dict[str, Any]:
    if not chech_file_exists(directory+f"{appId}_{event_type}_{instance_id}.json"):
        logging.warning(f"File {appId}_{event_type}_{instance_id}.json does not exist.")
        return None
    json_data = read_blob(directory+f"{appId}_{event_type}_{instance_id}.json")
    return json_data["digitaliseringstiltak_report_id"]


class InstanceTracker:
    def __init__(self, log_file: Dict[str, Any], log_path: str = None):
        self.log_file = {}
        self.file_name = "" 
        self.log_path = log_path
        self.log_changes = {}
    
    @classmethod
    def from_directory(cls, path_to_json_dir: str):
        # Now expects a directory, not a file
        return cls({"organisations": {}}, log_path=path_to_json_dir)
    
      
    def logging_varlsing(self, org_number: str, org_name: str,app_name: str,send_time: str, digitaliseringstiltak_report_id: str, shipment_id: str, recipientEmail: str, event_type: str, shipment_status: Dict[str, Any] = None):
        if not org_number or not digitaliseringstiltak_report_id:
          logging.warning("Organization number and report ID cannot be empty. Shipment_id: {shipment_id}, org_number: {org_number}, digitaliseringstiltak_report_id: {digitaliseringstiltak_report_id}")
        
        instance_log_entry = {
            "event_type": event_type,
            "digitaliseringstiltak_report_id": digitaliseringstiltak_report_id, 
            "org_number": org_number,
            "virksomhets_name":org_name,
            "processed_timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            "sent_time": send_time,
            "app_name": app_name,
            "shipment_id": shipment_id, 
            "recipientEmail": recipientEmail,
            "shipment_status": shipment_status
        }
        
        write_blob(self.log_path+f"{digitaliseringstiltak_report_id}_{app_name}_{event_type}_{shipment_id}.json",instance_log_entry)

    def logging_instance(self, instance_id: str,org_number: str, digitaliseringstiltak_report_id: str, instance_meta_data: dict, data_dict: dict ,event_type: str):
        if not org_number or not digitaliseringstiltak_report_id:
            logging.warning("Organization number and report ID cannot be empty. Instance_id: {instance_id}, org_number: {org_number}, digitaliseringstiltak_report_id: {digitaliseringstiltak_report_id}")
        if not instance_meta_data:
            logging.warning("Instance meta data cannot be empty. Instance_id: {instance_id}, org_number: {org_number}, digitaliseringstiltak_report_id: {digitaliseringstiltak_report_id}")
        if not data_dict:
            logging.warning("Data dictionary cannot be empty. Instance_id: {instance_id}, org_number: {org_number}, digitaliseringstiltak_report_id: {digitaliseringstiltak_report_id}")
        if org_number != instance_meta_data['instanceOwner'].get("organisationNumber"):
            logging.warning(f"Organization numbers do not match: {org_number} != {instance_meta_data['instanceOwner'].get('organisationNumber')}. Instance_id: {instance_id}, org_number: {org_number}, digitaliseringstiltak_report_id: {digitaliseringstiltak_report_id}")
        
        datamodel_metadata = get_meta_data_info(instance_meta_data["data"])
        app_id = instance_meta_data["appId"].split("/")[-1]
        instance_log_entry = {
            "event_type": event_type,
            "appId": app_id,
            "digitaliseringstiltak_report_id": digitaliseringstiltak_report_id, 
            "org_number": org_number,
            "virksomhets_name": instance_meta_data.get("instanceOwner").get("party").get("name"),
            "processed_timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            "instancePartyId": instance_meta_data['instanceOwner'].get("partyId"),
            "instanceId": instance_id,
            "visibleAfter": instance_meta_data.get("visibleAfter"),
            "instance_info.last_changed": instance_meta_data.get('lastChanged'),
            "instance_info.last_changed_by": instance_meta_data.get('lastChangedBy'),
            "instance_info.created": instance_meta_data.get('created'),
            "data_info.last_changed": datamodel_metadata.get('lastChanged'),
            "data_info.last_changed_by": datamodel_metadata.get('lastChangedBy'),
            "data_info.created": datamodel_metadata.get('created'), 
            "data_info.dataGuid": datamodel_metadata.get('id'),
            "data": data_dict
        } 
        write_blob( self.log_path+f"{app_id}_{event_type}_{instance_id}.json",instance_log_entry)

                            
def get_meta_data_info(list_of_data_instance_meta_info: List[Dict[str, str]]) -> Dict[str, str]:
    if not list_of_data_instance_meta_info:
        raise ValueError("No instance metadata provided.")

    for instance in list_of_data_instance_meta_info:
        if (
            instance.get("dataType") == "DataModel" and 
            instance.get("contentType") in ["application/xml", "application/json"]
        ):
            return instance

    raise ValueError("No instance with dataType='DataModel' and contentType='application/xml' or 'application/json' was found.")