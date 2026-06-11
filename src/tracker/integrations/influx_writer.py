"""InfluxDB writer for position telemetry."""
from __future__ import annotations

import time
import threading
from typing import Any

import structlog

log = structlog.get_logger(__name__)

try:
    from influxdb_client import InfluxDBClient, Point, WritePrecision
    from influxdb_client.client.write_api import SYNCHRONOUS
    HAS_INFLUX = True
except ImportError:
    HAS_INFLUX = False


class TrackerInfluxWriter:
    """Batched InfluxDB writer for aircraft and vessel positions."""

    BUCKET = "tracker-raw"

    def __init__(self, url: str, token: str, org: str,
                 batch_size: int = 100, flush_interval_ms: int = 1000) -> None:
        self._url = url
        self._org = org
        self._buffer: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._client = None
        self._write_api = None

        if HAS_INFLUX and token:
            try:
                self._client = InfluxDBClient(url=url, token=token, org=org)
                self._write_api = self._client.write_api(write_options=SYNCHRONOUS)
                log.info("influx.connected", url=url)
            except Exception as exc:
                log.warning("influx.connect_failed", error=str(exc))

    def write_aircraft_position(self, icao_hex: str, lat: float, lng: float,
                                 altitude_ft: float | None, speed_kts: float | None,
                                 heading: float | None) -> None:
        if not self._write_api:
            return
        try:
            point = (
                Point("aircraft_pos")
                .tag("icao", icao_hex)
                .field("lat", lat)
                .field("lng", lng)
                .time(int(time.time_ns()), WritePrecision.NS)
            )
            if altitude_ft is not None:
                point = point.field("altitude_ft", float(altitude_ft))
            if speed_kts is not None:
                point = point.field("speed_kts", float(speed_kts))
            if heading is not None:
                point = point.field("heading", float(heading))

            self._write_api.write(bucket=self.BUCKET, org=self._org, record=point)
        except Exception as exc:
            log.debug("influx.write_failed", measurement="aircraft_pos", error=str(exc))

    def write_vessel_position(self, mmsi: str, lat: float, lng: float,
                               speed_kts: float | None, heading: float | None) -> None:
        if not self._write_api:
            return
        try:
            point = (
                Point("vessel_pos")
                .tag("mmsi", mmsi)
                .field("lat", lat)
                .field("lng", lng)
                .time(int(time.time_ns()), WritePrecision.NS)
            )
            if speed_kts is not None:
                point = point.field("speed_kts", float(speed_kts))
            if heading is not None:
                point = point.field("heading", float(heading))

            self._write_api.write(bucket=self.BUCKET, org=self._org, record=point)
        except Exception as exc:
            log.debug("influx.write_failed", measurement="vessel_pos", error=str(exc))

    def is_healthy(self) -> bool:
        if not self._client:
            return False
        try:
            return self._client.ping()
        except Exception:
            return False

    def close(self) -> None:
        if self._client:
            self._client.close()
            log.info("influx.closed")
