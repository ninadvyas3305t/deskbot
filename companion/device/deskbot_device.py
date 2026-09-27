"""Unified cross-platform device interface for the DeskBot ESP32-S3 hardware."""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

import serial

from .discovery import scan_candidate_ports
from .handshake import probe_port

logger = logging.getLogger(__name__)


class DeskBotDevice:
    """Manages the connection, communication, and command dispatch to the ESP32-S3."""

    def __init__(self, preferred_port: str = "auto", baud: int = 921600):
        self.preferred_port = preferred_port
        self.baud = baud
        self.active_port: Optional[str] = None
        self._ser: Optional[serial.Serial] = None
        self._lock = threading.Lock()

    @property
    def is_connected(self) -> bool:
        """Return True if the serial port is open and active."""
        with self._lock:
            return bool(self._ser and self._ser.is_open)

    def discover(self, verify_handshake: bool = True) -> Optional[str]:
        """Automatically find the connected DeskBot ESP32 port.

        If a specific port was requested (not 'auto'), it is tested first.
        Otherwise, all candidate ports are scanned and verified.
        """
        # 1. Test user's preferred port first if specified
        if self.preferred_port and self.preferred_port != "auto":
            if not verify_handshake or probe_port(self.preferred_port, baud=self.baud):
                return self.preferred_port

        # 2. Enumerate and probe candidates
        candidates = scan_candidate_ports()
        for cand in candidates:
            if not verify_handshake:
                return cand.device
            logger.debug("Probing candidate port: %s (%s)", cand.device, cand.description)
            if probe_port(cand.device, baud=self.baud):
                logger.info("Found verified DeskBot device on %s", cand.device)
                return cand.device

        return None

    def connect(self, port: Optional[str] = None) -> bool:
        """Connect to the DeskBot device and verify handshake."""
        with self._lock:
            if self._ser and self._ser.is_open:
                return True

            target_port = port or self.discover(verify_handshake=True)
            if not target_port:
                return False

            try:
                logger.info("Connecting to DeskBot on %s at %d baud...", target_port, self.baud)
                ser = serial.Serial(target_port, self.baud, timeout=0.5)

                # Reset stream state on ESP32
                ser.write(b"STOP_STREAM\n")
                ser.flush()
                time.sleep(0.15)
                ser.reset_input_buffer()
                ser.reset_output_buffer()

                self._ser = ser
                self.active_port = target_port
                return True
            except Exception as err:
                logger.warning("Could not connect to %s: %s", target_port, err)
                return False

    def disconnect(self) -> None:
        """Gracefully disconnect from the DeskBot hardware."""
        with self._lock:
            if self._ser:
                try:
                    self._ser.write(b"STOP_STREAM\n")
                    self._ser.flush()
                    time.sleep(0.05)
                except Exception:
                    pass
                try:
                    self._ser.close()
                except Exception:
                    pass
                self._ser = None
            self.active_port = None

    def send_command(self, cmd: str) -> bool:
        """Send a string command (e.g. 'STATE_THINKING') to update OLED display or mode."""
        clean_cmd = cmd.strip()
        if not clean_cmd:
            return False

        with self._lock:
            if not self._ser or not self._ser.is_open:
                return False
            try:
                payload = f"{clean_cmd}\n".encode("ascii")
                self._ser.write(payload)
                self._ser.flush()
                return True
            except Exception as err:
                logger.debug("Device command send failed: %s", err)
                return False

    def read_raw(self, size: int = 4096) -> bytes:
        """Read raw bytes from the open serial stream."""
        with self._lock:
            if not self._ser or not self._ser.is_open:
                return b""
            try:
                return self._ser.read(size)
            except Exception as err:
                logger.debug("Serial read exception: %s", err)
                raise
