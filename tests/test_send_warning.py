import pytest
from unittest.mock import MagicMock
from datetime import datetime, timedelta, timezone
import os

from send_warning import run  # adjust to your actual filename


@pytest.fixture
def monkeypatch_env(monkeypatch):
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("MASKINPORTEN_SECRET_VAULT_URL", "https://mock.vault.azure.net/")
    monkeypatch.setenv("MASKINPORTEN_SECRET_NAME", "mock-secret")


def test_run_success(monkeypatch, monkeypatch_env):
    # Mock load_full_config
    mock_config = MagicMock()
    mock_config.app_config.emailSubject = "Test Subject"
    mock_config.app_config.emailBody = "Test Body"
    monkeypatch.setattr("upload_notification.load_full_config", lambda path, app_name, env: mock_config)

    # Mock AltinnVarslingClient
    mock_varsling_client = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {
        "notification": {
            "shipmentId": "shipment-123"
        }
    }
    mock_varsling_client.send_notification.return_value = mock_response
    monkeypatch.setattr("upload_notification.AltinnVarslingClient.init_from_config", lambda config: mock_varsling_client)

    # Mock InstanceTracker
    mock_tracker = MagicMock()
    monkeypatch.setattr("upload_notification.InstanceTracker.from_directory", lambda _: mock_tracker)

    # Mock SecretClient (to avoid actual Azure calls)
    monkeypatch.setattr("upload_notification.SecretClient", lambda vault_url, credential: MagicMock(
        get_secret=lambda name: MagicMock(value="dummy-secret")
    ))
    monkeypatch.setattr("upload_notification.DefaultAzureCredential", lambda: MagicMock())

    # Prefill test data
    prefill_data = {
        "Initiell": {
            "Kontaktperson": {"EPostadresse": "user@example.com"},
            "AnsvarligVirksomhet": {"Navn": "Test Org"}
        }
    }

    # Future date
    dato = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    # Run the test
    status = run(
        org_number="123456789",
        digitaliseringstiltak_report_id="report-001",
        dato=dato,
        app_name="regvil-2025-initiell",
        prefill_data=prefill_data
    )

    assert status == 200
    mock_varsling_client.send_notification.assert_called_once()
    mock_tracker.logging_varlsing.assert_called_once()


def test_run_failure_on_response(monkeypatch, monkeypatch_env):
    # Setup same as above but simulate a failed request
    mock_config = MagicMock()
    mock_config.app_config.emailSubject = "Test Subject"
    mock_config.app_config.emailBody = "Test Body"
    monkeypatch.setattr("upload_notification.load_full_config", lambda path, app_name, env: mock_config)

    mock_varsling_client = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    mock_varsling_client.send_notification.return_value = mock_response
    monkeypatch.setattr("upload_notification.AltinnVarslingClient.init_from_config", lambda config: mock_varsling_client)

    monkeypatch.setattr("upload_notification.InstanceTracker.from_directory", lambda _: MagicMock())
    monkeypatch.setattr("upload_notification.SecretClient", lambda vault_url, credential: MagicMock(
        get_secret=lambda name: MagicMock(value="dummy-secret")
    ))
    monkeypatch.setattr("upload_notification.DefaultAzureCredential", lambda: MagicMock())

    prefill_data = {
        "Initiell": {
            "Kontaktperson": {"EPostadresse": "user@example.com"},
            "AnsvarligVirksomhet": {"Navn": "Test Org"}
        }
    }

    dato = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    status = run(
        org_number="123456789",
        digitaliseringstiltak_report_id="report-001",
        dato=dato,
        app_name="regvil-2025-initiell",
        prefill_data=prefill_data
    )

    assert status == 500 or status == 206
