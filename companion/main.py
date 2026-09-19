"""DeskBot complete voice-to-AI command pipeline."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

COMPANION_DIR = Path(__file__).parent

RECORDER = COMPANION_DIR / "receive_audio.py"
TRANSCRIBER = COMPANION_DIR / "speech_to_text.py"
AI_BRAIN = COMPANION_DIR / "ai_brain.py"
COMMAND_EXECUTOR = COMPANION_DIR / "command_executor.py"
DEFAULT_AUDIO = COMPANION_DIR / "test_recording.wav"


def run(command: list[str]) -> subprocess.CompletedProcess:
    """Run a companion stage."""
    return subprocess.run(
        command,
        cwd=COMPANION_DIR,
        check=False,
        capture_output=True,
        text=True,
    )


def capture_audio() -> int:
    """Capture audio from DeskBot."""
    print("=== DeskBot: capture ===", flush=True)

    result = run([
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
        command.extend([
            "--model",
            model,
        ])

    result = run(command)

    print(result.stdout, end="")

    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return None

    for line in result.stdout.splitlines():
        if line.startswith("You said:"):
            transcript = line[len("You said:"):].strip()

            # Remove surrounding quotation marks.
            transcript = transcript.strip('"')

            return transcript

    return None


def ask_ai(transcript: str) -> dict | None:
    """Send the transcript to Nemotron and parse its JSON intent."""
    print("\n=== DeskBot: AI brain ===", flush=True)

    result = run([
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
        print(
            f"Could not parse AI response as JSON: {error}",
            file=sys.stderr,
        )
        return None

    if not isinstance(intent, dict):
        print("AI response is not a JSON object.")
        return None

    return intent


def execute_intent(intent: dict) -> int:
    """Send the AI intent to the command executor."""
    print("\n=== DeskBot: command execution ===", flush=True)

    intent_json = json.dumps(intent)

    result = run([
        sys.executable,
        str(COMMAND_EXECUTOR),
        intent_json,
    ])

    print(result.stdout, end="")

    if result.stderr:
        print(result.stderr, file=sys.stderr)

    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the complete DeskBot voice-to-AI pipeline."
    )

    parser.add_argument(
        "--transcribe-only",
        action="store_true",
        help="Skip ESP32 capture and use the existing WAV file.",
    )

    parser.add_argument(
        "--model",
        default=None,
        help="Optional Faster-Whisper model name.",
    )

    args = parser.parse_args()

    # ---------------------------------------------------------
    # 1. Capture
    # ---------------------------------------------------------

    if not args.transcribe_only:
        capture_status = capture_audio()

        if capture_status != 0:
            print(
                "Capture failed. Pipeline stopped.",
                file=sys.stderr,
            )
            return capture_status

    # ---------------------------------------------------------
    # 2. Speech-to-text
    # ---------------------------------------------------------

    transcript = transcribe_audio(args.model)

    if not transcript:
        print(
            "\nNo transcript available. Pipeline stopped."
        )
        return 1

    print(f"\nTranscript: {transcript}")

    # ---------------------------------------------------------
    # 3. AI understanding
    # ---------------------------------------------------------

    intent = ask_ai(transcript)

    if intent is None:
        print(
            "\nAI understanding failed. Pipeline stopped."
        )
        return 1

    # ---------------------------------------------------------
    # 4. Execute action
    # ---------------------------------------------------------

    return execute_intent(intent)


if __name__ == "__main__":
    raise SystemExit(main())