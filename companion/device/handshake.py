"""Hardware handshake verification for DeskBot ESP32-S3."""

from __future__ import annotations

import logging
import time

import serial

logger = logging.getLogger(__name__)


def probe_port(port: str, baud: int = 921600, timeout: float = 1.8) -> bool:
    """Perform a non-destructive handshake to verify that port is an authentic DeskBot ESP32.

    Protocol:
    1. Open port with short timeout.
    2. Send 'STOP_STREAM\\n' to clear any pending state.
    3. Send 'START_STREAM\\n' probe.
    4. Verify 'STREAM_START' confirmation line or incoming PCM audio frames.
    5. Send 'STOP_STREAM\\n' and close cleanly.
    """
    ser = None
    try:
        ser = serial.Serial(port, baud, timeout=0.4)
        time.sleep(0.1)

        # Clear any prior state
        ser.write(b"STOP_STREAM\n")
        ser.flush()
        time.sleep(0.1)
        ser.reset_input_buffer()

        # Send probe
        ser.write(b"START_STREAM\n")
        ser.flush()

        deadline = time.monotonic() + timeout
        confirmed = False

        while time.monotonic() < deadline:
            # Check for incoming PCM audio bytes
            if ser.in_waiting > 256:
                confirmed = True
                break

            line = ser.readline()
            if line:
                text = line.decode("ascii", errors="ignore").strip()
                if "STREAM_START" in text:
                    confirmed = True
                    break

        if confirmed:
            try:
                ser.write(b"STOP_STREAM\n")
                ser.flush()
                time.sleep(0.05)
            except Exception:
                pass
            return True

    except Exception as err:
        logger.debug("Port %s probe failed: %s", port, err)
    finally:
        if ser and ser.is_open:
            try:
                ser.close()
            except Exception:
                pass

    return False
