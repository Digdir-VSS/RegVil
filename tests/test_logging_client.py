import pytest

from pathlib import Path
import json
import os
import sys
import importlib
import importlib.util
from typing import Dict, Any

def load_in_json(path_to_json_file: Path) -> Dict[str, Any]:
    with open(path_to_json_file, 'r', encoding='utf-8') as file:
        return json.load(file)

def import_fabric_notebook(notebook_path, module_name):
    """Import a Fabric notebook's Python content"""
    py_file_path = os.path.join(notebook_path, 'notebook-content.py')
   
    spec = importlib.util.spec_from_file_location(module_name, py_file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

test_prefill_data_with_errors = load_in_json(Path(__file__).parent.parent / "data" / "test_virksomheter_prefill_with_uuid_with_errors.json")
test_prefill_data = load_in_json(Path(__file__).parent.parent / "data" / "test_virksomheter_prefill_with_uuid.json")

instance_logging = import_fabric_notebook('clients/instance_logging.Notebook', 'instance_logging')


def test_prefill_valdiation_correct():
    assert True == instance_logging.validate_prefill_data(test_prefill_data_with_errors[0])

@pytest.mark.parametrize("row", test_prefill_data_with_errors[1:])
def test_prefill_validation_fails(row):
    with pytest.raises(instance_logging.PrefillValidationError):
        instance_logging.validate_prefill_data(row)

def test_transform_flat_to_nested_with_prefill_single():
    result = instance_logging.transform_flat_to_nested_with_prefill(test_prefill_data[0])
    expected = {
        "Prefill": {
            "AnsvarligDepartement": {
                "Navn": "KRISTIANSAND",
                "Organisasjonsnummer": "310075728"
            },
            "AnsvarligVirksomhet": {
                "Navn": "KVADRATISK BRA APE",
                "Organisasjonsnummer": "310075728"
            },
            "Kontaktperson": {
                "FulltNavn": "Kontaktperson 1",
                "Telefonnummer": "+(47) 19094980",
                "EPostadresse": "01909498089@testmail.no"
            },
            "Tiltak": {
                "Nummer": "15",
                "Tekst": "15",
                "Kortnavn": "videreutvikle virkemidler for digitalisering og innovasjon i offentlig sektor",
                "ErDeltiltak": True
            },
            "Kapittel": {
                "Nummer": "3.1.1",
                "Tekst": "3.1.1"
            },
            "Maal": {
                "Nummer": "3",
                "Tekst": "3"
            }
        }
    }
    assert result == expected

def test_missing_key_raises_error():
    flat_record = {
        "AnsvarligDepartement.Navn": "A",
    }
    with pytest.raises(KeyError):
        instance_logging.transform_flat_to_nested_with_prefill(flat_record)


def test_returns_true_when_exact_match_found():
    """Test returns True when exact org_number and report_id match"""
    log_data = {
            "organisations": {
                "123456789": {
                    "events": [
                        {
                            "event_type": "initiell_skjema_instance_created",
                            "digitaliseringstiltak_report_id": "target-uuid-123",
                            "org_number": "123456789"
                        }
                    ]
                }
            }
        }
    tracker = instance_logging.InstanceTracker(log_data)
    result = tracker.has_processed_instance("123456789", "target-uuid-123")
    assert result is True

def test_returns_false_when_org_not_found():
    """Test returns False when organisation doesn't exist"""
    log_data = {
            "organisations": {
                "123456789": {
                    "events": [
                        {
                            "event_type": "initiell_skjema_instance_created",
                            "digitaliseringstiltak_report_id": "some-uuid",
                            "org_number": "123456789"
                        }
                    ]
                }
            }
        }
    tracker = instance_logging.InstanceTracker(log_data)
    result = tracker.has_processed_instance("999999999", "some-uuid")
    assert result is False
    
def test_returns_false_when_report_id_not_found():
    """Test returns False when report_id doesn't exist for org"""
    log_data = {
            "organisations": {
                "123456789": {
                    "events": [
                        {
                            "event_type": "initiell_skjema_instance_created",
                            "digitaliseringstiltak_report_id": "existing-uuid",
                            "org_number": "123456789"
                        }
                    ]
                }
            }
        }
    tracker = instance_logging.InstanceTracker(log_data)
    result = tracker.has_processed_instance("123456789", "different-uuid")
    assert result is False
    
def test_returns_false_when_wrong_event_type():
    """Test returns False when event_type is not 'skjema_instance_created'"""
    log_data = {
            "organisations": {
                "123456789": {
                    "events": [
                        {
                            "event_type": "different_event_type",
                            "digitaliseringstiltak_report_id": "target-uuid",
                            "org_number": "123456789"
                        }
                    ]
                }
            }
        }
    tracker = instance_logging.InstanceTracker(log_data)
    result = tracker.has_processed_instance("123456789", "target-uuid")
    assert result is False
    
def test_returns_true_with_multiple_events_target_first():
    """Test returns True when target event is first in list"""
    log_data = {
            "organisations": {
                "123456789": {
                    "events": [
                        {
                            "event_type": "initiell_skjema_instance_created",
                            "digitaliseringstiltak_report_id": "target-uuid",
                            "org_number": "123456789"
                        },
                        {
                            "event_type": "initiell_skjema_instance_created",
                            "digitaliseringstiltak_report_id": "other-uuid",
                            "org_number": "123456789"
                        }
                    ]
                }
            }
        }
    tracker = instance_logging.InstanceTracker(log_data)
    result = tracker.has_processed_instance("123456789", "target-uuid")
    assert result is True
    
def test_returns_true_with_multiple_events_target_last():
    """Test returns True when target event is last in list"""
    log_data = {
            "organisations": {
                "123456789": {
                    "events": [
                        {
                            "event_type": "initiell_skjema_instance_created",
                            "digitaliseringstiltak_report_id": "other-uuid-1",
                            "org_number": "123456789"
                        },
                        {
                            "event_type": "initiell_skjema_instance_created",
                            "digitaliseringstiltak_report_id": "other-uuid-2",
                            "org_number": "123456789"
                        },
                        {
                            "event_type": "initiell_skjema_instance_created",
                            "digitaliseringstiltak_report_id": "target-uuid",
                            "org_number": "123456789"
                        }
                    ]
                }
            }
        }
    tracker = instance_logging.InstanceTracker(log_data)
    result = tracker.has_processed_instance("123456789", "target-uuid")
    assert result is True
    
def test_returns_true_with_mixed_event_types():
    """Test returns True when target event exists among different event types"""
    log_data = {
            "organisations": {
                "123456789": {
                    "events": [
                        {
                            "event_type": "other_event",
                            "digitaliseringstiltak_report_id": "target-uuid",
                            "org_number": "123456789"
                        },
                        {
                            "event_type": "initiell_skjema_instance_created",
                            "digitaliseringstiltak_report_id": "target-uuid",
                            "org_number": "123456789"
                        }
                    ]
                }
            }
        }
    tracker = instance_logging.InstanceTracker(log_data)
    result = tracker.has_processed_instance("123456789", "target-uuid")
    assert result is True
    
def test_returns_false_when_events_list_empty():
    """Test returns False when events list is empty"""
    log_data = {
            "organisations": {
                "123456789": {
                    "events": []
                }
            }
        }
    tracker = instance_logging.InstanceTracker(log_data)
    result = tracker.has_processed_instance("123456789", "any-uuid")
    assert result is False


test_meta_instance_data = {
  "id": "51625403/0512ce74-90a9-4b5c-ab15-910f60db92d1",
  "instanceOwner": {
    "partyId": "51625403",
    "personNumber": None,
    "organisationNumber": "311138693",
      "party": {
      "partyId": 51625403,
      "partyUuid": "1ed8aa98-31ed-4f78-b1f6-f12f46e8de04",
      "partyTypeName": 2,
      "orgNumber": "311138693",
      "name": "OMKOMMEN TRU TIGER AS",
    }
  },
  "appId": "digdir/regvil-2025-initiell",
  "org": "digdir",
  "dueBefore": "2025-06-01T12:00:00Z",
  "visibleAfter": "2025-05-20T00:00:00Z",
  "data": [
    {
      "id": "fed122b9-672c-4b34-9a47-09f501d5af72",
      "instanceGuid": "0512ce74-90a9-4b5c-ab15-910f60db92d1",
      "dataType": "DataModel",
      "contentType": "application/xml",
      "created": "2025-06-24T10:42:49.5878193Z",
      "createdBy": "991825827",
      "lastChanged": "2025-06-24T10:43:23.253583Z",
      "lastChangedBy": "1260288"
    },
  ],
  "created": "2025-06-24T10:42:49.5447149Z",
  "createdBy": "991825827",
  "lastChanged": "2025-06-24T13:17:29.883956Z",
  "lastChangedBy": "991825827"
}

def test_logging_instance():

    instance_logger = instance_logging.InstanceTracker({"organisations": {}}, "test/path")
    print(test_meta_instance_data)
    instance_logger.logging_instance("311138693", "123-uuid", test_meta_instance_data)

    with pytest.raises(ValueError, match="Organization number and report ID cannot be empty"):
        instance_logger.logging_instance("", "123-uuid", test_meta_instance_data)

    with pytest.raises(ValueError, match="Organization number and report ID cannot be empty"):
        instance_logger.logging_instance("311138693", "", test_meta_instance_data)
    
    with pytest.raises(ValueError, match="Instance meta data cannot be empty"):
        instance_logger.logging_instance("311138693", "123-uuid", {})

    # Extract the logged event
    logged_event = instance_logger.log_changes["311138693"].copy()
    logged_event.pop("processed_timestamp")
    expected_event = {
        'event_type': 'initiell_skjema_instance_created',
        'digitaliseringstiltak_report_id': '123-uuid',
        'org_number': '311138693',
        'virksomhets_name': 'OMKOMMEN TRU TIGER AS',
        'instancePartyId': '51625403',
        'instanceId': '51625403/0512ce74-90a9-4b5c-ab15-910f60db92d1',
        'instance_info': {
            'last_changed': '2025-06-24T13:17:29.883956Z',
            'last_changed_by': '991825827',
            'created': '2025-06-24T10:42:49.5447149Z',
        },
        'data_info': {
            'last_changed': '2025-06-24T10:43:23.253583Z',
            'last_changed_by': '1260288',
            'created': '2025-06-24T10:42:49.5878193Z',
            'dataGuid': 'fed122b9-672c-4b34-9a47-09f501d5af72',
        },
    }
    assert logged_event == expected_event

    instance_logger = instance_logging.InstanceTracker({"organisations": {"previous-org-nr":{}}}, "test/path")
    instance_logger.logging_instance("311138693", "123-uuid", test_meta_instance_data)
    # Extract the logged event
    logged_event = instance_logger.log_file["organisations"]["311138693"]["events"][0].copy()
    logged_event.pop("processed_timestamp")
    expected_event = {
        'event_type': 'initiell_skjema_instance_created',
        'digitaliseringstiltak_report_id': '123-uuid',
        'org_number': '311138693',
        'virksomhets_name': 'OMKOMMEN TRU TIGER AS',
        'instancePartyId': '51625403',
        'instanceId': '51625403/0512ce74-90a9-4b5c-ab15-910f60db92d1',
        'instance_info': {
            'last_changed': '2025-06-24T13:17:29.883956Z',
            'last_changed_by': '991825827',
            'created': '2025-06-24T10:42:49.5447149Z',
        },
        'data_info': {
            'last_changed': '2025-06-24T10:43:23.253583Z',
            'last_changed_by': '1260288',
            'created': '2025-06-24T10:42:49.5878193Z',
            'dataGuid': 'fed122b9-672c-4b34-9a47-09f501d5af72',
        },
    }
    assert logged_event == expected_event
    assert list(instance_logger.log_file["organisations"].keys()) == ["previous-org-nr", "311138693"]

    logger = instance_logging.InstanceTracker({"organisations": {}}, "test/path")
    logger.logging_instance("311138693", "uuid-1", test_meta_instance_data)
    logger.logging_instance("311138693", "uuid-2", test_meta_instance_data)

    events = logger.log_file["organisations"]["311138693"]["events"]
    assert len(events) == 2
    assert events[0]["digitaliseringstiltak_report_id"] == "uuid-1"
    assert events[1]["digitaliseringstiltak_report_id"] == "uuid-2"

    logger = instance_logging.InstanceTracker({"organisations": {}}, "test/path")
    logger.logging_instance("311138693", "uuid-1", test_meta_instance_data)
    first_id = logger.log_changes["311138693"]["digitaliseringstiltak_report_id"]

    logger.logging_instance("311138693", "uuid-2", test_meta_instance_data)
    second_id = logger.log_changes["311138693"]["digitaliseringstiltak_report_id"]

    assert first_id == "uuid-1"
    assert second_id == "uuid-2"
    assert len(logger.log_changes) == 1

    logger = instance_logging.InstanceTracker({"organisations": {}}, "test/path")
    mismatching_meta = test_meta_instance_data.copy()
    mismatching_meta['instanceOwner'] = mismatching_meta['instanceOwner'].copy()
    mismatching_meta['instanceOwner']['organisationNumber'] = "999999999"  # Not matching

    with pytest.raises(ValueError, match="Organization numbers do not match"):
        logger.logging_instance("311138693", "123-uuid", mismatching_meta)