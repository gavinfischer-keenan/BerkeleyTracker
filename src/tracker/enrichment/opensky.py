"""OpenSky Network API client — free aircraft metadata lookup."""
from __future__ import annotations

import httpx
import structlog

log = structlog.get_logger(__name__)

OPENSKY_METADATA_URL = "https://opensky-network.org/api/metadata/aircraft/icao/{icao}"


class OpenSkyClient:
    def __init__(self, username: str = "", password: str = "") -> None:
        self._auth = (username, password) if username else None

    def get_aircraft_metadata(self, icao_hex: str) -> dict | None:
        """Lookup aircraft registration, type, and operator by ICAO hex."""
        url = OPENSKY_METADATA_URL.format(icao=icao_hex.lower())
        try:
            with httpx.Client(timeout=10.0) as client:
                kwargs = {"auth": self._auth} if self._auth else {}
                resp = client.get(url, **kwargs)
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "registration": data.get("registration", ""),
                        "type_code": data.get("typecode", ""),
                        "type_desc": data.get("model", ""),
                        "manufacturer": data.get("manufacturer", ""),
                        "operator": data.get("operator", ""),
                        "owner": data.get("owner", ""),
                        "icao_type": data.get("icaoAircraftClass", ""),
                        "source": "opensky",
                    }
                elif resp.status_code == 404:
                    return None
                else:
                    log.debug("opensky.error", status=resp.status_code, icao=icao_hex)
                    return None
        except Exception as exc:
            log.debug("opensky.request_failed", icao=icao_hex, error=str(exc))
            return None
