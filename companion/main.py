"""DeskBot main launcher and voice command pipeline."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

COMPANION_DIR = Path(__file__).resolve().parent

RECORDER = COMPANION_DIR / "receive_audio.py"
TRANSCRIBER = COMPANION_DIR / "speech_to_text.py"
AI_BRAIN = COMPANION_DIR / "ai_brain.py"
COMMAND_EXECUTOR = COMPANION_DIR / "command_executor.py"
CONTINUOUS_ASSISTANT = COMPANION_DIR / "continuous_assistant.py"
DEFAULT_AUDIO = COMPANION_DIR / "test_recording.wav"


def run_process(command: list[str]) -> subprocess.CompletedProcess:
    """Run a companion stage as a subprocess."""
    return subprocess.run(
        command,
        cwd=COMPANION_DIR,
        check=False,
        capture_output=True,
        text=True,
    )


def run_continuous(args: argparse.Namespace) -> int:
    """Launch the continuous voice assistant engine."""
    command = [
        sys.executable,
        str(CONTINUOUS_ASSISTANT),
    ]

    if args.model:
        command.extend(["--stt-model", args.model])

    if args.wake_model:
        command.extend(["--wake-model", args.wake_model])

    if args.wake_threshold is not None:
        command.extend(["--wake-threshold", str(args.wake_threshold)])

    if args.once:
        command.append("--once")

    if args.debug:
        command.append("--debug")

    # Run interactively so terminal output streams in real-time
    result = subprocess.run(
        command,
        cwd=COMPANION_DIR,
        check=False,
    )
    return result.returncode


def capture_audio() -> int:
    """Capture audio from DeskBot (legacy one-shot capture)."""
    print("=== DeskBot: capture ===", flush=True)

    result = run_process([
        sys.executable,
        str(RECORDER),
    ])

    print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    return result.returncode


def transcribe_audio(model: str | None = None) -> str | None:
    """Transcribe the recorded WAV file."""
    print("\n=== DeskBot: speech-to-text ===", flush=True)

    command = [
        sys.executable,
        str(TRANSCRIBER),
        str(DEFAULT_AUDIO),
    ]

    if model:
        command.extend(["--model", model])

    result = run_process(command)

    print(result.stdout, end="")
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return None

    for line in result.stdout.splitlines():
        if line.startswith("You said:"):
            transcript = line[len("You said:"):].strip()
            return transcript.strip('"')

    return None


def ask_ai(transcript: str) -> dict | None:
    """Send the transcript to Nemotron and parse its JSON intent."""
    print("\n=== DeskBot: AI brain ===", flush=True)

    result = run_process([
        sys.executable,
        str(AI_BRAIN),
        transcript,
    ])

    print(result.stdout, end="")
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return None

    raw_response = result.stdout.strip()
    if not raw_response:
        print("AI brain returned an empty response.")
        return None

    try:
        intent = json.loads(raw_response)
    except json.JSONDecodeError as error:
        print(f"Could not parse AI response as JSON: {error}", file=sys.stderr)
        return None

    if not isinstance(intent, dict):
        print("AI response is not a JSON object.")
        return None

    return intent


def execute_intent(intent: dict) -> int:
    """Send the AI intent to the command executor."""
    print("\n=== DeskBot: command execution ===", flush=True)

    intent_json = json.dumps(intent)
    result = run_process([
        sys.executable,
        str(COMMAND_EXECUTOR),
        intent_json,
    ])

    print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    return result.returncode


def run_legacy_pipeline(args: argparse.Namespace) -> int:
    """Run one-shot step-by-step pipeline."""
    if not args.transcribe_only:
        status = capture_audio()
        if status != 0:
            print("Capture failed. Pipeline stopped.", file=sys.stderr)
            return status

    transcript = transcribe_audio(args.model)
    if not transcript:
        print("\nNo transcript available. Pipeline stopped.")
        return 1

    print(f"\nTranscript: {transcript}")

    intent = ask_ai(transcript)
    if intent is None:
        print("\nAI understanding failed. Pipeline stopped.")
        return 1

    return execute_intent(intent)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="DeskBot: Physical AI Desktop Companion Voice Assistant."
    )

    parser.add_argument(
        "--transcribe-only",
        action="store_true",
        help="Skip ESP32 capture and transcribe the existing test WAV file.",
    )
    parser.add_argument(
        "--single-step",
        action="store_true",
        help="Run legacy one-shot pipeline instead of continuous listening.",
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Explicit flag for continuous listening (default).",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Optional Faster-Whisper model name.",
    )
    parser.add_argument(
        "--wake-model",
        default=None,
        help="Wake-word model name or path.",
    )
    parser.add_argument(
        "--wake-threshold",
        type=float,
        default=None,
        help="Wake confidence threshold.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Exit after one wake activation (for testing).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging output.",
    )

    args = parser.parse_args()

    # If transcribe-only or single-step is explicitly requested, run legacy pipeline
    if args.transcribe_only or args.single_step:
        return run_legacy_pipeline(args)

    # By default, DeskBot runs continuously as an always-listening desktop voice assistant
    return run_continuous(args)


if __name__ == "__main__":
    raise SystemExit(main())
