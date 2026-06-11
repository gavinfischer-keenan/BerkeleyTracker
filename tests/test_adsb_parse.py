"""Tests for ADS-B SBS message parsing."""
from tracker.sdr.adsb_ingest import parse_sbs_message


def test_parse_msg3_position():
    """MSG type 3 = airborne position with lat/lng/altitude."""
    line = "MSG,3,1,1,A0B1C2,1,2024/01/15,12:30:00.000,2024/01/15,12:30:00.000,,35000,,,37.8751,-122.2697,,,,,,0"
    result = parse_sbs_message(line)
    assert result is not None
    assert result["icao_hex"] == "A0B1C2"
    assert result["msg_type"] == 3
    assert result["altitude_ft"] == 35000.0
    assert abs(result["lat"] - 37.8751) < 0.001
    assert abs(result["lng"] - (-122.2697)) < 0.001


def test_parse_msg1_identification():
    """MSG type 1 = identification (callsign)."""
    line = "MSG,1,1,1,A0B1C2,1,2024/01/15,12:30:01.000,2024/01/15,12:30:01.000,UAL1234,,,,,,,,,,,,"
    result = parse_sbs_message(line)
    assert result is not None
    assert result["icao_hex"] == "A0B1C2"
    assert result["msg_type"] == 1
    assert result["callsign"] == "UAL1234"


def test_parse_msg4_velocity():
    """MSG type 4 = airborne velocity."""
    line = "MSG,4,1,1,A0B1C2,1,2024/01/15,12:30:03.000,2024/01/15,12:30:03.000,,,450,,,,12345,,,,,"
    result = parse_sbs_message(line)
    assert result is not None
    assert result["msg_type"] == 4
    assert result["speed_kts"] == 450.0


def test_parse_empty_line():
    result = parse_sbs_message("")
    assert result is None


def test_parse_garbage():
    result = parse_sbs_message("this is not an SBS message")
    assert result is None
