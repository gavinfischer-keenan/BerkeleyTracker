"""Health monitor — heartbeat and component health checks."""
from __future__ import annotations

import threading
import time

import structlog

log = structlog.get_logger(__name__)


class HealthMonitor:
    def __init__(self, publisher, influx, interval_sec: int = 60) -> None:
        self._publisher = publisher
        self._influx = influx
        self._interval = interval_sec
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._start_time = time.time()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True, name="health")
        self._thread.start()
        log.info("health.started", interval=self._interval)

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                health = self.check()
                log.debug("health.check", **health)
            except Exception as exc:
                log.warning("health.check_failed", error=str(exc))
            self._stop.wait(self._interval)

    def check(self) -> dict:
        return {
            "influx_ok": self._influx.is_healthy() if hasattr(self._influx, 'is_healthy') else True,
            "uptime_s": int(time.time() - self._start_time),
        }
