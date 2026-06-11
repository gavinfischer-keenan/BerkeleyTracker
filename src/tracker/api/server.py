"""FastAPI server for BerkeleyTracker — aircraft, vessel, route, and photo endpoints."""
from __future__ import annotations

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse

from tracker.config import Settings
from tracker.registry.db import TrackerDB
from tracker.registry.aircraft import AircraftRegistry
from tracker.registry.vessels import VesselRegistry
from tracker.registry.routes import RouteManager
from tracker.registry.photos import PhotoManager


def create_app(
    db: TrackerDB,
    aircraft_reg: AircraftRegistry,
    vessel_reg: VesselRegistry,
    route_mgr: RouteManager,
    settings: Settings,
) -> FastAPI:
    app = FastAPI(
        title="Berkeley Tracker API",
        description="ADS-B and AIS tracking — aircraft, vessels, routes, photos",
        version="0.1.0",
    )
    photos = PhotoManager(db, settings.photo_dir)

    # ── Health ─────────────────────────────────────────────────────
    @app.get("/health")
    def health():
        return {"status": "ok", "agent": "tracker", "version": "0.1.0"}

    # ── Aircraft ───────────────────────────────────────────────────
    @app.get("/api/tracker/aircraft")
    def list_aircraft(since_minutes: int = Query(5, ge=1, le=60)):
        return aircraft_reg.get_all_visible(since_minutes)

    @app.get("/api/tracker/aircraft/{icao}")
    def get_aircraft(icao: str):
        craft = aircraft_reg.get(icao)
        if not craft:
            raise HTTPException(404, f"Aircraft {icao} not found")
        craft["photos"] = photos.get_photos("aircraft", icao.upper())
        return craft

    @app.get("/api/tracker/aircraft/{icao}/positions")
    def aircraft_positions(icao: str, hours: int = Query(24, ge=1, le=168)):
        return aircraft_reg.get_history(icao, hours)

    @app.post("/api/tracker/aircraft/{icao}/photo")
    async def upload_aircraft_photo(
        icao: str, file: UploadFile = File(...), caption: str = "",
    ):
        craft = aircraft_reg.get(icao)
        if not craft:
            raise HTTPException(404, f"Aircraft {icao} not found")
        content = await file.read()
        photo_id = photos.save_uploaded("aircraft", icao.upper(), content,
                                         file.filename or "photo.jpg", caption)
        return {"photo_id": photo_id, "icao": icao}

    # ── Vessels ────────────────────────────────────────────────────
    @app.get("/api/tracker/vessels")
    def list_vessels(since_minutes: int = Query(10, ge=1, le=60)):
        return vessel_reg.get_all_visible(since_minutes)

    @app.get("/api/tracker/vessels/{mmsi}")
    def get_vessel(mmsi: str):
        craft = vessel_reg.get(mmsi)
        if not craft:
            raise HTTPException(404, f"Vessel {mmsi} not found")
        craft["photos"] = photos.get_photos("vessel", mmsi)
        return craft

    @app.get("/api/tracker/vessels/{mmsi}/positions")
    def vessel_positions(mmsi: str, hours: int = Query(24, ge=1, le=168)):
        return vessel_reg.get_history(mmsi, hours)

    @app.post("/api/tracker/vessels/{mmsi}/photo")
    async def upload_vessel_photo(
        mmsi: str, file: UploadFile = File(...), caption: str = "",
    ):
        craft = vessel_reg.get(mmsi)
        if not craft:
            raise HTTPException(404, f"Vessel {mmsi} not found")
        content = await file.read()
        photo_id = photos.save_uploaded("vessel", mmsi, content,
                                         file.filename or "photo.jpg", caption)
        return {"photo_id": photo_id, "mmsi": mmsi}

    # ── Routes ─────────────────────────────────────────────────────
    @app.get("/api/tracker/routes")
    def list_routes(craft_type: str | None = None):
        return route_mgr.get_all_routes(craft_type)

    @app.get("/api/tracker/routes/{route_id}")
    def get_route(route_id: str):
        route = route_mgr.get_route(route_id)
        if not route:
            raise HTTPException(404, f"Route {route_id} not found")
        return route

    # ── Stats ──────────────────────────────────────────────────────
    @app.get("/api/tracker/stats")
    def stats():
        aircraft_total = db.query_one("SELECT COUNT(*) as cnt FROM aircraft")
        vessel_total = db.query_one("SELECT COUNT(*) as cnt FROM vessels")
        route_total = db.query_one("SELECT COUNT(*) as cnt FROM routes")
        return {
            "aircraft_total": aircraft_total["cnt"] if aircraft_total else 0,
            "vessels_total": vessel_total["cnt"] if vessel_total else 0,
            "routes_total": route_total["cnt"] if route_total else 0,
        }

    @app.get("/api/tracker/stats/frequency")
    def frequency(craft_type: str = "aircraft", limit: int = Query(50, ge=1, le=200)):
        if craft_type == "aircraft":
            return aircraft_reg.get_most_seen(limit)
        else:
            return vessel_reg.get_most_seen(limit)

    return app
