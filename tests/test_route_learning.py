"""Tests for route learning — pattern detection and candidate promotion."""
from tracker.registry.routes import _haversine_nm, RouteManager


def test_haversine_known_distance():
    """SF to Oakland ~= 8 NM."""
    dist = _haversine_nm(37.7749, -122.4194, 37.8044, -122.2712)
    assert 6.0 < dist < 10.0


def test_haversine_same_point():
    dist = _haversine_nm(37.8, -122.3, 37.8, -122.3)
    assert dist < 0.001


def test_short_trace_rejected(tmp_db):
    """Traces with fewer than 10 points are rejected."""
    mgr = RouteManager(tmp_db)
    positions = [{"lat": 37.8 + i * 0.001, "lng": -122.3} for i in range(5)]
    result = mgr.record_trace("vessel", "366000001", positions)
    assert result is None


def test_new_route_created(tmp_db):
    """A trace with enough points and distance creates a candidate route."""
    mgr = RouteManager(tmp_db)
    # Create a trace from SF Bay to Golden Gate (~5 NM)
    positions = [
        {"lat": 37.78 + i * 0.005, "lng": -122.38 - i * 0.005}
        for i in range(15)
    ]
    result = mgr.record_trace("vessel", "366000001", positions)
    assert result is not None
    assert result.startswith("route-")

    # Verify it was stored
    route = mgr.get_route(result)
    assert route is not None
    assert route["craft_type"] == "vessel"


def test_route_promotion(tmp_db):
    """Routes with 3+ sightings get promoted to scheduled."""
    mgr = RouteManager(tmp_db)
    positions = [
        {"lat": 37.78 + i * 0.005, "lng": -122.38 - i * 0.005}
        for i in range(15)
    ]

    # First sighting
    route_id = mgr.record_trace("vessel", "366000001", positions)
    assert route_id is not None

    # Manually bump sighting count
    tmp_db.execute("UPDATE routes SET sighting_count = 3 WHERE route_id = ?", (route_id,))

    promoted = mgr.promote_candidates(min_sightings=3)
    assert route_id in promoted
