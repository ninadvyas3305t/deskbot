"""Thread-safe rolling PCM ring buffer for audio context retention."""

from __future__ import annotations

import threading


class RingBuffer:
    """Thread-safe circular byte buffer for audio PCM data."""

    def __init__(self, capacity_bytes: int):
        if capacity_bytes <= 0:
            raise ValueError("Capacity must be greater than 0.")
        self.capacity = capacity_bytes
        self._buffer = bytearray(capacity_bytes)
        self._write_pos = 0
        self._size = 0
        self._lock = threading.RLock()

    @classmethod
    def from_duration(
        cls,
        duration_seconds: float = 2.0,
        sample_rate: int = 16000,
        sample_width: int = 2,
    ) -> RingBuffer:
        """Create a ring buffer sized for a specific duration of PCM audio."""
        capacity_bytes = int(duration_seconds * sample_rate) * sample_width
        return cls(capacity_bytes)

    def write(self, data: bytes | bytearray | memoryview) -> None:
        """Write raw audio bytes into the ring buffer, overwriting oldest data if full."""
        if not data:
            return

        data_bytes = bytes(data)
        data_len = len(data_bytes)

        with self._lock:
            if data_len >= self.capacity:
                # If incoming data exceeds capacity, keep only the most recent chunk
                self._buffer[:] = data_bytes[-self.capacity:]
                self._write_pos = 0
                self._size = self.capacity
                return

            first_part = min(data_len, self.capacity - self._write_pos)
            second_part = data_len - first_part

            self._buffer[self._write_pos : self._write_pos + first_part] = data_bytes[:first_part]

            if second_part > 0:
                self._buffer[:second_part] = data_bytes[first_part:]
                self._write_pos = second_part
            else:
                self._write_pos = (self._write_pos + first_part) % self.capacity

            self._size = min(self.capacity, self._size + data_len)

    def get_recent(self, num_bytes: int) -> bytes:
        """Retrieve the most recent `num_bytes` in chronological order."""
        with self._lock:
            if num_bytes <= 0 or self._size == 0:
                return b""

            actual_bytes = min(num_bytes, self._size)
            start_pos = (self._write_pos - actual_bytes) % self.capacity

            if start_pos + actual_bytes <= self.capacity:
                return bytes(self._buffer[start_pos : start_pos + actual_bytes])
            else:
                first_len = self.capacity - start_pos
                second_len = actual_bytes - first_len
                return (
                    bytes(self._buffer[start_pos : self.capacity])
                    + bytes(self._buffer[:second_len])
                )

    def get_recent_seconds(
        self,
        seconds: float,
        sample_rate: int = 16000,
        sample_width: int = 2,
    ) -> bytes:
        """Retrieve recent audio by duration in seconds."""
        num_bytes = int(seconds * sample_rate) * sample_width
        return self.get_recent(num_bytes)

    def get_all(self) -> bytes:
        """Retrieve all currently buffered audio in chronological order."""
        with self._lock:
            return self.get_recent(self._size)

    def clear(self) -> None:
        """Reset the buffer state."""
        with self._lock:
            self._write_pos = 0
            self._size = 0

    def __len__(self) -> int:
        with self._lock:
            return self._size
