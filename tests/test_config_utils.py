import pytest
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta

from config.config_loader import load_full_config
from config.utils import add_time_delta, check_date_before, get_initiell_date, get_oppstart_date, get_status_date, to_utc_aware, parse_date

def test_add_time_delta():
    base_date_str = "2025-07-22T12:59:42.6342741Z"
    timedelta_str = "P1M"
    result = add_time_delta(base_date_str, timedelta_str)
    assert result == "2025-08-22T12:59:42.634274Z"
    
    base_date_str = "2025-07-22T12:59:42.6342741Z"
    timedelta_str = "P0M"
    result = add_time_delta(base_date_str, timedelta_str)
    assert result == "2025-07-22T12:59:42.634274Z"
    
    base_date_str = "2025-07-22T12:59:42.6342741Z"
    timedelta_str = "PT15M"
    result = add_time_delta(base_date_str, timedelta_str)
    assert result == "2025-07-22T13:14:42.634274Z"

    base_date_str = "2025-07-22T12:59:42.6342741Z"
    timedelta_str = "-P1D"
    result = add_time_delta(base_date_str, timedelta_str)
    assert result == "2025-07-21T12:59:42.634274Z"

    base_date_str = "2025-07-22T12:59:42.6342741Z"
    timedelta_str = "-P1D"
    result = add_time_delta(base_date_str, timedelta_str)
    assert result == "2025-07-21T12:59:42.634274Z"

    ValueError("Timedelta string is empty")

    base_date_str = "2025-07-22T12:59:42.6342741Z"
    timedelta_str = ""
    with pytest.raises(ValueError, match="Timedelta string is empty"):
        add_time_delta(base_date_str, timedelta_str)
        base_date_str = "2025-07-22T12:59:42.6342741Z"
    
    timedelta_str = None
    with pytest.raises(ValueError, match="Timedelta string is empty"):
        add_time_delta(base_date_str, timedelta_str)


def test_check_date_before():
    ref_date_str = "2025-07-23T12:59:42.6342741Z"
    compare_date_str = "2025-07-22T12:59:42.6342741Z"
    result = check_date_before(ref_date_str, compare_date_str)
    assert result == False

    ref_date_str = "2025-07-21T12:59:42.6342741Z"
    compare_date_str = "2025-07-22T12:59:42.6342741Z"
    result = check_date_before(ref_date_str, compare_date_str)
    assert result == True

    ref_date_str = ""
    compare_date_str = "2025-07-22T12:59:42.6342741Z"
    with pytest.raises(ValueError, match="Reference date string is empty"):
        result = check_date_before(ref_date_str, compare_date_str)
    
    ref_date_str = "2025-07-21T12:59:42.6342741Z"
    compare_date_str = ""
    with pytest.raises(ValueError, match="Comapre date string is empty"):
        result = check_date_before(ref_date_str, compare_date_str)

def test_get_initiell_date_paabegynt(monkeypatch):
    reported_data = {
        "Initiell": {
            "ErTiltaketPaabegynt": True,
            "DatoPaabegynt": "2025-07-01T00:00:00Z"
        }
    }
    monkeypatch.setattr("config.utils.get_today_date", lambda: "2026-07-01T00:00:00Z")
    assert get_initiell_date(reported_data, "P3M") == "2026-10-01T00:00:00Z"

def test_get_initiell_date_forventet_oppstart():
    reported_data = {
        "Initiell": {
            "ErTiltaketPaabegynt": False,
            "DatoForventetOppstart": "2025-08-01T00:00:00Z"
        }
    }
    assert get_initiell_date(reported_data, "P3M") == "2025-08-01T00:00:00Z"

def test_get_status_date_finished(monkeypatch):
    reported_data = {
        "Status": {"ErArbeidAvsluttet": True},
        "Oppstart": {"ForventetSluttdato": "2025-12-01T00:00:00Z"}
    }
    monkeypatch.setattr("config.utils.get_today_date", lambda: "2025-07-24T00:00:00Z")
    assert get_status_date(reported_data, None) == "2025-07-24T00:00:00Z"

def test_get_status_date_not_finished():
    reported_data = {
        "Status": {"ErArbeidAvsluttet": False},
        "Oppstart": {"ForventetSluttdato": "2025-12-01T00:00:00Z"}
    }
    assert get_status_date(reported_data, None) == "2025-12-01T00:00:00Z"

def test_get_oppstart_date_negative_delta_triggers_today(monkeypatch):
    reported_data = {
        "Oppstart": {
            "ForventetSluttdato": "2025-01-01T00:00:00Z"
        }
    }

    # Simulate today being after the delta-adjusted date
    monkeypatch.setattr("config.utils.get_today_date", lambda: "2025-07-24T00:00:00Z")
    monkeypatch.setattr("config.utils.add_time_delta", lambda d, td: "2024-12-18T00:00:00Z")  # 14 days before
    monkeypatch.setattr("config.utils.check_date_before", lambda d1, d2: True)

    result = get_oppstart_date(reported_data, "-P14D")
    assert result == "2025-07-24T00:00:00Z"

def test_get_oppstart_date_negative_delta_still_future(monkeypatch):
    reported_data = {
        "Oppstart": {
            "ForventetSluttdato": "2025-08-10T00:00:00Z"
        }
    }

    monkeypatch.setattr("config.utils.get_today_date", lambda: "2025-07-24T00:00:00Z")
    monkeypatch.setattr("config.utils.add_time_delta", lambda d, td: "2024-07-27T00:00:00Z")  # still in future
    monkeypatch.setattr("config.utils.check_date_before", lambda d1, d2: True)

    result = get_oppstart_date(reported_data, None)
    assert result == "2025-07-24T00:00:00Z"


def test_load_full_config(monkeypatch):
    # Arrange
    monkeypatch.setenv("ENV", "test")  # if your test ENV folder is `config_files/test/`
    app_name = "regvil-2025-oppstart"  # update as needed
    config_path = Path(__file__).parent.parent / "config_files"

    # Act
    oppstart_config = load_full_config(config_path, app_name, os.getenv("ENV"))

    # Assert
    assert oppstart_config is not None

    # App-level checks
    assert hasattr(oppstart_config, "app_config")
    assert oppstart_config.app_config.app_name == app_name
    assert "tag_instance" in oppstart_config.app_config.tag
    assert "tag_download" in oppstart_config.app_config.tag
    assert oppstart_config.app_config.tag["tag_instance"] == "OppstartSkjemaLevert"
    assert oppstart_config.app_config.tag["tag_download"] == "OppstartSkjemaDownloaded"

    # Maskinporten client config
    assert hasattr(oppstart_config, "maskinporten_config_instance")
    assert isinstance(oppstart_config.maskinporten_config_instance.client_id, str)
    assert isinstance(oppstart_config.maskinporten_config_instance.kid, str)

    # DAG check
    assert hasattr(oppstart_config, "workflow_dag")
    assert oppstart_config.workflow_dag.get_next(app_name) == "regvil-2025-status" 

    # Optional date delta logic
    assert hasattr(oppstart_config.app_config, "timedelta_visibleAfter")
    assert oppstart_config.app_config.timedelta_visibleAfter == "P6M"
    assert oppstart_config.app_config.visibleAfter == None

    app_name = "regvil-2025-initiell"  # update as needed
    # Act
    initiell_config = load_full_config(config_path, app_name, os.getenv("ENV"))
        # App-level checks
    assert initiell_config.app_config.tag["tag_instance"] == "InitiellSkjemaLevert"
    assert initiell_config.app_config.tag["tag_download"] == "InitiellSkjemaDownloaded"

    # DAG check
    assert initiell_config.workflow_dag.get_next(app_name) == "regvil-2025-oppstart" 

    # date delta logic
    assert hasattr(initiell_config.app_config, "timedelta_visibleAfter")
    assert initiell_config.app_config.timedelta_visibleAfter == "P6M"
    assert initiell_config.app_config.timedelta_dueBefore == None
    assert initiell_config.app_config.visibleAfter == "2025-07-17T00:00:00Z"
    assert initiell_config.app_config.dueBefore == "2025-09-01T12:00:00Z"

    app_name = "regvil-2025-status"  # update as needed
    # Act
    status_config = load_full_config(config_path, app_name, os.getenv("ENV"))
        # App-level checks
    assert status_config.app_config.tag["tag_instance"] == "StatusSkjemaLevert"
    assert status_config.app_config.tag["tag_download"] == "StatusSkjemaDownloaded"

    # DAG check
    assert status_config.workflow_dag.get_next(app_name) == "regvil-2025-slutt" 

    # date delta logic
    assert hasattr(status_config.app_config, "timedelta_visibleAfter")
    assert status_config.app_config.timedelta_visibleAfter == "P6M"
    assert status_config.app_config.visibleAfter == None
    assert status_config.app_config.visibleAfter == None


    app_name = "regvil-2025-slutt"  # update as needed
    # Act
    slutt_config = load_full_config(config_path, app_name, os.getenv("ENV"))

        # App-level checks
    assert slutt_config.app_config.tag["tag_instance"] == "SluttSkjemaLevert"
    assert slutt_config.app_config.tag["tag_download"] == "SluttSkjemaDownloaded"

    # DAG check
    assert status_config.workflow_dag.get_next(app_name) == None

    # date delta logic
    assert hasattr(slutt_config.app_config, "timedelta_visibleAfter")
    assert slutt_config.app_config.timedelta_visibleAfter == None
    assert slutt_config.app_config.visibleAfter == None
    assert slutt_config.app_config.visibleAfter == None


def test_to_utc_aware_returns_aware_datetime():
    iso_str = "2025-07-28T15:00:00Z"
    dt = to_utc_aware(iso_str)

    assert isinstance(dt, datetime)
    assert dt.tzinfo is not None
    assert dt.tzinfo.utcoffset(dt) == timezone.utc.utcoffset(dt)

def test_check_date_before_comparison_with_aware_datetimes():
    earlier = "2025-07-28T14:00:00Z"
    later = "2025-07-28T15:00:00Z"

    # Should not raise and should return True
    result = check_date_before(earlier, later)
    assert result is True

    # Reverse comparison
    result = check_date_before(later, earlier)
    assert result is False




test_dates = [
    ("2025-08-18T11:49:43.3529573Z", datetime(2025, 8, 18, 0, 0, tzinfo=timezone.utc)),
    ("2025-08-14T00:00:00Z", datetime(2025, 8, 14, 0, 0, tzinfo=timezone.utc)),
    ("2025-08-06T11:05:12.5883858Z", datetime(2025, 8, 6, 0, 0, tzinfo=timezone.utc)),
    (datetime.now(timezone.utc).strftime("%Y-%m-%d"),
     datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0))
]
@pytest.mark.parametrize("date, expected", test_dates)
def test_parse_date_returns_utc_aware_datetime(date, expected):
    result = parse_date(date)
    assert result.date() == expected.date()
    assert result.tzinfo is not None
    assert result.tzinfo.utcoffset(result) == timedelta(0)
    assert result.hour == 0


@pytest.mark.parametrize("invalid_date", [
    "",                    # Empty string
    None,                  # None input
    "invalid-date",        # Non-date string
    "2025/08/06",          # Wrong delimiter
    "06-08-2025",          # Wrong format
    "2025-13-40",          # Impossible date
    "2025-08",             # Missing day
])
def test_parse_date_invalid_inputs(invalid_date):
    """Ensure parse_date raises ValueError for invalid or missing inputs."""
    with pytest.raises(ValueError):
        parse_date(invalid_date)
