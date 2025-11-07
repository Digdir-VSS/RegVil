import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
from send_reminders import get_latest_notification_date, check_instance_active, run

@pytest.fixture
def mock_blob_data():
    """Fixture with fake blob 'sent_time' values."""
    now = datetime.now(timezone.utc)
    return [
        {"sent_time": (now - timedelta(days=15)).isoformat(), "event_type": "Varsling1Send"},
        {"sent_time": (now - timedelta(days=30)).isoformat(), "event_type": "Varsling1Send"},
    ]


def test_get_latest_notification_date_parses_times(mock_blob_data):
    """Ensure get_latest_notification_date parses blob sent_time correctly."""
    with patch("send_reminders.list_blobs_with_prefix", return_value=["blob1", "blob2"]), \
         patch("send_reminders.read_blob", side_effect=mock_blob_data):
        result = get_latest_notification_date(["tag1"], "myapp")
        assert len(result) == 2
        assert all(isinstance(dt, datetime) for dt in result)
        assert max(result) > min(result)


@pytest.mark.parametrize(
    "instance_meta, tag, expected",
    [
        ({"isHardDeleted": True}, ["tag"], False),
        ({"isSoftDeleted": True}, ["tag"], False),
        ({"isHardDeleted": False, "isSoftDeleted": False}, [], False),
        ({"isHardDeleted": False, "isSoftDeleted": False}, ["tag"], True),
    ]
)
def test_check_instance_active(instance_meta, tag, expected):
    """Test different deletion/tag conditions."""
    result = check_instance_active("instance123", instance_meta, tag)
    assert result is expected


def test_run_sends_warning_only_when_conditions_met(tmp_path):
    """Test run() flow with everything mocked to trigger send_warning."""
    fake_instance_meta = {
        "data": {},
        "visibleAfter": (datetime.now(timezone.utc) - timedelta(days=20)).isoformat().replace("+00:00", "Z"),
        "createdBy": "user1", "lastChangedBy": "user1",
        "isHardDeleted": False,
        "isSoftDeleted": False,
    }
    fake_data = {"Prefill": {"AnsvarligVirksomhet": {"Organisasjonsnummer": "123456789"}}}

    mock_client = MagicMock()
    mock_client.get_stored_instances_ids.return_value = [{"instanceId": "123/456"}]
    mock_client.get_instance.return_value.status_code = 200
    mock_client.get_instance.return_value.json.return_value = fake_instance_meta
    mock_client.get_instance_data.return_value.status_code = 200
    mock_client.get_instance_data.return_value.json.return_value = fake_data

    with patch("send_reminders.apps", ["regvil-2025-initiell"]), \
         patch("send_reminders.load_full_config", return_value={"dummy": "config"}), \
         patch("send_reminders.AltinnInstanceClient.init_from_config", return_value=mock_client), \
         patch("send_reminders.get_meta_data_info", return_value={"id": "dataguid", "tags": ["tag1"],  "created": (datetime.now(timezone.utc) - timedelta(days=20)).isoformat().replace("+00:00", "Z")}), \
         patch("send_reminders.list_blobs_with_prefix", return_value=[]), \
         patch("send_reminders.read_blob", return_value={}), \
         patch("send_reminders.get_latest_notification_date", return_value=[datetime.now(timezone.utc) - timedelta(days=20)]), \
         patch("send_reminders.send_warning") as mock_send:
        result, status_code = run()
        assert result == [{'org_number': '123456789', 'party_id': '123', 'instance_id': '456', 'org_name': None, 'digitaliseringstiltak_report_id': 'tag1', 'dato': datetime.now(timezone.utc).strftime("%Y-%m-%d"), 'app_name': 'regvil-2025-initiell'}]
        assert status_code == 201
        mock_send.assert_called_once()


def test_run_skips_when_recent_notification():
    """Ensure run() skips sending if last notification < 14 days ago."""
    now = datetime.now(timezone.utc)
    recent_time = (now - timedelta(days=5)).isoformat()
    fake_instance_meta = {
        "data": {},
        "visibleAfter": (now - timedelta(days=20)).isoformat().replace("+00:00", "Z"),
        "status": {"createdBy": "user1", "lastChangedBy": "user1"},
        "isHardDeleted": False,
        "isSoftDeleted": False,
    }
    fake_data = {"Prefill": {"AnsvarligVirksomhet": {"Organisasjonsnummer": "123456789"}}}

    mock_client = MagicMock()
    mock_client.get_stored_instances_ids.return_value = [{"instanceId": "123/456"}]
    mock_client.get_instance.return_value.status_code = 200
    mock_client.get_instance.return_value.json.return_value = fake_instance_meta
    mock_client.get_instance_data.return_value.status_code = 200
    mock_client.get_instance_data.return_value.json.return_value = fake_data

    with patch("send_reminders.load_full_config", return_value={"dummy": "config"}), \
         patch("send_reminders.AltinnInstanceClient.init_from_config", return_value=mock_client), \
         patch("send_reminders.get_meta_data_info", return_value={"id": "dataguid", "tags": ["tag1"],"created": (now - timedelta(days=20)).isoformat().replace("+00:00", "Z")}), \
         patch("send_reminders.list_blobs_with_prefix", return_value=["blob1"]), \
         patch("send_reminders.read_blob", return_value={"sent_time": recent_time, "event_type": "Varsling1Send"}), \
         patch("send_reminders.send_warning") as mock_send:
        result, status_code = run()
        assert result == []
        assert status_code == 200
        mock_send.assert_not_called()