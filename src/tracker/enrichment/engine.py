"""Background enrichment engine — lazy API lookups for new craft."""
from __future__ import annotations

import threading
import time

import structlog

from tracker.config import Settings

log = structlog.get_logger(__name__)


class EnrichmentEngine:
    """Background thread that enriches unenriched aircraft/vessels via APIs."""

    def __init__(self, aircraft_reg, vessel_reg, settings: Settings) -> None:
        self._aircraft = aircraft_reg
        self._vessels = vessel_reg
        self._settings = settings
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True, name="enrichment")
        self._thread.start()
        log.info("enrichment.started")

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        # Wait 30s before first run to let initial sightings accumulate
        self._stop.wait(30)

        while not self._stop.is_set():
            try:
                self._enrich_batch()
            except Exception as exc:
                log.warning("enrichment.error", error=str(exc))
            self._stop.wait(60)  # run every 60 seconds

    def _enrich_batch(self) -> None:
        # Aircraft
        unenriched = self._aircraft.get_unenriched(limit=5)
        for craft in unenriched:
            try:
                data = self._lookup_aircraft(craft["icao_hex"])
                if data:
                    self._aircraft.mark_enriched(craft["icao_hex"], data)
                    log.info("enrichment.aircraft", icao=craft["icao_hex"],
                             type=data.get("type_code", "?"))
                time.sleep(1)  # rate limit
            except Exception as exc:
                log.debug("enrichment.aircraft_failed", icao=craft["icao_hex"], error=str(exc))

        # Vessels
        unenriched_v = self._vessels.get_unenriched(limit=5)
        for vessel in unenriched_v:
            try:
                data = self._lookup_vessel(vessel["mmsi"])
                if data:
                    self._vessels.mark_enriched(vessel["mmsi"], data)
                    log.info("enrichment.vessel", mmsi=vessel["mmsi"],
                             name=data.get("name", "?"))
                time.sleep(1)
            except Exception as exc:
                log.debug("enrichment.vessel_failed", mmsi=vessel["mmsi"], error=str(exc))

    def _lookup_aircraft(self, icao_hex: str) -> dict | None:
        """Try OpenSky first, then FlightAware."""
        try:
            from tracker.enrichment.opensky import OpenSkyClient
            client = OpenSkyClient(self._settings.opensky_username,
                                    self._settings.opensky_password)
            data = client.get_aircraft_metadata(icao_hex)
            if data:
                return data
        except Exception:
            pass

        if self._settings.flightaware_api_key:
            try:
                from tracker.enrichment.flightaware import FlightAwareClient
                client = FlightAwareClient(self._settings.flightaware_api_key)
                return client.get_flight_info(icao_hex)
            except Exception:
                pass

        return None

    def _lookup_vessel(self, mmsi: str) -> dict | None:
        """Try static MMSI lookup, then MarineTraffic."""
        from tracker.enrichment.mmsi_lookup import mmsi_to_flag, mmsi_to_type_hint
        data: dict = {}

        flag = mmsi_to_flag(mmsi)
        if flag:
            data["flag"] = flag

        type_hint = mmsi_to_type_hint(mmsi)
        if type_hint:
            data["type_hint"] = type_hint

        if self._settings.marine_traffic_api_key:
            try:
                from tracker.enrichment.marine_traffic import MarineTrafficClient
                client = MarineTrafficClient(self._settings.marine_traffic_api_key)
                mt_data = client.get_vessel_info(mmsi)
                if mt_data:
                    data.update(mt_data)
            except Exception:
                pass

        return data if data else None
