"""DeskBot cross-platform serial device and hardware interface package."""

from .deskbot_device import DeskBotDevice
from .discovery import (
    SerialCandidate,
    get_first_candidate_port,
    is_candidate_port,
    scan_candidate_ports,
)
from .handshake import probe_port
from .monitor import DeviceMonitor

__all__ = [
    "DeskBotDevice",
    "DeviceMonitor",
    "scan_candidate_ports",
    "get_first_candidate_port",
    "is_candidate_port",
    "probe_port",
    "SerialCandidate",
]

