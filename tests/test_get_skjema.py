import pytest
from unittest.mock import patch, MagicMock
from get_initiell_skjema import run  # Make sure this matches the filename
import logging
from config.config_loader import APPConfig

SAMPLE_PARTY_ID = "50015641"
SAMPLE_INSTANCE_ID = "a72223a3-926b-4095-a2a6-bacc10815f2d"
SAMPLE_APP_NAME = "regvil-2025-initiell"

@patch("get_initiell_skjema.find_event_by_instance")
@patch("get_initiell_skjema.InstanceTracker")
@patch("get_initiell_skjema.AltinnInstanceClient")
@patch("get_initiell_skjema.SecretClient")
@patch("get_initiell_skjema.DefaultAzureCredential")
@patch("get_initiell_skjema.load_dotenv")
@patch("get_initiell_skjema.load_full_config")
def test_run_success(
    mock_load_config,
    mock_load_dotenv,
    mock_default_cred,
    mock_secret_client,
    mock_altinn_client,
    mock_tracker,
    mock_find_event
):
    # Mock config
    mock_config = MagicMock()
    mock_config.app_config.tag = {
        "tag_instance": "created",
        "tag_download": "downloaded"
    }
    mock_load_config.return_value = mock_config

    # Mock secret
    mock_secret = MagicMock()
    mock_secret.value = "supersecret"
    mock_secret_client.return_value.get_secret.return_value = mock_secret

    # Mock event
    mock_find_event.return_value = {
        "org_number": "123456789",
        "instancePartyId": SAMPLE_PARTY_ID,
        "instanceId": f"{SAMPLE_PARTY_ID}/{SAMPLE_INSTANCE_ID}",
        "data_info": {"dataGuid": "abc123"},
        "digitaliseringstiltak_report_id": "report001"
    }

    # Mock instance response
    instance_mock = MagicMock()
    instance_mock.json.return_value = {
    "id": f"{SAMPLE_PARTY_ID}/{SAMPLE_INSTANCE_ID}",
    "instanceOwner": {"organisationNumber": "123456789"}, 
    "data": [{
        "dataType": "DataModel",  
        "contentType": "application/json",  
        "createdBy": "user1",
        "lastChangedBy": "user2",
        "id": "abc123",
        "tags": ["created"]
    }]
}

    mock_altinn = mock_altinn_client.init_from_config.return_value
    mock_altinn.get_instance.return_value = instance_mock
    mock_altinn.get_instance_data.return_value.json.return_value = {"field": "value"}
    mock_altinn.tag_instance_data.return_value.status_code = 200

    mock_tracker_inst = mock_tracker.from_log_file.return_value

    result = run(SAMPLE_PARTY_ID, SAMPLE_INSTANCE_ID, SAMPLE_APP_NAME)
    assert isinstance(result, dict)

@patch("get_initiell_skjema.load_dotenv")
@patch("get_initiell_skjema.load_full_config")
@patch("get_initiell_skjema.AltinnInstanceClient")
@patch("get_initiell_skjema.InstanceTracker")
@patch("get_initiell_skjema.get_meta_data_info")
def test_run_raises_value_error_on_invalid_metadata(
    mock_get_meta_data_info,
    mock_instance_tracker,
    mock_instance_client_class,
    mock_load_config,
    mock_load_dotenv
):
    # Arrange
    mock_client = MagicMock()
    mock_instance_client_class.init_from_config.return_value = mock_client

    mock_client.get_instance.return_value.json.return_value = {
            "id": f"{SAMPLE_PARTY_ID}/{SAMPLE_INSTANCE_ID}",
    "instanceOwner": {"organisationNumber": "123456789"}, 
        "data": [{"tags": ["InitiellSkjemaDownloaded"], "id": "abc123",  "createdBy": "user", "lastChangedBy": "user"}]
    }

    mock_tracker = MagicMock()
    mock_tracker.log_file = {"organisations": []}
    mock_instance_tracker.from_log_file.return_value = mock_tracker

    # Cause get_meta_data_info to raise the ValueError
    mock_get_meta_data_info.side_effect = ValueError("No instance with dataType='DataModel'...")

    # Act & Assert
    with pytest.raises(ValueError, match="Log data is empty."):
        run("50015641", "a72223a3-926b-4095-a2a6-bacc10815f2d", "regvil-2025-initiell")

#Test: Already tagged (skip download)
@patch("get_initiell_skjema.load_dotenv")
@patch("get_initiell_skjema.load_full_config")
@patch("get_initiell_skjema.AltinnInstanceClient")
@patch("get_initiell_skjema.InstanceTracker")
@patch("get_initiell_skjema.get_meta_data_info")
def test_run_skips_when_already_tagged(
    mock_get_meta_data_info,
    mock_instance_tracker,
    mock_instance_client_class,
    mock_load_config,
    mock_load_dotenv
):
    mock_client = MagicMock()
    mock_instance_client_class.init_from_config.return_value = mock_client

    mock_client = MagicMock()
    mock_instance_client_class.init_from_config.return_value = mock_client

    mock_config = MagicMock()
    mock_config.app_config.tag = {
    "tag_instance": "InitiellSkjemaLevert",
    "tag_download": "InitiellSkjemaDownloaded"
}
    mock_load_config.return_value = mock_config

    mock_client.get_instance.return_value.json.return_value = {
            "id": f"{SAMPLE_PARTY_ID}/{SAMPLE_INSTANCE_ID}",
    "instanceOwner": {"organisationNumber": "123456789"}, 
        "data": [{"tags": ["InitiellSkjemaDownloaded"], "id": "abc123",  "createdBy": "user", "lastChangedBy": "user"}]
    }

    mock_get_meta_data_info.return_value = {"tags": ["InitiellSkjemaDownloaded"], "id": "abc123",  "createdBy": "user", "lastChangedBy": "user"}

    mock_tracker = MagicMock()
    mock_tracker.log_file = {
  "organisations": {
    "123456789": {
      "events": [
          {
            "instanceId": "50015641/a72223a3-926b-4095-a2a6-bacc10815f2d",
            "instancePartyId": "50015641",
            "org_number": "123456789",
            "data_info": {"dataGuid": "abc123"},
            "digitaliseringstiltak_report_id": "report-1",
            "event_type": "InitiellSkjemaLevert"
        }
    ]}}}
    mock_instance_tracker.from_log_file.return_value = mock_tracker

    result = run("50015641", "a72223a3-926b-4095-a2a6-bacc10815f2d", "regvil-2025-initiell")
    assert result is None  # run logs and skips when already tagged

#Test: Successful full run
@patch("get_initiell_skjema.write_to_json")
@patch("get_initiell_skjema.get_meta_data_info")
@patch("get_initiell_skjema.InstanceTracker")
@patch("get_initiell_skjema.AltinnInstanceClient")
@patch("get_initiell_skjema.load_full_config")
@patch("get_initiell_skjema.load_dotenv")
def test_run_success_full_flow(
    mock_load_dotenv,
    mock_load_config,
    mock_instance_client_class,
    mock_instance_tracker,
    mock_get_meta_data_info,
    mock_write_to_json
):
    mock_client = MagicMock()
    mock_instance_client_class.init_from_config.return_value = mock_client

    mock_config = MagicMock()
    mock_config.app_config.tag = {
    "tag_instance": "InitiellSkjemaLevert",
    "tag_download": "InitiellSkjemaDownloaded"
}
    mock_load_config.return_value = mock_config

    mock_get_meta_data_info.return_value = {
        "tags": ["InitiellSkjemaLevert"],
        "createdBy": "user2",
        "id": "abc123",
        "lastChangedBy": "user1",
        "dataType": "DataModel",
        "contentType": "application/json"
    }

    mock_client.get_instance.return_value.json.return_value = {
            "id": f"{SAMPLE_PARTY_ID}/{SAMPLE_INSTANCE_ID}",
    "instanceOwner": {"organisationNumber": "123456789"}, 
        "data": [{"tags": ["InitiellSkjemaDownloaded"], "id": "abc123",  "createdBy": "user1", "lastChangedBy": "user2"}]
    }

    mock_client.get_instance_data.return_value.json.return_value = {
        "Initiell": {"DatoPaabegynt": "2024-01-01"}
    }

    mock_tracker = MagicMock()
    mock_tracker.log_file = {
  "organisations": {
    "123456789": {
      "events": [
          {
            "instanceId": "50015641/a72223a3-926b-4095-a2a6-bacc10815f2d",
            "instancePartyId": "50015641",
            "org_number": "123456789",
            "data_info": {"dataGuid": "abc123"},
            "digitaliseringstiltak_report_id": "report-1",
            "event_type": "InitiellSkjemaLevert"
        }
    ]}}}
    mock_instance_tracker.from_log_file.return_value = mock_tracker

    result = run("50015641", "a72223a3-926b-4095-a2a6-bacc10815f2d", "regvil-2025-initiell")
    print(result)
    assert isinstance(result, dict)

@patch("get_initiell_skjema.find_event_by_instance")
@patch("get_initiell_skjema.InstanceTracker")
@patch("get_initiell_skjema.AltinnInstanceClient")
@patch("get_initiell_skjema.SecretClient")
@patch("get_initiell_skjema.DefaultAzureCredential")
@patch("get_initiell_skjema.load_dotenv")
@patch("get_initiell_skjema.load_full_config")
def test_run_logs_exception_when_instance_data_fails(
    mock_load_config,
    mock_load_dotenv,
    mock_default_cred,
    mock_secret_client,
    mock_altinn_client,
    mock_tracker,
    mock_find_event,
    caplog
):
    # Arrange
    caplog.set_level("ERROR")

    mock_config = MagicMock()
    mock_config.app_config.tag = {
        "tag_instance": "created",
        "tag_download": "downloaded"
    }
    mock_load_config.return_value = mock_config

    mock_secret = MagicMock()
    mock_secret.value = "secret"
    mock_secret_client.return_value.get_secret.return_value = mock_secret

    mock_find_event.return_value = {
        "org_number": "123456789",
        "instancePartyId": "50015641",
        "instanceId": "50015641/a72223a3-926b-4095-a2a6-bacc10815f2d",
        "data_info": {"dataGuid": "abc123"},
        "digitaliseringstiltak_report_id": "report001"
    }

    mock_client = MagicMock()
    mock_altinn_client.init_from_config.return_value = mock_client

    # Force an exception when calling get_instance().json()
    broken_instance_response = MagicMock()
    broken_instance_response.json.side_effect = Exception("Failed to parse JSON")
    mock_client.get_instance.return_value = broken_instance_response

    mock_tracker.from_log_file.return_value.log_file = {
        "organisations": {
            "123456789": {
                "events": [mock_find_event.return_value]
            }
        }
    }

    # Act & Assert
    with pytest.raises(Exception, match="Failed to parse JSON"):
        run("50015641", "a72223a3-926b-4095-a2a6-bacc10815f2d", "regvil-2025-initiell")

    # Validate that logging.exception was called with the correct message
    assert any(
        "Error processing party id: 50015641, instance id a72223a3-926b-4095-a2a6-bacc10815f2d"
        in message
        for message in caplog.text.splitlines()
    )

@patch("get_initiell_skjema.AltinnInstanceClient")
@patch("get_initiell_skjema.InstanceTracker")
@patch("get_initiell_skjema.find_event_by_instance")
@patch("get_initiell_skjema.load_full_config")
@patch("get_initiell_skjema.load_dotenv")
def test_run_returns_none_if_get_instance_fails(
    mock_dotenv, mock_config, mock_find_event, mock_tracker, mock_client_class, caplog
):
    mock_find_event.return_value = {"instancePartyId": "500", "instanceId": "abc"}
    mock_client = MagicMock()
    mock_client.get_instance.return_value = None
    mock_client_class.init_from_config.return_value = mock_client

    with caplog.at_level(logging.ERROR):
        result = run("500", "abc", "regvil-2025-initiell")
    assert result is None

@patch("get_initiell_skjema.get_meta_data_info")
@patch("get_initiell_skjema.AltinnInstanceClient")
@patch("get_initiell_skjema.InstanceTracker")
@patch("get_initiell_skjema.find_event_by_instance")
@patch("get_initiell_skjema.load_full_config")
@patch("get_initiell_skjema.load_dotenv")
def test_run_returns_none_if_get_instance_data_fails(
    mock_dotenv, mock_config, mock_find_event, mock_tracker,
    mock_client_class, mock_get_meta, caplog
):
    mock_find_event.return_value = {
        "instancePartyId": "500", "instanceId": "abc", "data_info": {"dataGuid": "123"}, "digitaliseringstiltak_report_id": "r1"
    }

    mock_client = MagicMock()
    mock_instance = MagicMock()
    mock_instance.json.return_value = {
        "data": [{"dataType": "DataModel", "contentType": "application/json", "createdBy": "user1", "lastChangedBy": "user2", "tags": ["tag"]}],
        "id": "500/abc", "instanceOwner": {"orgNumber": "123456789"}
    }
    mock_client.get_instance.return_value = mock_instance
    mock_client.get_instance_data.return_value = None
    mock_client_class.init_from_config.return_value = mock_client

    mock_get_meta.return_value = {
        "dataType": "DataModel", "contentType": "application/json", "createdBy": "user1", "lastChangedBy": "user2", "tags": ["tag"], "id": "123"
    }

    with caplog.at_level(logging.ERROR):
        result = run("500", "abc", "regvil-2025-initiell")
    result = run("500", "abc", "regvil-2025-initiell")
    assert result is None

@patch("get_initiell_skjema.get_meta_data_info")
@patch("get_initiell_skjema.AltinnInstanceClient")
@patch("get_initiell_skjema.InstanceTracker")
@patch("get_initiell_skjema.find_event_by_instance")
@patch("get_initiell_skjema.load_full_config")
@patch("get_initiell_skjema.load_dotenv")
def test_run_skips_if_tag_does_not_match(
    mock_dotenv, mock_config, mock_find_event, mock_tracker,
    mock_client_class, mock_get_meta, caplog
):
    mock_find_event.return_value = {
        "instancePartyId": "500", "instanceId": "abc", "data_info": {"dataGuid": "123"}, "digitaliseringstiltak_report_id": "r1"
    }

    mock_client = MagicMock()
    mock_instance = MagicMock()
    mock_instance.json.return_value = {
        "data": [{"tags": ["wrong_tag"], "createdBy": "user", "lastChangedBy": "user", "dataType": "DataModel", "contentType": "application/json"}],
        "id": "500/abc", "instanceOwner": {"orgNumber": "123456789"}
    }
    mock_client.get_instance.return_value = mock_instance
    mock_client_class.init_from_config.return_value = mock_client

    mock_get_meta.return_value = {
        "tags": ["wrong_tag"], "createdBy": "user", "lastChangedBy": "user", "id": "123"
    }

    mock_config_inst = MagicMock()
    mock_config_inst.app_config.tag = {"tag_instance": "expected_tag", "tag_download": "downloaded"}
    mock_config.return_value = mock_config_inst
    with caplog.at_level(logging.WARNING):
        result = run("500", "abc", "regvil-2025-initiell")
    assert result is None

@pytest.mark.parametrize("app_name, report_data, expected_date_start", [
    (
        "regvil-2025-initiell",
        {"Initiell": {"ErTiltaketPaabegynt": True, "DatoPaabegynt": "2025-07-10T00:00:00Z"}},
        "2025-07-10T"
    ),
    (
        "regvil-2025-oppstart",
        {"Oppstart": {"ForventetSluttdato": "2025-01-01T00:00:00Z"}},
        "2025-07"  # 2025-01-01 + P6M = 2025-07-01 (approx)
    ),
        (
        "regvil-2025-status",
        {"Status": {"ErArbeidAvsluttet": False}, "Oppstart": {"ForventetSluttdato": "2025-02-01T00:00:00Z"}},
        "2025-02"
    )
])
def test_appconfig_get_date(app_name, report_data, expected_date_start):
    config_map = {
        "regvil-2025-initiell": {
            "visibleAfter": "2025-07-17T00:00:00Z",
            "timedelta_visibleAfter": None
        },
        "regvil-2025-oppstart": {
            "visibleAfter": None,
            "timedelta_visibleAfter": "P6M"
        },
        "regvil-2025-status": {
            "visibleAfter": None,
            "timedelta_visibleAfter": "P6M"
        }
    }

    app_cfg = APPConfig(
        app_name=app_name,
        visibleAfter=config_map[app_name]["visibleAfter"],
        timedelta_visibleAfter=config_map[app_name]["timedelta_visibleAfter"]
    )

    date = app_cfg.get_date(report_data)

    # Check basic format and value start
    assert isinstance(date, str)
    assert date.startswith(expected_date_start)
    assert "T" in date and date.endswith("Z")
