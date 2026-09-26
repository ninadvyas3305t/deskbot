"""Transcribe a DeskBot WAV recording locally with Faster-Whisper."""

from __future__ import annotations

import argparse
import os
import re
import sys
import wave
from pathlib import Path
from typing import Any


DEFAULT_AUDIO = Path(__file__).with_name("test_recording.wav")
DEFAULT_MODEL = os.getenv("DESKBOT_STT_MODEL", "base")
DEFAULT_LANGUAGE = "en"
DEFAULT_PROMPT = (
    "DeskBot voice commands: notes.txt, main.py, open, delete, create, play, "
    "volume, mute, unmute, YouTube, Spotify, calculator."
)
DEFAULT_HOTWORDS = (
    "Hey Jarvis, yes, no, notes, main, delete, create, open, play, screenshot, "
    "folder, file, explorer, volume, mute"
)


def validate_audio(path: Path) -> None:
    """Fail early with a useful message if the recorder output is not usable."""

    if not path.is_file():
        raise FileNotFoundError(
            f"Audio file not found: {path}\n"
            "Run receive_audio.py first, or pass a WAV file path to this script."
        )

    with wave.open(str(path), "rb") as recording:
        channels = recording.getnchannels()
        sample_width = recording.getsampwidth()
        sample_rate = recording.getframerate()
        frames = recording.getnframes()

    if channels != 1 or sample_width != 2 or sample_rate != 16_000:
        raise ValueError(
            "DeskBot STT expects a 16 kHz, 16-bit, mono WAV. "
            f"Received {sample_rate} Hz, "
            f"{sample_width * 8}-bit, "
            f"{channels} channel(s)."
        )

    if frames == 0:
        raise ValueError("The WAV file contains no audio frames.")


def is_hallucination(text: str) -> bool:
    """Check if transcribed text is a Whisper hallucination, repetition loop, or silence artifact."""
    if not text:
        return True

    cleaned = text.strip().lower()
    if not cleaned:
        return True

    # 1. Repetition check: any phrase of 1-6 words repeating 2 or more times
    # e.g. "I'm sorry, I'm sorry, I'm sorry", "thank you, thank you, thank you"
    repetition_pattern = re.compile(
        r"(\b[\w\']+(?:\s+[\w\']+){0,5}\b)(?:[,\s]+(?:\1)){2,}",
        re.IGNORECASE,
    )
    if repetition_pattern.search(cleaned):
        return True

    # 2. Token vocabulary collapse: 4+ words but only 1 or 2 distinct words
    words = [w.strip(".,?!;:`'\"") for w in cleaned.split() if w.strip(".,?!;:`'\"")]
    if len(words) >= 4 and len(set(words)) <= 2:
        return True

    # 3. Single filler words / noise artifacts (e.g. "and", "so", "you", "um", "uh")
    single_fillers = {
        "and", "so", "or", "but", "the", "a", "an", "you", "to", "of",
        "in", "for", "on", "at", "by", "with", "from", "up", "about",
        "into", "over", "after", "um", "uh", "ah", "oh", "er", "hmm", "mm",
    }
    if len(words) <= 2 and all(w in single_fillers for w in words):
        return True

    # 4. Known subtitle / silence hallucination patterns commonly emitted on quiet audio
    silence_patterns = [
        r"^i'?m\s+sorry[.!?, ]*$",
        r"^sorry[.!?, ]*$",
        r"subtitles\s+by",
        r"amara\.org",
        r"thank\s+you\s+for\s+watching",
        r"thanks\s+for\s+watching",
        r"^please\s+subscribe",
        r"^like\s+and\s+subscribe",
        r"^you[.!?, ]*$",
        r"^\[.*\]$",
        r"^\(.*\)$",
        r"\bmute[,\s]+mute\b",
    ]
    for pattern in silence_patterns:
        if re.search(pattern, cleaned):
            return True

    return False


_MODEL_CACHE: dict[str, Any] = {}


def get_whisper_model(
    model_name: str = DEFAULT_MODEL,
    cpu_threads: int = 4,
) -> Any:
    """Return a cached WhisperModel singleton for the requested model."""
    if model_name not in _MODEL_CACHE:
        try:
            from faster_whisper import WhisperModel
        except ImportError as error:
            raise RuntimeError(
                "Faster-Whisper is not installed. "
                "Run: python -m pip install -r requirements.txt"
            ) from error

        print(f"Loading Whisper model ({model_name})...", flush=True)
        _MODEL_CACHE[model_name] = WhisperModel(
            model_name,
            device="cpu",
            compute_type="int8",
            cpu_threads=cpu_threads,
        )
    return _MODEL_CACHE[model_name]


def transcribe(
    audio_path: Path,
    model_name: str | Any = DEFAULT_MODEL,
    initial_prompt: str | None = None,
    hotwords: str | None = None,
) -> tuple[str, str]:
    """Return transcript and language using cached Whisper model."""

    if hasattr(model_name, "transcribe"):
        model = model_name
    else:
        model = get_whisper_model(str(model_name))

    transcribe_kwargs: dict[str, Any] = {
        "language": DEFAULT_LANGUAGE,
        "beam_size": 1,
        "best_of": 1,
        "vad_filter": False,
        "condition_on_previous_text": False,
        "temperature": 0,
        "repetition_penalty": 1.2,
        "no_repeat_ngram_size": 3,
    }
    if initial_prompt:
        transcribe_kwargs["initial_prompt"] = initial_prompt
    if hotwords:
        transcribe_kwargs["hotwords"] = hotwords

    segments, info = model.transcribe(
        str(audio_path),
        **transcribe_kwargs,
    )

    valid_segments: list[str] = []
    for segment in segments:
        text = segment.text.strip()
        # Filter high compression ratio (classic Whisper repetition hallucination signal)
        if hasattr(segment, "compression_ratio") and segment.compression_ratio > 2.4:
            continue
        # Filter high no_speech_prob on noise/silence
        if hasattr(segment, "no_speech_prob") and segment.no_speech_prob > 0.85:
            continue
        if text:
            valid_segments.append(text)

    transcript = " ".join(valid_segments).strip()

    if is_hallucination(transcript):
        return "", info.language

    return transcript, info.language


def main() -> int:

    parser = argparse.ArgumentParser(
        description="Transcribe a DeskBot WAV recording locally."
    )

    parser.add_argument(
        "audio",
        nargs="?",
        type=Path,
        default=DEFAULT_AUDIO,
    )

    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Faster-Whisper model name.",
    )

    args = parser.parse_args()

    try:
        validate_audio(args.audio)

        print(f"Transcribing: {args.audio.name}")
        print(f"Model: {args.model} (local CPU)")
        print("Language: English (forced)")

        transcript, language = transcribe(
            args.audio,
            args.model,
        )

    except (
        FileNotFoundError,
        ValueError,
        RuntimeError,
        wave.Error,
    ) as error:

        print(
            f"STT error: {error}",
            file=sys.stderr,
        )

        return 1

    if not transcript:

        print(
            "No speech was detected. "
            "Try recording again a little closer to the microphone."
        )

        return 2

    print()
    print(f"Language used: {language}")
    print(f'You said: "{transcript}"')

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
