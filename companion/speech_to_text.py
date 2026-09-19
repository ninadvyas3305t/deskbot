"""Transcribe a DeskBot WAV recording locally with Faster-Whisper."""

from __future__ import annotations

import argparse
import os
import sys
import wave
from pathlib import Path


DEFAULT_AUDIO = Path(__file__).with_name("test_recording.wav")
DEFAULT_MODEL = os.getenv("DESKBOT_STT_MODEL", "base")
DEFAULT_LANGUAGE = "en"


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


def transcribe(
    audio_path: Path,
    model_name: str,
) -> tuple[str, str]:
    """Return transcript and language."""

    try:
        from faster_whisper import WhisperModel
    except ImportError as error:
        raise RuntimeError(
            "Faster-Whisper is not installed. "
            "Run: python -m pip install -r requirements.txt"
        ) from error

    print("Loading Whisper model...")

    model = WhisperModel(
        model_name,
        device="cpu",
        compute_type="int8",
    )

    segments, info = model.transcribe(
        str(audio_path),

        # DeskBot user speaks English.
        language=DEFAULT_LANGUAGE,

        # Speech recognition settings.
        beam_size=5,
        best_of=5,

        # Ignore long silent sections.
        vad_filter=True,

        # Prevent previous text from influencing recognition.
        condition_on_previous_text=False,

        # More conservative transcription.
        temperature=0,
    )

    transcript = " ".join(
        segment.text.strip()
        for segment in segments
    ).strip()

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
