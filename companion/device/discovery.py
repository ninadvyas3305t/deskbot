"""Cross-platform serial device discovery for DeskBot ESP32-S3 hardware."""

from __future__ import annotations

import glob
import logging
import sys
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)

# Known USB-to-UART and USB-JTAG chip identifiers for ESP32 boards
ESP32_CHIPSET_KEYWORDS = (
    "usbmodem",
    "usbserial",
    "ch34",
    "cp210",
    "espressif",
    "usb single serial",
    "usb jtag/serial",
    "ftdi",
    "silicon labs",
    "wch",
)


@dataclass
class SerialCandidate:
    """Describes a candidate serial port."""
    device: str
    description: str
    hwid: str
    is_preferred: bool = False


def is_candidate_port(device: str, description: str = "", hwid: str = "") -> bool:
    """Check if a device port or its description/hwid matches expected ESP32 chipsets."""
    dev_lower = device.lower()
    desc_lower = description.lower()
    hwid_lower = hwid.lower()

    if "bluetooth" in dev_lower or "debug-console" in dev_lower:
        return False

    return any(
        k in desc_lower or k in hwid_lower or k in dev_lower
        for k in ESP32_CHIPSET_KEYWORDS
    )


def scan_candidate_ports() -> List[SerialCandidate]:
    """Enumerate and prioritize all candidate serial ports matching ESP32 hardware."""
    candidates: List[SerialCandidate] = []

    try:
        import serial.tools.list_ports
        for port in serial.tools.list_ports.comports():
            desc_lower = (port.description or "").lower()
            hwid_lower = (port.hwid or "").lower()
            dev_lower = (port.device or "").lower()

            is_match = any(
                k in desc_lower or k in hwid_lower or k in dev_lower
                for k in ESP32_CHIPSET_KEYWORDS
            )

            # Ignore Bluetooth and debug virtual consoles
            if "bluetooth" in dev_lower or "debug-console" in dev_lower:
                continue

            candidates.append(
                SerialCandidate(
                    device=port.device,
                    description=port.description or "",
                    hwid=port.hwid or "",
                    is_preferred=is_match,
                )
            )
    except Exception as err:
        logger.debug("pyserial comports scan error: %s", err)

    # Sort preferred USB chipsets first
    candidates.sort(key=lambda c: (not c.is_preferred, c.device))

    # Platform fallback globbing if comports returned empty
    if not candidates:
        if sys.platform == "darwin":
            ports = glob.glob("/dev/cu.usbmodem*") + glob.glob("/dev/cu.usbserial*")
            for p in sorted(ports):
                if "debug-console" not in p:
                    candidates.append(SerialCandidate(device=p, description="USB Serial Device", hwid="", is_preferred=True))
        elif sys.platform.startswith("linux"):
            ports = glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*")
            for p in sorted(ports):
                candidates.append(SerialCandidate(device=p, description="USB Serial Device", hwid="", is_preferred=True))

    return candidates


def get_first_candidate_port() -> Optional[str]:
    """Return the most likely candidate port string or None."""
    candidates = scan_candidate_ports()
    return candidates[0].device if candidates else None
