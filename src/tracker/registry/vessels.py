"""Vessel registry — CRUD + sighting logic."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import json
from typing import Any

import structlog

from tracker.registry.db import TrackerDB

log = structlog.get_logger(__name__)


class VesselRegistry:
    def __init__(self, db: TrackerDB) -> None:
        self.db = db

    def upsert_sighting(
        self, mmsi: str, lat: float | None = None, lng: float | None = None,
        speed_kts: float | None = None, heading: float | None = None,
        name: str | None = None, vessel_type: int | None = None,
        flag: str | None = None, callsign: str | None = None,
    ) -> bool:
        now = datetime.now(timezone.utc).isoformat()

        existing = self.get(mmsi)
        if existing:
            updates: dict[str, Any] = {"last_seen": now, "sighting_count": existing["sighting_count"] + 1}
            if name and name.strip():
                updates["name"] = name.strip()
            if vessel_type:
                updates["vessel_type"] = vessel_type
            if flag:
                updates["flag"] = flag
            if callsign:
                updates["callsign"] = callsign
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            self.db.execute(f"UPDATE vessels SET {set_clause} WHERE mmsi = ?",
                            (*updates.values(), mmsi))
            is_new = False
        else:
            self.db.execute(
                "INSERT INTO vessels (mmsi, name, vessel_type, flag, callsign, "
                "first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (mmsi, (name or "").strip(), vessel_type or 0,
                 flag or "", (callsign or "").strip(), now, now))
            is_new = True
            log.info("vessel.new", mmsi=mmsi, name=name)

        if lat is not None and lng is not None:
            self.db.execute(
                "INSERT INTO positions (craft_type, craft_id, timestamp, lat, lng, "
                "speed_kts, heading) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("vessel", mmsi, now, lat, lng, speed_kts, heading))

        return is_new

    def get(self, mmsi: str) -> dict[str, Any] | None:
        row = self.db.query_one("SELECT * FROM vessels WHERE mmsi = ?", (mmsi,))
        return dict(row) if row else None

    def get_all_visible(self, since_minutes: int = 10) -> list[dict]:
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=since_minutes)).isoformat()
        rows = self.db.query("SELECT * FROM vessels WHERE last_seen >= ? ORDER BY last_seen DESC", (cutoff,))
        return [dict(r) for r in rows]

    def get_history(self, mmsi: str, hours: int = 24) -> list[dict]:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        rows = self.db.query(
            "SELECT * FROM positions WHERE craft_type = 'vessel' AND craft_id = ? "
            "AND timestamp >= ? ORDER BY timestamp", (mmsi, cutoff))
        return [dict(r) for r in rows]

    def get_most_seen(self, limit: int = 50) -> list[dict]:
        rows = self.db.query("SELECT * FROM vessels ORDER BY sighting_count DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    def search(self, query: str) -> list[dict]:
        q = f"%{query}%"
        rows = self.db.query(
            "SELECT * FROM vessels WHERE mmsi LIKE ? OR name LIKE ? "
            "OR callsign LIKE ? OR flag LIKE ? LIMIT 50", (q, q, q, q))
        return [dict(r) for r in rows]

    def mark_enriched(self, mmsi: str, data: dict) -> None:
        self.db.execute(
            "UPDATE vessels SET enriched = 1, vessel_type_desc = ?, data = ? WHERE mmsi = ?",
            (data.get("type_desc", ""), json.dumps(data), mmsi))

    def get_unenriched(self, limit: int = 10) -> list[dict]:
        rows = self.db.query("SELECT * FROM vessels WHERE enriched = 0 LIMIT ?", (limit,))
        return [dict(r) for r in rows]
