"""SQLite registry database.

Creates and manages the ``tracker.db`` database with tables for aircraft,
vessels, positions, routes, and photos.  Uses WAL journal mode and NORMAL
synchronous for performance, with a threading lock for safety.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

log = structlog.get_logger(__name__)

DEFAULT_DB_PATH = os.environ.get(
    "TRACKER_DB_PATH",
    str(Path(__file__).resolve().parent.parent.parent.parent / "data" / "tracker.db"),
)


class RegistryDB:
    """Thread-safe SQLite database wrapper for the tracker registry.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database file.  Parent directories are
        created automatically.
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self._local = threading.local()

        # Ensure data directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    # ── Connection management ────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        """Return a per-thread connection (created lazily)."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    def execute(
        self,
        sql: str,
        params: tuple = (),
    ) -> sqlite3.Cursor:
        """Execute SQL with the thread lock held."""
        with self._lock:
            conn = self._get_conn()
            cursor = conn.execute(sql, params)
            conn.commit()
            return cursor

    def executemany(
        self,
        sql: str,
        params_list: List[tuple],
    ) -> sqlite3.Cursor:
        """Execute SQL for many parameter sets."""
        with self._lock:
            conn = self._get_conn()
            cursor = conn.executemany(sql, params_list)
            conn.commit()
            return cursor

    def fetchone(
        self,
        sql: str,
        params: tuple = (),
    ) -> Optional[Dict[str, Any]]:
        """Execute and fetch one row as a dict."""
        with self._lock:
            conn = self._get_conn()
            row = conn.execute(sql, params).fetchone()
            return dict(row) if row else None

    def fetchall(
        self,
        sql: str,
        params: tuple = (),
    ) -> List[Dict[str, Any]]:
        """Execute and fetch all rows as dicts."""
        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def close(self) -> None:
        """Close the current thread's connection."""
        conn = getattr(self._local, "conn", None)
        if conn:
            conn.close()
            self._local.conn = None

    # ── Schema initialisation ────────────────────────────────────

    def init_db(self) -> None:
        """Create all tables and indexes if they do not exist."""
        log.info("registry.init_db", path=self.db_path)

        self.execute(
            """
            CREATE TABLE IF NOT EXISTS aircraft (
                icao_hex        TEXT PRIMARY KEY,
                callsign        TEXT,
                registration    TEXT,
                type_code       TEXT,
                type_desc       TEXT,
                operator        TEXT,
                manufacturer    TEXT,
                owner           TEXT,
                country         TEXT,
                mil             INTEGER DEFAULT 0,
                interesting     INTEGER DEFAULT 0,
                notes           TEXT,
                photo_url       TEXT,
                first_seen      TEXT NOT NULL DEFAULT (datetime('now')),
                last_seen       TEXT NOT NULL DEFAULT (datetime('now')),
                sighting_count  INTEGER DEFAULT 1,
                enriched        INTEGER DEFAULT 0,
                enriched_at     TEXT,
                extra_json      TEXT
            )
            """
        )

        self.execute(
            """
            CREATE TABLE IF NOT EXISTS vessels (
                mmsi            TEXT PRIMARY KEY,
                name            TEXT,
                callsign        TEXT,
                vessel_type     INTEGER,
                vessel_type_desc TEXT,
                flag            TEXT,
                imo             TEXT,
                length          REAL,
                beam            REAL,
                draft           REAL,
                destination     TEXT,
                photo_url       TEXT,
                first_seen      TEXT NOT NULL DEFAULT (datetime('now')),
                last_seen       TEXT NOT NULL DEFAULT (datetime('now')),
                sighting_count  INTEGER DEFAULT 1,
                enriched        INTEGER DEFAULT 0,
                enriched_at     TEXT,
                extra_json      TEXT
            )
            """
        )

        self.execute(
            """
            CREATE TABLE IF NOT EXISTS positions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                craft_type  TEXT NOT NULL,  -- 'aircraft' or 'vessel'
                craft_id    TEXT NOT NULL,   -- icao_hex or mmsi
                lat         REAL NOT NULL,
                lng         REAL NOT NULL,
                altitude    REAL,
                speed       REAL,
                heading     REAL,
                timestamp   TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )

        self.execute(
            """
            CREATE TABLE IF NOT EXISTS routes (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                craft_type      TEXT NOT NULL,
                craft_id        TEXT,
                name            TEXT,
                waypoints_json  TEXT NOT NULL,
                sighting_count  INTEGER DEFAULT 1,
                status          TEXT DEFAULT 'candidate',  -- 'candidate' or 'confirmed'
                first_seen      TEXT NOT NULL DEFAULT (datetime('now')),
                last_seen       TEXT NOT NULL DEFAULT (datetime('now')),
                distance_nm     REAL
            )
            """
        )

        self.execute(
            """
            CREATE TABLE IF NOT EXISTS photos (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                craft_type  TEXT NOT NULL,
                craft_id    TEXT NOT NULL,
                file_path   TEXT NOT NULL,
                caption     TEXT,
                taken_at    TEXT,
                added_at    TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )

        # ── Indexes ──────────────────────────────────────────────

        self.execute(
            "CREATE INDEX IF NOT EXISTS idx_positions_craft "
            "ON positions (craft_type, craft_id)"
        )
        self.execute(
            "CREATE INDEX IF NOT EXISTS idx_positions_ts "
            "ON positions (timestamp)"
        )
        self.execute(
            "CREATE INDEX IF NOT EXISTS idx_routes_type "
            "ON routes (craft_type)"
        )
        self.execute(
            "CREATE INDEX IF NOT EXISTS idx_routes_status "
            "ON routes (status)"
        )
        self.execute(
            "CREATE INDEX IF NOT EXISTS idx_photos_craft "
            "ON photos (craft_type, craft_id)"
        )
        self.execute(
            "CREATE INDEX IF NOT EXISTS idx_aircraft_last_seen "
            "ON aircraft (last_seen)"
        )
        self.execute(
            "CREATE INDEX IF NOT EXISTS idx_vessels_last_seen "
            "ON vessels (last_seen)"
        )
        self.execute(
            "CREATE INDEX IF NOT EXISTS idx_aircraft_enriched "
            "ON aircraft (enriched)"
        )
        self.execute(
            "CREATE INDEX IF NOT EXISTS idx_vessels_enriched "
            "ON vessels (enriched)"
        )

        log.info("registry.init_db.complete")
