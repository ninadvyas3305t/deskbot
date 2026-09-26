"""DeskBot Central Configuration Settings."""

from __future__ import annotations

import os
from pathlib import Path

# --- Paths ---
COMPANION_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = COMPANION_DIR.parent

# --- Environment Variable Auto-Loader ---
def _load_env() -> None:
    """Load key-value pairs from .env into os.environ if not already present."""
    candidates = [
        PROJECT_ROOT / ".env",
        COMPANION_DIR / ".env",
    ]
    for env_path in candidates:
        if env_path.is_file():
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip().strip("'\"")
                        if key and key not in os.environ:
                            os.environ[key] = val
            except Exception:
                pass

_load_env()

WORKSPACE_ROOT = Path(os.getenv("DESKBOT_WORKSPACE_ROOT", str(PROJECT_ROOT)))
COMMAND_AUDIO_PATH = COMPANION_DIR / "last_command.wav"
SCRATCH_DIR = COMPANION_DIR / "scratch"


# --- Hardware Serial (ESP32) ---
DEFAULT_PORT = os.getenv("DESKBOT_PORT", "COM4")
DEFAULT_BAUD = int(os.getenv("DESKBOT_BAUD", "921600"))

# --- Audio Format ---
SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2
CHANNELS = 1

# --- Wake Word Detection (openWakeWord) ---
DEFAULT_WAKE_MODEL = os.getenv("DESKBOT_WAKE_MODEL", "hey_jarvis")
DEFAULT_WAKE_THRESHOLD = float(os.getenv("DESKBOT_WAKE_THRESHOLD", "0.50"))
DEFAULT_MIC_GAIN = float(os.getenv("DESKBOT_MIC_GAIN", "1.2"))

# --- Speech-to-Text (Faster-Whisper) ---
DEFAULT_STT_MODEL = os.getenv("DESKBOT_STT_MODEL", "base")

# --- Conversation & Multi-Turn Mode ---
# Number of seconds assistant stays in active listening mode for follow-up speech
CONVERSATION_TIMEOUT_SECONDS = float(os.getenv("DESKBOT_CONVERSATION_TIMEOUT", "7.0"))
MAX_CONTEXT_MESSAGES = int(os.getenv("DESKBOT_MAX_CONTEXT_MESSAGES", "8"))
CONTEXT_TTL_SECONDS = float(os.getenv("DESKBOT_CONTEXT_TTL", "90.0"))

# --- VAD & Speech Detection Parameters ---
VAD_MODE = int(os.getenv("DESKBOT_VAD_MODE", "2"))
FRAME_DURATION_MS = 30
PRE_ROLL_SECONDS = 0.35
SILENCE_DURATION_SECONDS = 0.55
INITIAL_SPEECH_TIMEOUT = 4.5
MAX_COMMAND_SECONDS = 12.0
TRANSITION_WINDOW_SECONDS = 0.25

# --- Debugging ---
DEBUG = os.getenv("DESKBOT_DEBUG", "0").lower() in ("1", "true", "yes")

# --- Text-to-Speech (TTS) Settings ---
TTS_ENABLED = os.getenv("DESKBOT_TTS_ENABLED", "1").lower() in ("1", "true", "yes")
TTS_ENGINE = os.getenv("DESKBOT_TTS_ENGINE", "sapi5")
TTS_VOICE = os.getenv("DESKBOT_TTS_VOICE", None)
TTS_RATE = int(os.getenv("DESKBOT_TTS_RATE", "1"))
TTS_VOLUME = int(os.getenv("DESKBOT_TTS_VOLUME", "100"))

