"""DeskBot Desktop Application Entrypoint.

Unified entry point for DeskBot cross-platform distributable desktop application.
Integrates:
- Structured rotating logging (logs/deskbot.log) with secret redaction
- One-time setup wizard on first launch
- Hardware auto-discovery and hotplug auto-reconnect
- OS native system tray / menu bar with status icon and settings dialog
- Continuous voice assistant loop with touch-sensor and Hey Jarvis wake word
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
import time
from pathlib import Path

# Ensure companion package directory is at the head of sys.path
COMPANION_DIR = Path(__file__).resolve().parent
if str(COMPANION_DIR) not in sys.path:
    sys.path.insert(0, str(COMPANION_DIR))

import config
from assistant.lifecycle import AppLifecycleState, get_lifecycle_manager
from continuous_assistant import run_assistant
try:
    from platform_layer.config_manager import get_config_manager
    from platform_layer.credentials import get_credential_store
    from platform_layer.logger import setup_logging
    from platform_layer.permissions import (
        check_microphone_permission,
        check_screen_recording_permission,
    )
except (ImportError, ModuleNotFoundError):
    from companion.platform_layer.config_manager import get_config_manager
    from companion.platform_layer.credentials import get_credential_store
    from companion.platform_layer.logger import setup_logging
    from companion.platform_layer.permissions import (
        check_microphone_permission,
        check_screen_recording_permission,
    )
from ui.setup_wizard import SetupWizard, maybe_run_first_time_setup
from ui.tray import DeskBotTray

logger = logging.getLogger("deskbot")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="DeskBot — Cross-Platform AI Assistant Companion Application",
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Run in headless/terminal-only mode without System Tray icon.",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Force open the initial first-time setup wizard.",
    )
    parser.add_argument(
        "--port",
        default=config.DEFAULT_PORT,
        help=f"Serial port (default: {config.DEFAULT_PORT})",
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=config.DEFAULT_BAUD,
        help=f"Serial baud rate (default: {config.DEFAULT_BAUD})",
    )
    parser.add_argument(
        "--wake-model",
        default=config.DEFAULT_WAKE_MODEL,
        help=f"Wake model name (default: {config.DEFAULT_WAKE_MODEL})",
    )
    parser.add_argument(
        "--wake-threshold",
        type=float,
        default=config.DEFAULT_WAKE_THRESHOLD,
        help=f"Wake sensitivity threshold (default: {config.DEFAULT_WAKE_THRESHOLD})",
    )
    parser.add_argument(
        "--stt-model",
        default=config.DEFAULT_STT_MODEL,
        help=f"Faster-Whisper model name (default: {config.DEFAULT_STT_MODEL})",
    )
    parser.add_argument(
        "--mic-gain",
        type=float,
        default=config.DEFAULT_MIC_GAIN,
        help=f"Microphone gain multiplier (default: {config.DEFAULT_MIC_GAIN})",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Exit after handling a single voice interaction (useful for automated testing).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose debug logging.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # 1. Setup rotating logging with sensitive data redaction
    setup_logging(debug=args.debug)
    lifecycle_mgr = get_lifecycle_manager()
    lifecycle_mgr.transition_to(AppLifecycleState.STARTING, "DeskBot starting...")

    config_mgr = get_config_manager()
    cred_store = get_credential_store()

    # 2. First-run onboarding check
    if args.setup:
        wizard = SetupWizard()
        wizard.root.mainloop()
    elif not args.cli:
        # Prompt GUI wizard if credentials/setup not completed
        if not cred_store.has_api_key() or not config_mgr.get("first_run_completed", False):
            proceed = maybe_run_first_time_setup()
            if not proceed:
                logger.info("[APP] Initial setup was skipped or closed. Exiting.")
                return 0

    # 3. Synchronize credentials from OS Keychain / Vault to os.environ
    stored_key = cred_store.get_api_key()
    if stored_key and "NVIDIA_API_KEY" not in os.environ:
        os.environ["NVIDIA_API_KEY"] = stored_key

    # 4. Check hardware permissions
    check_microphone_permission()
    check_screen_recording_permission()

    # 5. Apply saved configuration preferences
    dev_mode = bool(config_mgr.get("developer_mode", False))
    try:
        from tools.developer_tools import set_developer_mode
        set_developer_mode(dev_mode)
    except Exception:
        pass

    # Read config overrides
    port = args.port or config_mgr.get("serial_port", config.DEFAULT_PORT)
    baud = args.baud or int(config_mgr.get("baud_rate", config.DEFAULT_BAUD))
    wake_model = args.wake_model or config_mgr.get("wake_model", config.DEFAULT_WAKE_MODEL)
    wake_threshold = args.wake_threshold or float(config_mgr.get("wake_threshold", config.DEFAULT_WAKE_THRESHOLD))
    stt_model = args.stt_model or config_mgr.get("stt_model", config.DEFAULT_STT_MODEL)

    lifecycle_mgr.transition_to(AppLifecycleState.INITIALIZING, "Loading AI models...")

    stop_event = threading.Event()
    tray: DeskBotTray | None = None

    def request_shutdown() -> None:
        logger.info("[APP] Shutdown signal received.")
        stop_event.set()
        if tray:
            tray.stop()

    # 6. Initialize System Tray / Menu Bar unless running in pure CLI mode
    if not args.cli:
        try:
            tray = DeskBotTray(on_quit_callback=request_shutdown)
        except Exception as tray_err:
            logger.warning("[APP] Could not initialize system tray: %s.", tray_err)
            tray = None

    # Register OS signal handlers for graceful termination
    def sig_handler(sig, frame):
        request_shutdown()

    try:
        signal.signal(signal.SIGINT, sig_handler)
        signal.signal(signal.SIGTERM, sig_handler)
    except Exception:
        pass

    # 7. Run continuous assistant loop
    exit_code = 0
    try:
        if args.cli or args.once or tray is None:
            exit_code = run_assistant(
                port=port,
                baud=baud,
                wake_model=wake_model,
                wake_threshold=wake_threshold,
                stt_model=stt_model,
                mic_gain=args.mic_gain,
                run_once=args.once,
                debug=args.debug,
                wait_for_device=True,
                stop_event=stop_event,
            )
        else:
            assistant_thread = threading.Thread(
                target=run_assistant,
                kwargs=dict(
                    port=port,
                    baud=baud,
                    wake_model=wake_model,
                    wake_threshold=wake_threshold,
                    stt_model=stt_model,
                    mic_gain=args.mic_gain,
                    run_once=args.once,
                    debug=args.debug,
                    wait_for_device=True,
                    stop_event=stop_event,
                ),
                name="DeskBotAssistantWorker",
                daemon=True,
            )
            assistant_thread.start()

            # Run system tray event loop on the main thread (required by macOS AppKit)
            tray.run()
    except KeyboardInterrupt:
        logger.info("[APP] Keyboard interrupt received.")
    except Exception as err:
        logger.exception("[APP] Fatal error in assistant loop: %s", err)
        exit_code = 1
    finally:
        request_shutdown()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
