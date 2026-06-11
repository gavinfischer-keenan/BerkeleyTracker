"""ADS-B message ingest via dump1090 SBS/BaseStation output.

Connects to the dump1090 SBS TCP feed on port 30003 and parses MSG
types 1–8 to extract aircraft positions, identification, and velocity.
Runs in a background thread with automatic reconnection and exponential
backoff.
"""

from __future__ import annotations

import socket
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

import structlog

log = structlog.get_logger(__name__)


# ── Callback protocols ──────────────────────────────────────────────

class OnPositionCallback(Protocol):
    def __call__(
        self,
        icao_hex: str,
        lat: float,
        lng: float,
        alt: float,
        speed: float,
        heading: float,
        callsign: str,
    ) -> None: ...


class OnIdentificationCallback(Protocol):
    def __call__(self, icao_hex: str, callsign: str) -> None: ...


# ── SBS message dataclass ───────────────────────────────────────────

@dataclass
class SBSMessage:
    """Parsed SBS/BaseStation message."""

    msg_type: int  # 1-8
    icao_hex: str
    callsign: Optional[str] = None
    altitude: Optional[float] = None
    ground_speed: Optional[float] = None
    track: Optional[float] = None  # heading
    lat: Optional[float] = None
    lng: Optional[float] = None
    vertical_rate: Optional[float] = None
    squawk: Optional[str] = None
    alert: bool = False
    emergency: bool = False
    on_ground: bool = False


# ── SBS parser ──────────────────────────────────────────────────────

def parse_sbs_line(line: str) -> Optional[SBSMessage]:
    """Parse a single SBS/BaseStation CSV line into an :class:`SBSMessage`.

    SBS format (comma-separated, 22 fields):
        MSG,<msg_type>,<session_id>,<aircraft_id>,<icao_hex>,<flight_id>,
        <date_gen>,<time_gen>,<date_log>,<time_log>,<callsign>,<altitude>,
        <ground_speed>,<track>,<lat>,<lng>,<vertical_rate>,<squawk>,
        <alert>,<emergency>,<spi>,<on_ground>

    Returns ``None`` if the line cannot be parsed.
    """
    if not line.startswith("MSG,"):
        return None

    parts = line.split(",")
    if len(parts) < 22:
        return None

    try:
        msg_type = int(parts[1])
    except (ValueError, IndexError):
        return None

    icao_hex = parts[4].strip().upper()
    if not icao_hex:
        return None

    msg = SBSMessage(msg_type=msg_type, icao_hex=icao_hex)

    # Callsign (field 10)
    cs = parts[10].strip()
    if cs:
        msg.callsign = cs

    # Altitude (field 11)
    if parts[11].strip():
        try:
            msg.altitude = float(parts[11])
        except ValueError:
            pass

    # Ground speed (field 12)
    if parts[12].strip():
        try:
            msg.ground_speed = float(parts[12])
        except ValueError:
            pass

    # Track / heading (field 13)
    if parts[13].strip():
        try:
            msg.track = float(parts[13])
        except ValueError:
            pass

    # Lat (field 14)
    if parts[14].strip():
        try:
            msg.lat = float(parts[14])
        except ValueError:
            pass

    # Lng (field 15)
    if parts[15].strip():
        try:
            msg.lng = float(parts[15])
        except ValueError:
            pass

    # Vertical rate (field 16)
    if parts[16].strip():
        try:
            msg.vertical_rate = float(parts[16])
        except ValueError:
            pass

    # Squawk (field 17)
    sq = parts[17].strip()
    if sq:
        msg.squawk = sq

    # Boolean flags
    msg.alert = parts[18].strip() == "1"
    msg.emergency = parts[19].strip() == "1"
    msg.on_ground = parts[21].strip() == "1"

    return msg


def parse_sbs_message(line: str) -> dict | None:
    """Convenience wrapper that returns a dict instead of SBSMessage.

    Used by tests and external consumers that prefer dict access.
    """
    msg = parse_sbs_line(line)
    if msg is None:
        return None
    return {
        "msg_type": msg.msg_type,
        "icao_hex": msg.icao_hex,
        "callsign": msg.callsign or "",
        "altitude_ft": msg.altitude,
        "speed_kts": msg.ground_speed,
        "heading": msg.track,
        "lat": msg.lat,
        "lng": msg.lng,
        "vertical_rate": msg.vertical_rate,
        "squawk": msg.squawk,
        "on_ground": msg.on_ground,
    }




# ── ADS-B ingest thread ────────────────────────────────────────────

class ADSBIngest:
    """Background thread that connects to dump1090's SBS output
    on TCP port 30003 and dispatches parsed messages via callbacks.

    Parameters
    ----------
    host : str
        dump1090 host (default ``127.0.0.1``).
    port : int
        SBS port (default ``30003``).
    on_position : callable, optional
        Called with ``(icao_hex, lat, lng, alt, speed, heading, callsign)``
        when a position update is received.
    on_identification : callable, optional
        Called with ``(icao_hex, callsign)`` when an identification
        message (MSG type 1) is received.
    """

    INITIAL_BACKOFF = 1.0
    MAX_BACKOFF = 60.0
    BACKOFF_FACTOR = 2.0

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 30003,
        on_position: Optional[Callable] = None,
        on_identification: Optional[Callable] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.on_position = on_position
        self.on_identification = on_identification

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._backoff = self.INITIAL_BACKOFF
        self._messages_received = 0
        self._last_message_time: Optional[float] = None

        # Track partial callsigns/positions per ICAO for assembly
        self._callsigns: dict[str, str] = {}

    # ── Lifecycle ────────────────────────────────────────────────

    def start(self) -> None:
        """Start the ingest background thread."""
        if self._running:
            log.warning("adsb_ingest.already_running")
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, name="adsb-ingest", daemon=True
        )
        self._thread.start()
        log.info("adsb_ingest.started", host=self.host, port=self.port)

    def stop(self) -> None:
        """Signal the ingest thread to stop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        log.info("adsb_ingest.stopped")

    @property
    def messages_received(self) -> int:
        return self._messages_received

    @property
    def last_message_time(self) -> Optional[float]:
        return self._last_message_time

    # ── Main loop ────────────────────────────────────────────────

    def _run_loop(self) -> None:
        """Reconnecting receive loop."""
        while self._running:
            try:
                self._connect_and_read()
            except Exception as exc:
                if not self._running:
                    break
                log.warning(
                    "adsb_ingest.connection_lost",
                    error=str(exc),
                    backoff=self._backoff,
                )
                time.sleep(self._backoff)
                self._backoff = min(
                    self._backoff * self.BACKOFF_FACTOR, self.MAX_BACKOFF
                )

    def _connect_and_read(self) -> None:
        """Connect to dump1090 and read SBS lines until disconnected."""
        with socket.create_connection(
            (self.host, self.port), timeout=10
        ) as sock:
            log.info(
                "adsb_ingest.connected", host=self.host, port=self.port
            )
            self._backoff = self.INITIAL_BACKOFF  # reset on success
            sock.settimeout(30.0)
            buf = ""
            while self._running:
                try:
                    data = sock.recv(4096)
                except socket.timeout:
                    continue
                if not data:
                    raise ConnectionError("dump1090 closed connection")

                buf += data.decode("ascii", errors="replace")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if line:
                        self._handle_line(line)

    def _handle_line(self, line: str) -> None:
        """Parse and dispatch a single SBS line."""
        msg = parse_sbs_line(line)
        if msg is None:
            return

        self._messages_received += 1
        self._last_message_time = time.time()

        # Track callsigns across message types
        if msg.callsign:
            self._callsigns[msg.icao_hex] = msg.callsign

        # MSG type 1 — ES Identification
        if msg.msg_type == 1 and msg.callsign and self.on_identification:
            try:
                self.on_identification(msg.icao_hex, msg.callsign)
            except Exception:
                log.exception("adsb_ingest.callback_error", callback="on_identification")

        # MSG type 3 — ES Airborne Position
        # MSG type 2 — ES Surface Position
        # MSG type 4 — ES Airborne Velocity (no lat/lng, but speed/heading)
        # Dispatch position if we have lat/lng
        if msg.lat is not None and msg.lng is not None and self.on_position:
            callsign = msg.callsign or self._callsigns.get(msg.icao_hex, "")
            try:
                self.on_position(
                    msg.icao_hex,
                    msg.lat,
                    msg.lng,
                    msg.altitude or 0.0,
                    msg.ground_speed or 0.0,
                    msg.track or 0.0,
                    callsign,
                )
            except Exception:
                log.exception("adsb_ingest.callback_error", callback="on_position")
