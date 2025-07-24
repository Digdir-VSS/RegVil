import pytest

from config.utils import add_time_delta, check_date_before, get_initiell_date, get_oppstart_date, get_status_date

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

def test_get_initiell_date_paabegynt():
    reported_data = {
        "Initiell": {
            "ErTiltaketPaabegynt": True,
            "DatoPaabegynt": "2025-07-01T00:00:00Z"
        }
    }
    assert get_initiell_date(reported_data, None) == "2025-07-01T00:00:00Z"

def test_get_initiell_date_forventet_oppstart():
    reported_data = {
        "Initiell": {
            "ErTiltaketPaabegynt": False,
            "VetOppstartsDato": True,
            "DatoForventetOppstart": "2025-08-01T00:00:00Z"
        }
    }
    assert get_initiell_date(reported_data, None) == "2025-08-01T00:00:00Z"

def test_get_initiell_date_fallback_to_today(monkeypatch):
    reported_data = {
        "Initiell": {
            "ErTiltaketPaabegynt": False,
            "VetOppstartsDato": False
        }
    }
    monkeypatch.setattr("config.utils.get_today_date", lambda: "2025-07-24T12:00:00Z")
    assert get_initiell_date(reported_data, None) == "2025-07-24T12:00:00Z"
    

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
    monkeypatch.setattr("config.utils.add_time_delta", lambda d, td: "2025-07-27T00:00:00Z")  # still in future
    monkeypatch.setattr("config.utils.check_date_before", lambda d1, d2: False)

    result = get_oppstart_date(reported_data, "-P14D")
    assert result == "2025-07-27T00:00:00Z"
