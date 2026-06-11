"""main.py — Entry point for the Berkeley Tracker service.

Orchestrates:
  1. ADS-B ingest (dump1090 SBS on TCP 30003)
  2. AIS ingest (AIS-catcher NMEA on UDP 10110)
  3. Craft registry (SQLite)
  4. Enrichment engine (background API lookups)
  5. Route learner
  6. MQTT publisher (standard agent lifecycle)
  7. InfluxDB writer (position telemetry)
  8. FastAPI server (/api/tracker/*)

Usage:
    python -m tracker
"""
from __future__ import annotations

import signal
import sys
import threading
import time

import structlog

from tracker.config import Settings
from tracker.registry.db import TrackerDB
from tracker.registry.aircraft import AircraftRegistry
from tracker.registry.vessels import VesselRegistry
from tracker.registry.routes import RouteManager
from tracker.sdr.adsb_ingest import ADSBIngest as AdsbIngest
from tracker.sdr.ais_ingest import AISIngest as AisIngest
from tracker.enrichment.engine import EnrichmentEngine
from tracker.integrations.mqtt_publisher import MqttTrackerPublisher
from tracker.integrations.influx_writer import TrackerInfluxWriter
from tracker.telemetry.health import HealthMonitor

log = structlog.get_logger(__name__)


def _configure_logging(level: str) -> None:
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )


def main() -> None:
    settings = Settings()
    _configure_logging(settings.log_level)

    log.info("tracker.starting", version="0.1.0")

    # ── Core components ────────────────────────────────────────────
    db = TrackerDB(settings.tracker_db_path)
    aircraft_reg = AircraftRegistry(db)
    vessel_reg = VesselRegistry(db)
    route_mgr = RouteManager(db)

    # ── Infrastructure ─────────────────────────────────────────────
    publisher = MqttTrackerPublisher(
        broker=settings.mqtt_broker,
        port=settings.mqtt_port,
    )
    publisher.start()

    influx = TrackerInfluxWriter(
        url=settings.influxdb_url,
        token=settings.influxdb_token,
        org=settings.influxdb_org,
    )

    enrichment = EnrichmentEngine(
        aircraft_reg=aircraft_reg,
        vessel_reg=vessel_reg,
        settings=settings,
    )

    # ── ADS-B callbacks ────────────────────────────────────────────
    def on_adsb_position(icao_hex, lat, lng, alt, speed, heading, callsign):
        aircraft_reg.upsert_sighting(icao_hex, lat, lng, alt, speed, heading, callsign)
        influx.write_aircraft_position(icao_hex, lat, lng, alt, speed, heading)
        publisher.publish_aircraft_seen(icao_hex, {
            "icao": icao_hex, "callsign": callsign,
            "lat": lat, "lng": lng, "altitude_ft": alt,
            "speed_kts": speed, "heading": heading,
        })

    def on_adsb_identification(icao_hex, callsign):
        aircraft_reg.upsert_sighting(icao_hex, callsign=callsign)

    # ── AIS callbacks ──────────────────────────────────────────────
    def on_ais_position(mmsi, lat, lng, speed, heading):
        vessel_reg.upsert_sighting(mmsi, lat, lng, speed, heading)
        influx.write_vessel_position(mmsi, lat, lng, speed, heading)
        publisher.publish_vessel_seen(mmsi, {
            "mmsi": mmsi, "lat": lat, "lng": lng,
            "speed_kts": speed, "heading": heading,
        })

    def on_ais_static(mmsi, name, vessel_type, flag, callsign):
        vessel_reg.upsert_sighting(mmsi, name=name, vessel_type=vessel_type,
                                    flag=flag, callsign=callsign)

    # ── Ingest layers ──────────────────────────────────────────────
    adsb = AdsbIngest(
        host=settings.adsb_host,
        port=settings.adsb_sbs_port,
        on_position=on_adsb_position,
        on_identification=on_adsb_identification,
    )

    ais = AisIngest(
        port=settings.ais_udp_port,
        on_position=on_ais_position,
        on_static=on_ais_static,
    )

    # ── Shutdown handler ───────────────────────────────────────────
    def _shutdown(sig, frame):
        log.info("tracker.shutdown", signal=sig)
        adsb.stop()
        ais.stop()
        enrichment.stop()
        publisher.stop()
        influx.close()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    # ── Start everything ───────────────────────────────────────────
    adsb.start()
    ais.start()
    enrichment.start()

    log.info("tracker.running",
             adsb=f"{settings.adsb_host}:{settings.adsb_sbs_port}",
             ais_udp=settings.ais_udp_port)

    # Optional: start FastAPI
    try:
        from tracker.api.server import create_app
        import uvicorn

        app = create_app(db, aircraft_reg, vessel_reg, route_mgr, settings)
        api_thread = threading.Thread(
            target=uvicorn.run,
            kwargs={"app": app, "host": "0.0.0.0", "port": settings.api_port,
                    "log_level": "warning"},
            daemon=True,
        )
        api_thread.start()
        log.info("api.started", port=settings.api_port)
    except Exception as exc:
        log.warning("api.start_failed", error=str(exc))

    # Block until shutdown
    try:
        signal.pause()
    except AttributeError:
        while True:
            time.sleep(1)


if __name__ == "__main__":
    main()
