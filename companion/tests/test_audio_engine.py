"""Unit and simulation tests for DeskBot audio engine, ring buffer, and speech detector."""

import math
import struct
import time
import unittest
from pathlib import Path
import sys

COMPANION_DIR = Path(__file__).resolve().parent.parent
if str(COMPANION_DIR) not in sys.path:
    sys.path.insert(0, str(COMPANION_DIR))

from audio.ring_buffer import RingBuffer
from audio.speech_detector import SpeechDetector


def generate_voice_pcm(duration_seconds: float, sample_rate: int = 16000) -> bytes:
    """Generate pitch-modulated multi-harmonic PCM frames resembling human voice for WebRTC VAD."""
    num_samples = int(duration_seconds * sample_rate)
    samples = []
    for i in range(num_samples):
        t = i / sample_rate
        f0 = 200 + 40 * math.sin(2 * math.pi * 5 * t)
        val = int(
            8000 * math.sin(2 * math.pi * f0 * t)
            + 4000 * math.sin(2 * math.pi * 2 * f0 * t)
            + 2000 * math.sin(2 * math.pi * 3 * f0 * t)
        )
        samples.append(val)
    return struct.pack(f"<{len(samples)}h", *samples)


def generate_silence(duration_seconds: float, sample_rate: int = 16000) -> bytes:
    """Generate quiet/silent PCM frames."""
    num_samples = int(duration_seconds * sample_rate)
    return b"\x00\x00" * num_samples


class TestRingBuffer(unittest.TestCase):
    def test_init_and_capacity(self):
        rb = RingBuffer(100)
        self.assertEqual(rb.capacity, 100)
        self.assertEqual(len(rb), 0)
        self.assertEqual(rb.get_all(), b"")

    def test_write_and_read(self):
        rb = RingBuffer(10)
        rb.write(b"1234")
        self.assertEqual(len(rb), 4)
        self.assertEqual(rb.get_recent(4), b"1234")
        self.assertEqual(rb.get_recent(2), b"34")

    def test_wraparound_chronological(self):
        rb = RingBuffer(6)
        rb.write(b"ABC")  # buffer: ABC
        rb.write(b"DEF")  # buffer: ABCDEF
        rb.write(b"GH")   # buffer: GHEF -> chronological: CDEFGH
        self.assertEqual(len(rb), 6)
        self.assertEqual(rb.get_all(), b"CDEFGH")
        self.assertEqual(rb.get_recent(3), b"FGH")

    def test_overflow_single_write(self):
        rb = RingBuffer(4)
        rb.write(b"12345678")
        self.assertEqual(len(rb), 4)
        self.assertEqual(rb.get_all(), b"5678")

    def test_clear(self):
        rb = RingBuffer(10)
        rb.write(b"HELLO")
        rb.clear()
        self.assertEqual(len(rb), 0)
        self.assertEqual(rb.get_all(), b"")

    def test_from_duration(self):
        rb = RingBuffer.from_duration(duration_seconds=1.5, sample_rate=16000, sample_width=2)
        expected_bytes = int(1.5 * 16000 * 2)
        self.assertEqual(rb.capacity, expected_bytes)


class TestSpeechDetector(unittest.TestCase):
    def setUp(self):
        self.sample_rate = 16000
        self.sample_width = 2
        self.detector = SpeechDetector(
            sample_rate=self.sample_rate,
            sample_width=self.sample_width,
            frame_duration_ms=30,
            vad_mode=2,
            pre_roll_seconds=0.09,
            silence_duration_seconds=0.09,
            initial_speech_timeout=0.2,
            max_command_seconds=1.0,
            transition_window_seconds=0.15,
        )
        self.frame_bytes = self.detector.frame_bytes

    def test_frame_vad(self):
        speech_frame = generate_voice_pcm(0.03, self.sample_rate)[: self.frame_bytes]
        silence_frame = generate_silence(0.03, self.sample_rate)[: self.frame_bytes]

        self.assertTrue(self.detector.is_speech_frame(speech_frame))
        self.assertFalse(self.detector.is_speech_frame(silence_frame))

    def test_simulation_pattern_a_continuous_speech(self):
        """Pattern A: Continuous speech immediately after wake."""
        ring_buffer = RingBuffer.from_duration(0.5, self.sample_rate, self.sample_width)
        ring_buffer.write(generate_voice_pcm(0.1, self.sample_rate))

        # Continuous command speech: 0.3s voice + 0.2s silence
        command = generate_voice_pcm(0.3, self.sample_rate)
        trailing = generate_silence(0.2, self.sample_rate)
        stream = command + trailing

        frames = [
            stream[i : i + self.frame_bytes]
            for i in range(0, len(stream), self.frame_bytes)
            if len(stream[i : i + self.frame_bytes]) == self.frame_bytes
        ]

        frame_idx = [0]
        def read_frame():
            if frame_idx[0] < len(frames):
                f = frames[frame_idx[0]]
                frame_idx[0] += 1
                return f
            return generate_silence(0.03, self.sample_rate)[: self.frame_bytes]

        speech_started = []
        speech_ended = []

        result = self.detector.capture_utterance(
            read_frame_fn=read_frame,
            ring_buffer=ring_buffer,
            on_speech_start=lambda: speech_started.append(True),
            on_speech_end=lambda: speech_ended.append(True),
        )

        self.assertIsNotNone(result)
        self.assertTrue(len(speech_started) > 0)
        self.assertTrue(len(speech_ended) > 0)
        self.assertTrue(len(result) > 0)

    def test_simulation_pattern_b_pause_after_wake(self):
        """Pattern B: Pause after wake word, followed by command."""
        ring_buffer = RingBuffer.from_duration(0.5, self.sample_rate, self.sample_width)
        ring_buffer.write(generate_voice_pcm(0.1, self.sample_rate))

        # 0.2s silence pause + 0.3s voice + 0.2s trailing silence
        pause = generate_silence(0.2, self.sample_rate)
        command = generate_voice_pcm(0.3, self.sample_rate)
        trailing = generate_silence(0.2, self.sample_rate)
        stream = pause + command + trailing

        frames = [
            stream[i : i + self.frame_bytes]
            for i in range(0, len(stream), self.frame_bytes)
            if len(stream[i : i + self.frame_bytes]) == self.frame_bytes
        ]

        frame_idx = [0]
        def read_frame():
            if frame_idx[0] < len(frames):
                f = frames[frame_idx[0]]
                frame_idx[0] += 1
                return f
            return generate_silence(0.03, self.sample_rate)[: self.frame_bytes]

        result = self.detector.capture_utterance(
            read_frame_fn=read_frame,
            ring_buffer=ring_buffer,
        )

        self.assertIsNotNone(result)
        self.assertTrue(len(result) > 0)

    def test_simulation_silence_timeout(self):
        """Wake detected but no speech spoken -> timeout returns None."""
        ring_buffer = RingBuffer.from_duration(0.5, self.sample_rate, self.sample_width)

        def read_frame():
            time.sleep(0.01)
            return generate_silence(0.03, self.sample_rate)[: self.frame_bytes]

        result = self.detector.capture_utterance(
            read_frame_fn=read_frame,
            ring_buffer=ring_buffer,
        )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
