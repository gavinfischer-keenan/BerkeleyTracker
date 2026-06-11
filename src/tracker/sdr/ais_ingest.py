"""AIS NMEA ingest via AIS-catcher UDP output.

Listens on a UDP port (default 10110) for NMEA sentences produced by
AIS-catcher, decodes them with the ``pyais`` library, and dispatches
position reports (message types 1, 2, 3) and static/voyage data
(message type 5) via callbacks.
"""

from __future__ import annotations

import socket
import threading
import time
from typing import Callable, Optional, Protocol

import structlog

try:
    from pyais import decode as pyais_decode
    from pyais.stream import NMEAMessage
except ImportError:  # pragma: no cover
    pyais_decode = None  # type: ignore[assignment]
    NMEAMessage = None  # type: ignore[assignment,misc]

log = structlog.get_logger(__name__)


# ── Callback protocols ──────────────────────────────────────────────

class OnAISPositionCallback(Protocol):
    def __call__(
        self,
        mmsi: str,
        lat: float,
        lng: float,
        speed: float,
        heading: float,
    ) -> None: ...


class OnAISStaticCallback(Protocol):
    def __call__(
        self,
        mmsi: str,
        name: str,
        vessel_type: int,
        flag: str,
        callsign: str,
    ) -> None: ...


# ── AIS ingest thread ──────────────────────────────────────────────

class AISIngest:
    """Background thread that listens for AIS NMEA sentences on UDP and
    dispatches decoded data via callbacks.

    Parameters
    ----------
    host : str
        Bind address (default ``0.0.0.0``).
    port : int
        UDP port (default ``10110``).
    on_position : callable, optional
        Called with ``(mmsi, lat, lng, speed, heading)`` for position
        reports (AIS message types 1, 2, 3).
    on_static : callable, optional
        Called with ``(mmsi, name, vessel_type, flag, callsign)`` for
        static data (AIS message type 5).
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 10110,
        on_position: Optional[Callable] = None,
        on_static: Optional[Callable] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.on_position = on_position
        self.on_static = on_static

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._messages_received = 0
        self._last_message_time: Optional[float] = None

        # Buffer for multi-sentence messages (type 5 spans 2 sentences)
        self._fragment_buf: dict[int, list[str]] = {}

    # ── Lifecycle ────────────────────────────────────────────────

    def start(self) -> None:
        """Start the ingest background thread."""
        if pyais_decode is None:
            log.error("ais_ingest.pyais_not_installed")
            return
        if self._running:
            log.warning("ais_ingest.already_running")
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, name="ais-ingest", daemon=True
        )
        self._thread.start()
        log.info("ais_ingest.started", host=self.host, port=self.port)

    def stop(self) -> None:
        """Signal the ingest thread to stop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        log.info("ais_ingest.stopped")

    @property
    def messages_received(self) -> int:
        return self._messages_received

    @property
    def last_message_time(self) -> Optional[float]:
        return self._last_message_time

    # ── Main loop ────────────────────────────────────────────────

    def _run_loop(self) -> None:
        """UDP receive loop."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((self.host, self.port))
        except OSError as exc:
            log.error("ais_ingest.bind_failed", error=str(exc))
            return

        sock.settimeout(2.0)
        log.info("ais_ingest.listening", host=self.host, port=self.port)

        try:
            while self._running:
                try:
                    data, _addr = sock.recvfrom(4096)
                except socket.timeout:
                    continue
                except OSError:
                    if not self._running:
                        break
                    raise

                for line in data.decode("ascii", errors="replace").splitlines():
                    line = line.strip()
                    if line:
                        self._handle_nmea(line)
        finally:
            sock.close()

    # ── NMEA handling ────────────────────────────────────────────

    def _handle_nmea(self, raw: str) -> None:
        """Decode an NMEA sentence (or fragment) and dispatch."""
        if not raw.startswith("!"):
            return

        try:
            # pyais.decode() accepts a list of NMEA sentence strings and
            # handles multi-sentence message assembly internally.
            sentences = self._collect_fragments(raw)
            if sentences is None:
                return  # waiting for more fragments

            decoded_msgs = pyais_decode(*sentences)
            for msg in decoded_msgs:
                decoded = msg.asdict()
                self._dispatch(decoded)
        except Exception:
            log.debug("ais_ingest.decode_error", raw=raw[:80])

    def _collect_fragments(self, raw: str) -> Optional[list[str]]:
        """Buffer multi-sentence NMEA messages.

        Returns a complete list of fragment strings when all parts have
        arrived, or ``None`` if still waiting.
        """
        parts = raw.split(",")
        if len(parts) < 7:
            return [raw]

        try:
            frag_count = int(parts[1])
            frag_num = int(parts[2])
            seq_id = int(parts[3]) if parts[3] else 0
        except (ValueError, IndexError):
            return [raw]

        if frag_count == 1:
            return [raw]

        # Multi-sentence
        if seq_id not in self._fragment_buf:
            self._fragment_buf[seq_id] = []
        self._fragment_buf[seq_id].append(raw)

        if len(self._fragment_buf[seq_id]) >= frag_count:
            sentences = self._fragment_buf.pop(seq_id)
            return sentences

        return None

    def _dispatch(self, decoded: dict) -> None:
        """Route a decoded AIS message to the appropriate callback."""
        msg_type = decoded.get("msg_type")
        mmsi = str(decoded.get("mmsi", ""))
        if not mmsi:
            return

        self._messages_received += 1
        self._last_message_time = time.time()

        # Position reports: types 1, 2, 3
        if msg_type in (1, 2, 3) and self.on_position:
            lat = decoded.get("lat")
            lng = decoded.get("lon")
            speed = decoded.get("speed", 0.0)
            heading = decoded.get("heading", decoded.get("course", 0.0))

            if lat is not None and lng is not None:
                # Filter invalid coords (91 = not available per AIS spec)
                if abs(lat) <= 90.0 and abs(lng) <= 180.0:
                    try:
                        self.on_position(
                            mmsi,
                            float(lat),
                            float(lng),
                            float(speed) if speed else 0.0,
                            float(heading) if heading else 0.0,
                        )
                    except Exception:
                        log.exception("ais_ingest.callback_error", callback="on_position")

        # Static and voyage data: type 5
        elif msg_type == 5 and self.on_static:
            name = decoded.get("shipname", "").strip()
            vessel_type = decoded.get("ship_type", 0)
            callsign = decoded.get("callsign", "").strip()

            # Derive flag from MMSI (first 3 digits = MID)
            flag = ""
            if len(mmsi) == 9:
                from tracker.enrichment.mmsi_lookup import mmsi_to_flag

                flag = mmsi_to_flag(mmsi)

            try:
                self.on_static(
                    mmsi,
                    name,
                    int(vessel_type) if vessel_type else 0,
                    flag,
                    callsign,
                )
            except Exception:
                log.exception("ais_ingest.callback_error", callback="on_static")
