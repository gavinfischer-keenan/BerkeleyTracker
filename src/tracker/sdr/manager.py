"""SDR device manager.

Detects connected RTL-SDR dongles, ensures decoder services are running,
and reports device health statistics.
"""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import structlog

log = structlog.get_logger(__name__)


@dataclass
class SDRDevice:
    """Represents a detected RTL-SDR dongle."""

    index: int
    serial: str
    product: str = ""
    manufacturer: str = ""
    role: str = "unknown"  # "adsb", "ais", "unknown"


@dataclass
class DecoderStatus:
    """Status of a decoder systemd service."""

    name: str
    active: bool = False
    pid: Optional[int] = None
    uptime_seconds: float = 0.0
    messages_total: int = 0


@dataclass
class SDRStats:
    """Aggregated SDR statistics."""

    devices_detected: int = 0
    devices: List[SDRDevice] = field(default_factory=list)
    decoders: Dict[str, DecoderStatus] = field(default_factory=dict)
    adsb_messages_per_sec: float = 0.0
    ais_messages_per_sec: float = 0.0
    last_check: float = 0.0


class SDRManager:
    """Manages RTL-SDR devices and decoder services.

    Detects connected dongles via ``rtl_test``, monitors dump1090 and
    AIS-catcher systemd services, and reports health metrics.
    """

    SERIAL_ADSB = "ADSB001"
    SERIAL_AIS = "AIS001"

    DECODER_SERVICES = {
        "adsb": "dump1090-fa",
        "ais": "ais-catcher",
    }

    def __init__(self) -> None:
        self._devices: List[SDRDevice] = []
        self._decoder_status: Dict[str, DecoderStatus] = {}
        self._msg_counts: Dict[str, int] = {"adsb": 0, "ais": 0}
        self._last_count_time: float = time.monotonic()
        self._msg_rates: Dict[str, float] = {"adsb": 0.0, "ais": 0.0}

    # ------------------------------------------------------------------
    # Device detection
    # ------------------------------------------------------------------

    def detect_devices(self) -> List[SDRDevice]:
        """Run ``rtl_test`` to enumerate connected RTL-SDR dongles.

        Returns a list of :class:`SDRDevice` instances.  If ``rtl_test``
        is not installed or no devices are found, returns an empty list.
        """
        self._devices = []
        try:
            result = subprocess.run(
                ["rtl_test", "-t"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            output = result.stdout + result.stderr
        except FileNotFoundError:
            log.warning("rtl_test not found – is rtl-sdr installed?")
            return self._devices
        except subprocess.TimeoutExpired:
            log.warning("rtl_test timed out")
            return self._devices
        except Exception as exc:
            log.error("rtl_test failed", error=str(exc))
            return self._devices

        self._devices = self._parse_rtl_test_output(output)
        log.info("sdr.detect_devices", count=len(self._devices))
        return self._devices

    def _parse_rtl_test_output(self, output: str) -> List[SDRDevice]:
        """Parse ``rtl_test`` output for device entries."""
        devices: List[SDRDevice] = []
        # Typical line: "  0:  Realtek, RTL2838UHIDIR, SN: ADSB001"
        pattern = re.compile(
            r"(\d+):\s+(.+?),\s+(.+?),\s+SN:\s+(\S+)",
        )
        for match in pattern.finditer(output):
            idx = int(match.group(1))
            manufacturer = match.group(2).strip()
            product = match.group(3).strip()
            serial = match.group(4).strip()

            role = "unknown"
            if serial == self.SERIAL_ADSB:
                role = "adsb"
            elif serial == self.SERIAL_AIS:
                role = "ais"

            devices.append(
                SDRDevice(
                    index=idx,
                    serial=serial,
                    product=product,
                    manufacturer=manufacturer,
                    role=role,
                )
            )
        return devices

    # ------------------------------------------------------------------
    # Decoder service management
    # ------------------------------------------------------------------

    def ensure_decoders_running(self) -> Dict[str, DecoderStatus]:
        """Check that dump1090 and AIS-catcher systemd services are active.

        Returns a dict mapping decoder name → :class:`DecoderStatus`.
        """
        statuses: Dict[str, DecoderStatus] = {}
        for key, service in self.DECODER_SERVICES.items():
            statuses[key] = self._check_service(service)
        self._decoder_status = statuses
        return statuses

    def _check_service(self, service_name: str) -> DecoderStatus:
        """Query systemd for a service's status."""
        status = DecoderStatus(name=service_name)
        try:
            result = subprocess.run(
                ["systemctl", "is-active", service_name],
                capture_output=True,
                text=True,
                timeout=5,
            )
            status.active = result.stdout.strip() == "active"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            log.debug("systemctl not available or timed out", service=service_name)
            return status

        if status.active:
            try:
                result = subprocess.run(
                    [
                        "systemctl",
                        "show",
                        service_name,
                        "--property=MainPID,ActiveEnterTimestampMonotonic",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                for line in result.stdout.splitlines():
                    if line.startswith("MainPID="):
                        status.pid = int(line.split("=", 1)[1])
                    elif line.startswith("ActiveEnterTimestampMonotonic="):
                        mono_us = int(line.split("=", 1)[1])
                        now_us = int(time.monotonic() * 1_000_000)
                        status.uptime_seconds = (now_us - mono_us) / 1_000_000
            except Exception:
                pass

        log.debug(
            "service_check",
            service=service_name,
            active=status.active,
            pid=status.pid,
        )
        return status

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def record_message(self, decoder: str) -> None:
        """Increment the message counter for *decoder* (``adsb`` or ``ais``)."""
        self._msg_counts[decoder] = self._msg_counts.get(decoder, 0) + 1

    def get_stats(self) -> SDRStats:
        """Compute and return aggregated SDR statistics."""
        now = time.monotonic()
        elapsed = now - self._last_count_time
        if elapsed > 0:
            for key in self._msg_rates:
                self._msg_rates[key] = self._msg_counts.get(key, 0) / elapsed

        stats = SDRStats(
            devices_detected=len(self._devices),
            devices=list(self._devices),
            decoders=dict(self._decoder_status),
            adsb_messages_per_sec=self._msg_rates.get("adsb", 0.0),
            ais_messages_per_sec=self._msg_rates.get("ais", 0.0),
            last_check=now,
        )

        # Reset counters
        self._msg_counts = {k: 0 for k in self._msg_counts}
        self._last_count_time = now

        return stats
