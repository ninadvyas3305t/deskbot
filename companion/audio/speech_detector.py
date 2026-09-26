"""Intelligent speech detection using WebRTC VAD and audio ring buffers."""

from __future__ import annotations

import time
from collections import deque
from typing import Callable

import numpy as np
import webrtcvad

from .ring_buffer import RingBuffer


class SpeechDetector:
    """Detects spoken utterances using WebRTC VAD with support for continuous speech and pauses."""

    def __init__(
        self,
        sample_rate: int = 16000,
        sample_width: int = 2,
        frame_duration_ms: int = 30,
        vad_mode: int = 2,
        pre_roll_seconds: float = 0.35,
        silence_duration_seconds: float = 0.8,
        initial_speech_timeout: float = 4.5,
        max_command_seconds: float = 12.0,
        transition_window_seconds: float = 0.3,
        min_speech_amplitude: int = 80,
    ):
        if frame_duration_ms not in (10, 20, 30):
            raise ValueError("WebRTC VAD only supports 10, 20, or 30 ms frames.")

        self.sample_rate = sample_rate
        self.sample_width = sample_width
        self.frame_duration_ms = frame_duration_ms
        self.frame_samples = int(sample_rate * frame_duration_ms / 1000)
        self.frame_bytes = self.frame_samples * sample_width

        self.vad = webrtcvad.Vad(vad_mode)
        self.pre_roll_seconds = pre_roll_seconds
        self.pre_roll_frames_count = max(1, int(pre_roll_seconds * 1000 / frame_duration_ms))
        self.silence_frames_threshold = max(1, int(silence_duration_seconds * 1000 / frame_duration_ms))
        self.initial_speech_timeout = initial_speech_timeout
        self.max_command_seconds = max_command_seconds
        self.transition_frames_count = max(1, int(transition_window_seconds * 1000 / frame_duration_ms))
        # Silence frames required during transition to confirm user paused after wake word
        self.pause_silence_threshold = max(2, int(0.15 * 1000 / frame_duration_ms))
        self.min_speech_amplitude = min_speech_amplitude
        # Sustained speech frames required before declaring speech active (filters 1-frame transient noise/clicks)
        self.min_speech_onset_frames = max(2, int(0.06 * 1000 / frame_duration_ms))

    def is_speech_frame(self, frame: bytes) -> bool:
        """Check whether a single PCM frame contains speech."""
        if len(frame) != self.frame_bytes:
            raise ValueError(f"Expected frame of {self.frame_bytes} bytes, got {len(frame)}.")

        # Audio energy pre-filter: dead digital silence cannot be human speech
        audio_array = np.frombuffer(frame, dtype=np.int16)
        if int(np.max(np.abs(audio_array))) < self.min_speech_amplitude:
            return False

        return self.vad.is_speech(frame, self.sample_rate)

    def capture_utterance(
        self,
        read_frame_fn: Callable[[], bytes],
        ring_buffer: RingBuffer | None = None,
        on_speech_start: Callable[[], None] | None = None,
        on_speech_end: Callable[[], None] | None = None,
        initial_timeout: float | None = None,
        in_wake_transition: bool = True,
    ) -> bytes | None:
        """Capture one spoken command from an audio frame provider.

        Handles:
        - Pattern A: Continuous speech immediately following wake word.
        - Pattern B: Pauses after wake word, capturing command upon speech onset.
        - Follow-up: Direct speech capture without wake-word transition.
        - Timeouts: Safe return to IDLE if no command speech occurs.
        """
        # Snapshot recent pre-roll from ring buffer if available
        pre_roll_bytes_count = self.pre_roll_frames_count * self.frame_bytes
        initial_pre_roll = ring_buffer.get_recent(pre_roll_bytes_count) if ring_buffer else b""

        # Sliding pre-roll deque for when waiting during a pause
        pre_roll_deque: deque[bytes] = deque(maxlen=self.pre_roll_frames_count)
        if initial_pre_roll:
            for i in range(0, len(initial_pre_roll), self.frame_bytes):
                chunk = initial_pre_roll[i : i + self.frame_bytes]
                if len(chunk) == self.frame_bytes:
                    pre_roll_deque.append(chunk)

        recording = bytearray()
        transition_buffer = bytearray()

        transition_frames_evaluated = 0
        transition_silence_count = 0

        speech_active = False
        consecutive_silence = 0
        speech_start_announced = False
        consecutive_speech = 0
        onset_candidate_frames: list[bytes] = []

        start_time = time.monotonic()
        deadline = start_time + self.max_command_seconds
        timeout_val = initial_timeout if initial_timeout is not None else self.initial_speech_timeout
        initial_timeout_deadline = start_time + timeout_val

        while time.monotonic() < deadline:
            frame = read_frame_fn()
            if not frame:
                time.sleep(0.005)
                continue

            is_speech = self.is_speech_frame(frame)

            # --- Wake transition phase (evaluates whether user paused or spoke continuously) ---
            if in_wake_transition:
                transition_frames_evaluated += 1
                transition_buffer.extend(frame)

                if not is_speech:
                    transition_silence_count += 1
                else:
                    transition_silence_count = 0

                # If silence is observed during the transition window, the user paused (Pattern B)
                if transition_silence_count >= self.pause_silence_threshold:
                    in_wake_transition = False
                    transition_buffer.clear()
                    speech_active = False
                    consecutive_speech = 0
                    onset_candidate_frames.clear()
                    pre_roll_deque.clear()
                    pre_roll_deque.append(frame)
                    continue

                # If user kept speaking through the transition window, speech is continuous (Pattern A)
                if transition_frames_evaluated >= self.transition_frames_count:
                    in_wake_transition = False
                    speech_active = True
                    # Seed recording with pre-roll and transition audio
                    recording.extend(b"".join(pre_roll_deque))
                    recording.extend(transition_buffer)
                    transition_buffer.clear()
                    if on_speech_start and not speech_start_announced:
                        on_speech_start()
                        speech_start_announced = True
                    continue

                continue

            # --- Waiting for command speech onset (after confirmed pause) ---
            if not speech_active:
                if time.monotonic() > initial_timeout_deadline:
                    # Timed out waiting for speech to begin
                    return None

                if is_speech:
                    consecutive_speech += 1
                    onset_candidate_frames.append(frame)
                    if consecutive_speech >= self.min_speech_onset_frames:
                        speech_active = True
                        recording.extend(b"".join(pre_roll_deque))
                        for f in onset_candidate_frames:
                            recording.extend(f)
                        onset_candidate_frames.clear()
                        consecutive_silence = 0
                        if on_speech_start and not speech_start_announced:
                            on_speech_start()
                            speech_start_announced = True
                else:
                    consecutive_speech = 0
                    onset_candidate_frames.clear()
                    pre_roll_deque.append(frame)

            # --- Speech is actively being recorded ---
            else:
                recording.extend(frame)
                if is_speech:
                    consecutive_silence = 0
                else:
                    consecutive_silence += 1
                    if consecutive_silence >= self.silence_frames_threshold:
                        if on_speech_end:
                            on_speech_end()
                        # Minimum duration filter: require at least 0.3s of total audio
                        min_bytes = int(0.3 * self.sample_rate * self.sample_width)
                        if len(recording) < min_bytes:
                            return None
                        return bytes(recording)

        # Reached max command duration limit while speaking
        if speech_active and len(recording) > 0:
            if on_speech_end:
                on_speech_end()
            min_bytes = int(0.3 * self.sample_rate * self.sample_width)
            if len(recording) < min_bytes:
                return None
            return bytes(recording)

        return None
