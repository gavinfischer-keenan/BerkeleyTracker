"""Tests for AIS NMEA parsing."""
from tracker.enrichment.mmsi_lookup import mmsi_to_flag, mmsi_to_type_hint


def test_us_mmsi_flag():
    assert mmsi_to_flag("366999999") == "US"
    assert mmsi_to_flag("338123456") == "US"
    assert mmsi_to_flag("369000001") == "US"


def test_panama_flag():
    assert mmsi_to_flag("351234567") == "PA"
    assert mmsi_to_flag("370123456") == "PA"


def test_uk_flag():
    assert mmsi_to_flag("232000001") == "GB"
    assert mmsi_to_flag("235123456") == "GB"


def test_unknown_mmsi():
    assert mmsi_to_flag("999999999") is None
    assert mmsi_to_flag("") is None
    assert mmsi_to_flag("123") is None


def test_ship_station_type():
    assert mmsi_to_type_hint("366999999") == "ship_station"


def test_coast_station_type():
    assert mmsi_to_type_hint("003669999") == "coast_station"


def test_sar_aircraft_type():
    assert mmsi_to_type_hint("111366999") == "sar_aircraft"


def test_mob_device_type():
    assert mmsi_to_type_hint("972000001") == "mob_device"
