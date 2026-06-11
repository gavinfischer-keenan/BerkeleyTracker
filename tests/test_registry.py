"""Tests for aircraft and vessel registry CRUD."""
from tracker.registry.aircraft import AircraftRegistry
from tracker.registry.vessels import VesselRegistry
from tracker.registry.photos import PhotoManager


def test_aircraft_first_sighting(tmp_db):
    reg = AircraftRegistry(tmp_db)
    is_new = reg.upsert_sighting("A0B1C2", lat=37.8, lng=-122.3,
                                  altitude_ft=35000, callsign="UAL1234")
    assert is_new is True

    craft = reg.get("A0B1C2")
    assert craft is not None
    assert craft["icao_hex"] == "A0B1C2"
    assert craft["callsign_last"] == "UAL1234"
    assert craft["sighting_count"] == 1


def test_aircraft_repeat_sighting(tmp_db):
    reg = AircraftRegistry(tmp_db)
    reg.upsert_sighting("A0B1C2", lat=37.8, lng=-122.3, callsign="UAL1234")
    is_new = reg.upsert_sighting("A0B1C2", lat=37.81, lng=-122.31)
    assert is_new is False

    craft = reg.get("A0B1C2")
    assert craft["sighting_count"] == 2


def test_aircraft_case_insensitive(tmp_db):
    reg = AircraftRegistry(tmp_db)
    reg.upsert_sighting("a0b1c2", lat=37.8, lng=-122.3)
    craft = reg.get("A0B1C2")
    assert craft is not None


def test_aircraft_most_seen(tmp_db):
    reg = AircraftRegistry(tmp_db)
    for i in range(5):
        reg.upsert_sighting("AAAA01", lat=37.8, lng=-122.3)
    for i in range(3):
        reg.upsert_sighting("BBBB02", lat=37.8, lng=-122.3)

    top = reg.get_most_seen(limit=2)
    assert len(top) == 2
    assert top[0]["icao_hex"] == "AAAA01"


def test_vessel_first_sighting(tmp_db):
    reg = VesselRegistry(tmp_db)
    is_new = reg.upsert_sighting("366000001", lat=37.8, lng=-122.3,
                                  name="SF FERRY", vessel_type=60, flag="US")
    assert is_new is True

    vessel = reg.get("366000001")
    assert vessel["name"] == "SF FERRY"
    assert vessel["flag"] == "US"


def test_vessel_updates_name(tmp_db):
    reg = VesselRegistry(tmp_db)
    reg.upsert_sighting("366000001", name="FERRY")
    reg.upsert_sighting("366000001", name="SF BAY FERRY")

    vessel = reg.get("366000001")
    assert vessel["name"] == "SF BAY FERRY"
    assert vessel["sighting_count"] == 2


def test_aircraft_search(tmp_db):
    reg = AircraftRegistry(tmp_db)
    reg.upsert_sighting("A0B1C2", callsign="UAL1234")
    reg.mark_enriched("A0B1C2", {
        "registration": "N12345",
        "type_code": "B738",
        "type_desc": "Boeing 737-800",
        "operator": "United Airlines",
    })

    results = reg.search("United")
    assert len(results) == 1
    assert results[0]["operator"] == "United Airlines"


def test_vessel_search(tmp_db):
    reg = VesselRegistry(tmp_db)
    reg.upsert_sighting("366000001", name="GOLDEN GATE FERRY", flag="US")

    results = reg.search("GOLDEN")
    assert len(results) == 1
    assert results[0]["name"] == "GOLDEN GATE FERRY"
