"""Route learning — pattern detection from position traces."""
from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog

from tracker.registry.db import TrackerDB

log = structlog.get_logger(__name__)


def _haversine_nm(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in nautical miles."""
    R_NM = 3440.065
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R_NM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class RouteManager:
    def __init__(self, db: TrackerDB, corridor_tolerance_nm: float = 0.5) -> None:
        self.db = db
        self.tolerance = corridor_tolerance_nm

    def record_trace(self, craft_type: str, craft_id: str, positions: list[dict]) -> str | None:
        """Called when a craft disappears. Returns route_id if matched or created."""
        if len(positions) < 10:
            return None

        trace = [(p["lat"], p["lng"]) for p in positions if p.get("lat") and p.get("lng")]
        total_dist = sum(_haversine_nm(*trace[i], *trace[i + 1]) for i in range(len(trace) - 1))
        if total_dist < 2.0:
            return None  # too short to be a meaningful route

        # Try to match existing routes
        match = self.find_matching_route(craft_type, trace)
        if match:
            self._update_route(match["route_id"], craft_id)
            return match["route_id"]

        # Create new candidate route
        return self.create_route(craft_type, trace, craft_id)

    def find_matching_route(self, craft_type: str, trace: list[tuple[float, float]]) -> dict | None:
        routes = self.get_all_routes(craft_type)
        for route in routes:
            waypoints = json.loads(route.get("waypoints", "[]"))
            if not waypoints:
                continue
            if self._trace_matches_corridor(trace, waypoints):
                return route
        return None

    def _trace_matches_corridor(self, trace: list[tuple], waypoints: list[dict]) -> bool:
        """Check if trace follows the waypoint corridor within tolerance."""
        wp_points = [(w["lat"], w["lng"]) for w in waypoints]
        if not wp_points or not trace:
            return False

        # Sample 10 evenly-spaced points from trace
        step = max(1, len(trace) // 10)
        samples = trace[::step][:10]

        matches = 0
        for slat, slng in samples:
            min_dist = min(_haversine_nm(slat, slng, wlat, wlng) for wlat, wlng in wp_points)
            if min_dist <= self.tolerance:
                matches += 1

        return matches >= len(samples) * 0.7  # 70% of samples must be in corridor

    def create_route(self, craft_type: str, trace: list[tuple], craft_id: str) -> str:
        route_id = f"route-{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()

        # Downsample trace to ~20 waypoints
        step = max(1, len(trace) // 20)
        waypoints = [{"lat": t[0], "lng": t[1]} for t in trace[::step]]

        self.db.execute(
            "INSERT INTO routes (route_id, craft_type, waypoints, craft_ids, "
            "first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?)",
            (route_id, craft_type, json.dumps(waypoints),
             json.dumps([craft_id]), now, now))

        log.info("route.candidate_created", route_id=route_id, craft_type=craft_type,
                 waypoints=len(waypoints))
        return route_id

    def _update_route(self, route_id: str, craft_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        route = self.get_route(route_id)
        if not route:
            return

        craft_ids = json.loads(route.get("craft_ids", "[]"))
        if craft_id not in craft_ids:
            craft_ids.append(craft_id)

        self.db.execute(
            "UPDATE routes SET last_seen = ?, sighting_count = sighting_count + 1, "
            "craft_ids = ? WHERE route_id = ?",
            (now, json.dumps(craft_ids), route_id))

        log.info("route.sighting", route_id=route_id, count=route["sighting_count"] + 1)

    def promote_candidates(self, min_sightings: int = 3) -> list[str]:
        """Promote candidate routes (not yet scheduled) with enough sightings."""
        rows = self.db.query(
            "SELECT * FROM routes WHERE is_scheduled = 0 AND sighting_count >= ?",
            (min_sightings,))
        promoted = []
        for row in rows:
            self.db.execute("UPDATE routes SET is_scheduled = 1 WHERE route_id = ?",
                            (row["route_id"],))
            promoted.append(row["route_id"])
            log.info("route.promoted", route_id=row["route_id"], sightings=row["sighting_count"])
        return promoted

    def get_all_routes(self, craft_type: str | None = None) -> list[dict]:
        if craft_type:
            rows = self.db.query("SELECT * FROM routes WHERE craft_type = ? ORDER BY sighting_count DESC",
                                  (craft_type,))
        else:
            rows = self.db.query("SELECT * FROM routes ORDER BY sighting_count DESC")
        return [dict(r) for r in rows]

    def get_route(self, route_id: str) -> dict[str, Any] | None:
        row = self.db.query_one("SELECT * FROM routes WHERE route_id = ?", (route_id,))
        return dict(row) if row else None
