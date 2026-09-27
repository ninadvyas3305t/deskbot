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
    ):
        self.port = port
        self.baud = baud
        self.sample_rate = sample_rate
        self.sample_width = sample_width
        self.frame_bytes = frame_bytes

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
        self._chunk_buffer = bytearray()
        import atexit
        atexit.register(self.stop)

    def start(self) -> None:
        """Connect to the ESP32, initiate the audio stream, and start background reading."""
        if self._running:
            return

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

                # Intercept hardware TTP223 touch sensor marker from ESP32
                if b"TOUCH_TRIGGER" in raw_bytes:
                    with self._touch_lock:
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

                        # Align 'before' to 16-bit boundary (drop odd trailing byte)
                        if len(before) % 2 != 0:
                            before = before[:-1]
                        # Align 'after' so 16-bit PCM word phase is strictly maintained
                        if len(after) % 2 != 0:
                            after = after[1:]

                        raw_bytes = before + after

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
        """Attempt to recover from a transient serial disconnect."""
        with self._lock:
            try:
                if self._ser:
                    try:
                        self._ser.close()
                    except Exception:
                        pass
                time.sleep(1.0)
                self._ser = serial.Serial(self.port, self.baud, timeout=1)
                self._ser.write(b"START_STREAM\n")
                self._ser.flush()
                self._wait_for_stream_start(timeout=5.0)
                logger.info("Successfully reconnected to ESP32 on %s.", self.port)
            except Exception as reconnect_err:
                logger.warning("Serial reconnect attempt failed: %s", reconnect_err)

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
