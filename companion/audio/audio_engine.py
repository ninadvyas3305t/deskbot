"""Continuous serial audio engine for ESP32 PCM stream."""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Optional

import serial

from .ring_buffer import RingBuffer

logger = logging.getLogger(__name__)


class AudioEngine:
    """Manages the continuous serial audio stream from the ESP32-S3."""

    def __init__(
        self,
        port: str = "COM4",
        baud: int = 921600,
        sample_rate: int = 16000,
        sample_width: int = 2,
        frame_bytes: int = 960,  # 30ms at 16kHz 16-bit mono
        ring_buffer_duration: float = 2.0,
        wait_for_device: bool = False,
        baud_rate: Optional[int] = None,
    ):
        self.port = port
        self.baud = baud_rate if baud_rate is not None else baud
        self.sample_rate = sample_rate
        self.sample_width = sample_width
        self.frame_bytes = frame_bytes
        self.wait_for_device = wait_for_device

        self.ring_buffer = RingBuffer.from_duration(
            duration_seconds=ring_buffer_duration,
            sample_rate=sample_rate,
            sample_width=sample_width,
        )

        self._ser: Optional[serial.Serial] = None
        self._running = False
        self._reader_thread: Optional[threading.Thread] = None

        # Queue of complete audio frames for consumers (e.g. wake word, VAD)
        # Cap queue to ~3 seconds of frames so memory is bounded
        max_queue_frames = int(3.0 * sample_rate * sample_width / frame_bytes)
        self._frame_queue: queue.Queue[bytes] = queue.Queue(maxsize=max_queue_frames)
        self._lock = threading.Lock()
        self._touch_detected = False
        self._touch_lock = threading.Lock()
        self._last_touch_time: float = 0.0
        self._touch_debounce_seconds: float = 0.6
        self._chunk_buffer = bytearray()

        # On-Device Embedded ML Event State
        self._embedded_wake_detected = False
        self._embedded_wake_confidence: float = 0.0
        self._last_embedded_wake_time: float = 0.0
        self._embedded_command: Optional[str] = None
        self._embedded_command_confidence: float = 0.0
        self._embedded_lock = threading.Lock()
        self._device_info: dict = {}
        self._last_heartbeat_time: float = 0.0

        import atexit
        atexit.register(self.stop)

    def start(self) -> None:
        """Connect to the ESP32, initiate the audio stream, and start background reading."""
        if self._running:
            return

        # Auto-detect port if configured as 'auto'
        if not self.port or self.port == "auto":
            from device.discovery import scan_candidate_ports
            from device.handshake import probe_port
            candidates = scan_candidate_ports()
            found_port = None
            for cand in candidates:
                if probe_port(cand.device, baud=self.baud):
                    found_port = cand.device
                    break
            if not found_port and candidates:
                found_port = candidates[0].device
            if not found_port:
                if self.wait_for_device:
                    try:
                        from assistant.lifecycle import get_lifecycle_manager, AppLifecycleState
                        get_lifecycle_manager().transition_to(
                            AppLifecycleState.WAITING_FOR_DEVICE,
                            "Waiting for DeskBot ESP32 via USB..."
                        )
                    except Exception:
                        pass
                    logger.info("[DEVICE] Waiting for DeskBot ESP32 hardware to be plugged in...")
                    while not found_port:
                        time.sleep(1.0)
                        candidates = scan_candidate_ports()
                        for cand in candidates:
                            if probe_port(cand.device, baud=self.baud):
                                found_port = cand.device
                                break
                else:
                    raise RuntimeError(
                        "No DeskBot ESP32 hardware detected. Please plug in your DeskBot via USB."
                    )
            self.port = found_port

        try:
            from assistant.lifecycle import get_lifecycle_manager, AppLifecycleState
            get_lifecycle_manager().transition_to(
                AppLifecycleState.CONNECTING,
                f"Connecting on {self.port}"
            )
        except Exception:
            pass

        logger.info("Opening serial port %s at %d baud...", self.port, self.baud)
        self._ser = serial.Serial(self.port, self.baud, timeout=0.5)


        # 1. Break out of any leftover recordAudio() loop on ESP32 from a prior run
        try:
            self._ser.write(b"STOP_STREAM\n")
            self._ser.flush()
        except Exception:
            pass

        time.sleep(0.2)
        try:
            self._ser.reset_input_buffer()
            self._ser.reset_output_buffer()
        except Exception:
            pass

        # 2. Request clean stream start
        self._ser.write(b"START_STREAM\n")
        self._ser.flush()

        self._wait_for_stream_start()

        self._running = True
        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            name="DeskBotAudioReader",
            daemon=True,
        )
        self._reader_thread.start()
        logger.info("Audio engine started and streaming continuously.")

    def _wait_for_stream_start(self, timeout: float = 8.0) -> None:
        """Wait for the ESP32 confirmation line 'STREAM_START' or incoming PCM stream."""
        deadline = time.monotonic() + timeout
        last_retry = time.monotonic()

        while time.monotonic() < deadline:
            if not self._ser or not self._ser.is_open:
                break

            # If incoming audio is already flowing, the ESP32 stream is active
            try:
                if self._ser.in_waiting > 512:
                    return
            except Exception:
                pass

            line = self._ser.readline()
            if line:
                text = line.decode("ascii", errors="ignore").strip()
                if "STREAM_START" in text:
                    return

            # If nothing received after 1.5s, retry sending START_STREAM
            if time.monotonic() - last_retry > 1.5:
                try:
                    self._ser.write(b"START_STREAM\n")
                    self._ser.flush()
                except Exception:
                    pass
                last_retry = time.monotonic()

        raise RuntimeError(
            f"Timed out waiting for STREAM_START from ESP32 on {self.port}.\n"
            "  -> Hint: If your computer went to sleep or the board froze, press the physical 'RST' button on the ESP32 or reconnect the USB cable."
        )

    def _handle_hardware_event(self, event_type: str, params: dict) -> None:
        """Process structured event emitted by ESP32-S3."""
        logger.debug("[HARDWARE_EVENT] %s: %s", event_type, params)
        if event_type == "WAKE_DETECTED":
            try:
                conf = float(params.get("confidence", 0.85))
            except ValueError:
                conf = 0.85
            with self._embedded_lock:
                self._embedded_wake_detected = True
                self._embedded_wake_confidence = conf
                self._last_embedded_wake_time = time.monotonic()
            logger.info("[HARDWARE_WAKE] ESP32 on-device wake detected (confidence=%.3f)", conf)
        elif event_type == "COMMAND_CLASSIFIED":
            action = str(params.get("action", ""))
            try:
                conf = float(params.get("confidence", 0.85))
            except ValueError:
                conf = 0.85
            with self._embedded_lock:
                self._embedded_command = action
                self._embedded_command_confidence = conf
            logger.info("[HARDWARE_CMD] ESP32 classified command: %s (confidence=%.3f)", action, conf)
        elif event_type == "DEVICE_READY":
            logger.info("[HARDWARE_READY] ESP32-S3 firmware %s (%s)", params.get("version", "2.0"), params.get("board", "ESP32-S3"))
            self._device_info.update(params)
        elif event_type == "TOUCH_TRIGGER":
            with self._touch_lock:
                self._touch_detected = True
        elif event_type == "HEARTBEAT":
            self._last_heartbeat_time = time.monotonic()

    def _process_events(self, raw_bytes: bytes) -> bytes:
        """Parse structured hardware event markers ([EVENT:...], TOUCH_TRIGGER) and strip cleanly."""
        # 1. Handle legacy or direct TOUCH_TRIGGER marker
        if b"TOUCH_TRIGGER" in raw_bytes:
            now = time.monotonic()
            with self._touch_lock:
                if (now - self._last_touch_time) >= self._touch_debounce_seconds:
                    self._last_touch_time = now
                    self._touch_detected = True

            while b"TOUCH_TRIGGER" in raw_bytes:
                pos = raw_bytes.find(b"TOUCH_TRIGGER")
                start = pos
                while start > 0 and raw_bytes[start - 1 : start] in (b"\n", b"\r"):
                    start -= 1
                end = pos + len(b"TOUCH_TRIGGER")
                while end < len(raw_bytes) and raw_bytes[end : end + 1] in (b"\n", b"\r", b"_"):
                    end += 1

                before = raw_bytes[:start]
                after = raw_bytes[end:]
                if len(before) % 2 != 0:
                    before = before[:-1]
                if len(after) % 2 != 0:
                    after = after[1:]
                raw_bytes = before + after

        # 2. Handle structured [EVENT:...] markers
        while b"[EVENT:" in raw_bytes:
            start_pos = raw_bytes.find(b"[EVENT:")
            end_bracket = raw_bytes.find(b"]", start_pos)
            if end_bracket == -1:
                event_line = raw_bytes[start_pos:]
                end_pos = len(raw_bytes)
            else:
                event_line = raw_bytes[start_pos : end_bracket + 1]
                end_pos = end_bracket + 1
                while end_pos < len(raw_bytes) and raw_bytes[end_pos : end_pos + 1] in (b"\n", b"\r"):
                    end_pos += 1

            try:
                ev_str = event_line.decode("utf-8", errors="replace").strip("[]\r\n ")
                parts = ev_str.split(":")
                if len(parts) >= 2 and parts[0] == "EVENT":
                    event_type = parts[1]
                    params = {}
                    for p in parts[2:]:
                        if "=" in p:
                            k, v = p.split("=", 1)
                            params[k] = v
                        else:
                            params[p] = True
                    self._handle_hardware_event(event_type, params)
            except Exception as ev_err:
                logger.debug("Error parsing hardware event: %s", ev_err)

            start = start_pos
            while start > 0 and raw_bytes[start - 1 : start] in (b"\n", b"\r"):
                start -= 1

            before = raw_bytes[:start]
            after = raw_bytes[end_pos:]
            if len(before) % 2 != 0:
                before = before[:-1]
            if len(after) % 2 != 0:
                after = after[1:]
            raw_bytes = before + after

        # 3. Handle STREAM_START and STREAM_END markers
        for marker in (b"STREAM_START", b"STREAM_END"):
            while marker in raw_bytes:
                pos = raw_bytes.find(marker)
                start = pos
                while start > 0 and raw_bytes[start - 1 : start] in (b"\n", b"\r"):
                    start -= 1
                end = pos + len(marker)
                while end < len(raw_bytes) and raw_bytes[end : end + 1] in (b"\n", b"\r"):
                    end += 1
                before = raw_bytes[:start]
                after = raw_bytes[end:]
                if len(before) % 2 != 0:
                    before = before[:-1]
                if len(after) % 2 != 0:
                    after = after[1:]
                raw_bytes = before + after

        return raw_bytes

    def has_embedded_wake(self) -> bool:
        """Return True if ESP32 detected the wake-word on-device."""
        with self._embedded_lock:
            return self._embedded_wake_detected

    def clear_embedded_wake(self) -> None:
        """Clear embedded wake-word flag."""
        with self._embedded_lock:
            self._embedded_wake_detected = False

    def get_embedded_command(self) -> Optional[str]:
        """Return on-device classified command if present."""
        with self._embedded_lock:
            return self._embedded_command

    def clear_embedded_command(self) -> None:
        """Clear on-device classified command."""
        with self._embedded_lock:
            self._embedded_command = None

    def get_device_info(self) -> dict:
        """Return hardware metadata reported by device."""
        with self._embedded_lock:
            return dict(self._device_info)

    def _reader_loop(self) -> None:
        """Background thread continuously pumping PCM bytes from serial into RingBuffer and frame queue."""
        while self._running:
            try:
                if not self._ser or not self._ser.is_open:
                    time.sleep(0.01)
                    continue

                raw_bytes = self._ser.read(4096)
                if not raw_bytes:
                    continue

                raw_bytes = self._process_events(raw_bytes)

                if not raw_bytes:
                    continue

                # Ensure 16-bit PCM word alignment is never corrupted by odd-byte ASCII markers
                if len(raw_bytes) % 2 != 0:
                    raw_bytes = raw_bytes[:len(raw_bytes) - 1]

                if not raw_bytes:
                    continue

                # Write directly to rolling ring buffer for immediate historical context
                self.ring_buffer.write(raw_bytes)
                self._chunk_buffer.extend(raw_bytes)

                # Slice into discrete frames for synchronous consumers
                while len(self._chunk_buffer) >= self.frame_bytes:
                    frame = bytes(self._chunk_buffer[: self.frame_bytes])
                    del self._chunk_buffer[: self.frame_bytes]

                    # Push frame to consumer queue; discard oldest if queue is saturated
                    if self._frame_queue.full():
                        try:
                            self._frame_queue.get_nowait()
                        except queue.Empty:
                            pass
                    try:
                        self._frame_queue.put_nowait(frame)
                    except queue.Full:
                        pass

            except serial.SerialException as error:
                if not self._running:
                    break
                logger.error("Serial read error: %s. Reconnecting...", error)
                time.sleep(0.5)
                self._attempt_reconnect()
            except Exception as error:
                if not self._running:
                    break
                logger.exception("Unexpected error in audio reader: %s", error)
                time.sleep(0.1)

    def _attempt_reconnect(self) -> None:
        """Attempt to recover from a serial disconnect with automatic candidate scanning."""
        logger.warning("[DEVICE] DeskBot disconnected")
        try:
            from assistant.lifecycle import get_lifecycle_manager, AppLifecycleState
            get_lifecycle_manager().transition_to(AppLifecycleState.DISCONNECTED, "DeskBot disconnected")
        except Exception:
            pass

        with self._lock:
            if self._ser:
                try:
                    self._ser.close()
                except Exception:
                    pass
                self._ser = None

        while self._running:
            time.sleep(1.5)
            with self._lock:
                from device.discovery import scan_candidate_ports
                from device.handshake import probe_port
                candidates = scan_candidate_ports()
                target_port = None
                for cand in candidates:
                    if probe_port(cand.device, baud=self.baud):
                        target_port = cand.device
                        break

                if target_port:
                    logger.info("[DEVICE] DeskBot detected on %s", target_port)
                    logger.info("[DEVICE] Handshake successful")
                    try:
                        from assistant.lifecycle import get_lifecycle_manager, AppLifecycleState
                        get_lifecycle_manager().transition_to(AppLifecycleState.CONNECTING, f"Reconnecting to {target_port}")
                    except Exception:
                        pass
                    try:
                        self.port = target_port
                        self._ser = serial.Serial(self.port, self.baud, timeout=0.5)
                        self._ser.write(b"STOP_STREAM\n")
                        self._ser.flush()
                        time.sleep(0.1)
                        self._ser.reset_input_buffer()
                        self._ser.write(b"START_STREAM\n")
                        self._ser.flush()
                        self._wait_for_stream_start(timeout=5.0)
                        logger.info("[DEVICE] Reconnected")
                        logger.info("[DEVICE] Audio restored")
                        try:
                            from assistant.lifecycle import get_lifecycle_manager, AppLifecycleState
                            get_lifecycle_manager().transition_to(AppLifecycleState.READY, f"Reconnected on {self.port}")
                        except Exception:
                            pass
                        return

                    except Exception as rec_err:
                        logger.debug("Serial reconnect init failed: %s", rec_err)


    def read_frame(self, timeout: float = 1.0) -> bytes:
        """Read a single PCM frame of `self.frame_bytes`."""
        try:
            return self._frame_queue.get(timeout=timeout)
        except queue.Empty:
            return b""

    def drain_frames(self) -> None:
        """Drain any frames currently in the queue, ring buffer, and partial chunk buffer."""
        self._chunk_buffer.clear()
        while not self._frame_queue.empty():
            try:
                self._frame_queue.get_nowait()
            except queue.Empty:
                break
        self.ring_buffer.clear()

    def send_command(self, cmd: str) -> bool:
        """Send a text command line to the ESP32 (e.g. for OLED state sync)."""
        with self._lock:
            if self._ser and self._ser.is_open:
                try:
                    line = f"{cmd.strip()}\n".encode("ascii")
                    self._ser.write(line)
                    self._ser.flush()
                    return True
                except Exception as err:
                    logger.debug("Failed to send command '%s' to ESP32: %s", cmd, err)
                    return False
            return False

    def check_and_consume_touch(self) -> bool:
        """Atomically check and consume whether a touch trigger occurred."""
        with self._touch_lock:
            if self._touch_detected:
                self._touch_detected = False
                return True
            return False

    def has_touch_trigger(self) -> bool:
        """Check if a touch trigger is currently pending without consuming it."""
        with self._touch_lock:
            return self._touch_detected

    def clear_touch(self) -> None:
        """Clear any pending touch trigger."""
        with self._touch_lock:
            self._touch_detected = False

    def stop(self) -> None:
        """Stop background reading, send STOP_STREAM to ESP32, and close serial port."""
        self._running = False

        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=1.0)

        with self._lock:
            if self._ser and self._ser.is_open:
                try:
                    self._ser.write(b"STOP_STREAM\n")
                    self._ser.flush()
                except Exception:
                    pass
                time.sleep(0.1)
                try:
                    self._ser.close()
                except Exception:
                    pass
                self._ser = None

        logger.info("Audio engine stopped.")

    def __enter__(self) -> AudioEngine:
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()
