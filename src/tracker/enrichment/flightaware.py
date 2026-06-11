"""FlightAware AeroAPI client (stub — requires paid API key)."""
from __future__ import annotations

import httpx
import structlog

log = structlog.get_logger(__name__)

AEROAPI_BASE = "https://aeroapi.flightaware.com/aeroapi"


class FlightAwareClient:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def get_flight_info(self, icao_hex: str, callsign: str = "") -> dict | None:
        """Lookup flight route, origin, destination by callsign.

        Requires a FlightAware AeroAPI key (free tier: 20K lookups/month).
        See: https://www.flightaware.com/aeroapi/portal/documentation
        """
        if not self._api_key:
            return None
        if not callsign:
            return None

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(
                    f"{AEROAPI_BASE}/flights/{callsign}",
                    headers={"x-apikey": self._api_key},
                )
                if resp.status_code == 200:
                    flights = resp.json().get("flights", [])
                    if flights:
                        f = flights[0]
                        return {
                            "callsign": callsign,
                            "origin": f.get("origin", {}).get("code_iata", ""),
                            "destination": f.get("destination", {}).get("code_iata", ""),
                            "airline": f.get("operator", ""),
                            "aircraft_type": f.get("aircraft_type", ""),
                            "source": "flightaware",
                        }
                return None
        except Exception as exc:
            log.debug("flightaware.error", callsign=callsign, error=str(exc))
            return None
