"""MarineTraffic API client (stub — requires paid API key)."""
from __future__ import annotations

import httpx
import structlog

log = structlog.get_logger(__name__)


class MarineTrafficClient:
    """MarineTraffic API for vessel enrichment.

    Requires a paid API key. See: https://www.marinetraffic.com/en/ais-api-services
    Free alternatives: VesselFinder, myshiptracking.
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def get_vessel_info(self, mmsi: str) -> dict | None:
        """Lookup vessel name, type, flag, and photo by MMSI."""
        if not self._api_key:
            return None

        try:
            url = (
                f"https://services.marinetraffic.com/api/exportvessel/v:5"
                f"/{self._api_key}/mmsi:{mmsi}/protocol:jsono"
            )
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list) and data:
                        v = data[0]
                        return {
                            "name": v.get("SHIPNAME", ""),
                            "type_desc": v.get("SHIPTYPE", ""),
                            "flag": v.get("FLAG", ""),
                            "imo": v.get("IMO", ""),
                            "length_m": v.get("LENGTH", 0),
                            "photo_url": v.get("PHOTO_URL", ""),
                            "source": "marinetraffic",
                        }
                return None
        except Exception as exc:
            log.debug("marinetraffic.error", mmsi=mmsi, error=str(exc))
            return None
