"""Aircraft registry — CRUD + sighting logic."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog

from tracker.registry.db import TrackerDB

log = structlog.get_logger(__name__)


class AircraftRegistry:
    def __init__(self, db: TrackerDB) -> None:
        self.db = db

    def upsert_sighting(
        self, icao_hex: str, lat: float | None = None, lng: float | None = None,
        altitude_ft: float | None = None, speed_kts: float | None = None,
        heading: float | None = None, callsign: str | None = None,
    ) -> bool:
        """Create or update aircraft. Returns True if this is a new aircraft."""
        now = datetime.now(timezone.utc).isoformat()
        icao = icao_hex.upper()

        existing = self.get(icao)
        if existing:
            updates = {"last_seen": now, "sighting_count": existing["sighting_count"] + 1}
            if callsign and callsign.strip():
                updates["callsign_last"] = callsign.strip()
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            self.db.execute(f"UPDATE aircraft SET {set_clause} WHERE icao_hex = ?",
                            (*updates.values(), icao))
            is_new = False
        else:
            self.db.execute(
                "INSERT INTO aircraft (icao_hex, callsign_last, first_seen, last_seen) "
                "VALUES (?, ?, ?, ?)",
                (icao, (callsign or "").strip(), now, now))
            is_new = True
            log.info("aircraft.new", icao=icao, callsign=callsign)

        if lat is not None and lng is not None:
            self.db.execute(
                "INSERT INTO positions (craft_type, craft_id, timestamp, lat, lng, "
                "altitude_ft, speed_kts, heading) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("aircraft", icao, now, lat, lng, altitude_ft, speed_kts, heading))

        return is_new

    def get(self, icao_hex: str) -> dict[str, Any] | None:
        row = self.db.query_one("SELECT * FROM aircraft WHERE icao_hex = ?", (icao_hex.upper(),))
        return dict(row) if row else None

    def get_all_visible(self, since_minutes: int = 5) -> list[dict]:
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=since_minutes)).isoformat()
        rows = self.db.query("SELECT * FROM aircraft WHERE last_seen >= ? ORDER BY last_seen DESC", (cutoff,))
        return [dict(r) for r in rows]

    def get_history(self, icao_hex: str, hours: int = 24) -> list[dict]:
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        rows = self.db.query(
            "SELECT * FROM positions WHERE craft_type = 'aircraft' AND craft_id = ? "
            "AND timestamp >= ? ORDER BY timestamp", (icao_hex.upper(), cutoff))
        return [dict(r) for r in rows]

    def get_most_seen(self, limit: int = 50) -> list[dict]:
        rows = self.db.query("SELECT * FROM aircraft ORDER BY sighting_count DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    def search(self, query: str) -> list[dict]:
        q = f"%{query}%"
        rows = self.db.query(
            "SELECT * FROM aircraft WHERE icao_hex LIKE ? OR tail_number LIKE ? "
            "OR aircraft_type LIKE ? OR operator LIKE ? OR callsign_last LIKE ? LIMIT 50",
            (q, q, q, q, q))
        return [dict(r) for r in rows]

    def mark_enriched(self, icao_hex: str, data: dict) -> None:
        import json
        self.db.execute(
            "UPDATE aircraft SET enriched = 1, tail_number = ?, aircraft_type = ?, "
            "type_desc = ?, operator = ?, data = ? WHERE icao_hex = ?",
            (data.get("registration", ""), data.get("type_code", ""),
             data.get("type_desc", ""), data.get("operator", ""),
             json.dumps(data), icao_hex.upper()))

    def get_unenriched(self, limit: int = 10) -> list[dict]:
        rows = self.db.query("SELECT * FROM aircraft WHERE enriched = 0 LIMIT ?", (limit,))
        return [dict(r) for r in rows]
