"""HTTP POST to dashboard for tracker data."""
from __future__ import annotations

import httpx
import structlog

log = structlog.get_logger(__name__)


class DashboardPoster:
    """Forward tracker events to the BerkeleyHouse dashboard via HTTP POST."""

    def __init__(self, url: str = "http://localhost:5050/api/ingest/tracker") -> None:
        self._url = url

    def post(self, data: dict) -> bool:
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.post(self._url, json=data)
                return resp.status_code < 400
        except Exception as exc:
            log.debug("dashboard.post_failed", error=str(exc))
            return False
