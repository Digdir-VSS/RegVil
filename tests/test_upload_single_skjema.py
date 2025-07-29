import pytest
from pathlib import Path
import os
from unittest.mock import MagicMock
import json

from upload_single_skjema import create_payload  # adjust import if needed
from config.config_loader import load_full_config
from upload_single_skjema import run


def test_run_success(monkeypatch):
    # Mock the config loader
    monkeypatch.setattr("upload_skjema.load_full_config", lambda path, app_name, env: MagicMock(
        app_config=MagicMock(
            app_name="regvil-2025-initiell",
            tag={"tag_instance": "InitiellSkjemaLevert"}
        )
    ))

    # Mock AltinnInstanceClient
    mock_client = MagicMock()
    mock_instance_response = MagicMock()
    mock_instance_response.status_code = 201
    mock_instance_response.json.return_value = {
        "id": "51625403/abc123",
        "instanceOwner": {"partyId": "51625403"},
        "data": [{"id": "data-guid-123", "dataType": "DataModel","contentType": "application/json"}],
    }
    mock_tag_response = MagicMock()
    mock_tag_response.status_code = 201

    mock_client.post_new_instance.return_value = mock_instance_response
    mock_client.tag_instance_data.return_value = mock_tag_response
    mock_client.instance_created.return_value = False

    monkeypatch.setattr("upload_skjema.AltinnInstanceClient.init_from_config", lambda config: mock_client)

    # Mock instance tracker
    mock_tracker = MagicMock()
    mock_tracker.has_processed_instance.return_value = False
    monkeypatch.setattr("upload_skjema.InstanceTracker.from_directory", lambda _: mock_tracker)

    # Mock get_meta_data_info
    monkeypatch.setattr("upload_skjema.get_meta_data_info", lambda data: {"id": "data-guid-123"})

    # Run the function with test data
    run(
        org_number="51625403",
        digitaliseringstiltak_report_id="test-report-001",
        dato="2025-08-01T00:00:00Z",
        app_name="regvil-2025-initiell",
        prefill_data={"some": "data"}
    )

    # Assert calls were made (optional, depending on your test strictness)
    mock_client.post_new_instance.assert_called()
    mock_client.tag_instance_data.assert_called()
    mock_tracker.logging_instance.assert_called()


def test_create_payload():
    # Sample inputs
    org_number = "123456789"
    dato = "2025-08-01T00:00:00Z"
    prefill_data = {"Initiell": {"ErTiltaketPaabegynt": True}}

    app_name = "regvil-2025-initiell"  # update as needed
    config_path = Path(__file__).parent.parent / "config_files"

    config = load_full_config(config_path, app_name, os.getenv("ENV"))

    result = create_payload(org_number, dato, config, prefill_data)

    # Check output structure
    assert isinstance(result, dict)
    assert "instance" in result
    assert "DataModel" in result

    # Validate each file tuple
    for key in ["instance", "DataModel"]:
        filename, content, content_type = result[key]
        assert filename.endswith(".json")
        assert content_type == "application/json"
        # Should be valid JSON
        json.loads(content)

    # Specific content checks
    instance_content = json.loads(result["instance"][1])
    assert instance_content["instanceOwner"]["organisationNumber"] == org_number
    assert instance_content["visibleAfter"] == dato

    datamodel_content = json.loads(result["DataModel"][1])
    assert datamodel_content == prefill_data
