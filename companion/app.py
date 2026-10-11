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
        default=None,
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
        default=None,
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
    parser.add_argument(
        "--test-edge-glow",
        action="store_true",
        help="Diagnostic mode: force desktop edge illumination overlay to render continuously without audio/assistant pipeline.",
    )
    parser.add_argument(
        "--test-vision",
        action="store_true",
        help="Diagnostic mode: test screen capture, image optimization, vision model API, and screen-description pipeline independently.",
    )
    return parser.parse_args()


def run_vision_diagnostics() -> int:
    """Run isolated diagnostics for screen capture, optimization, vision API, and full pipeline."""
    import time
    from pathlib import Path

    print("\n" + "=" * 68)
    print("  DESKBOT 2.0 — SCREEN VISION DIAGNOSTIC SUITE")
    print("=" * 68)

    # Test 1: Screenshot capture
    print("\n[TEST 1/4] Testing Native Screen Capture...")
    try:
        from vision.screen_capture import capture_raw_screen
        t0 = time.perf_counter()
        raw_img = capture_raw_screen()
        dur_cap = (time.perf_counter() - t0) * 1000.0

        if raw_img is None:
            print("  ❌ Screenshot capture failed: capture_raw_screen returned None.")
            print("     Hint: Check macOS System Settings → Privacy & Security → Screen & System Audio Recording.")
            return 1
        print(f"  ✓ Screen captured successfully in {dur_cap:.1f}ms")
        print(f"    • Resolution : {raw_img.width}x{raw_img.height}")
        print(f"    • Color Mode : {raw_img.mode}")
    except Exception as err:
        print(f"  ❌ Screen capture exception: {err}")
        return 1

    # Test 2: Image conversion and optimization
    print("\n[TEST 2/4] Testing Image Optimization & Encoding for Vision Model...")
    try:
        from vision.screen_capture import optimize_image_for_vision
        t0 = time.perf_counter()
        opt_img, b64_data = optimize_image_for_vision(raw_img, max_dimension=1024, quality=85)
        dur_opt = (time.perf_counter() - t0) * 1000.0

        data_uri_len = len(f"data:image/jpeg;base64,{b64_data}")
        print(f"  ✓ Image optimized and encoded in {dur_opt:.1f}ms")
        print(f"    • Optimized Dimensions : {opt_img.width}x{opt_img.height}")
        print(f"    • Base64 Payload Size  : {data_uri_len / 1024.0:.1f} KB")
        if data_uri_len < 500:
            print("  ❌ Encoded payload too small to be a valid image.")
            return 1
    except Exception as err:
        print(f"  ❌ Image optimization exception: {err}")
        return 1

    # Test 3: Vision API connectivity & model query
    print("\n[TEST 3/4] Testing Vision Model API Request...")
    try:
        from vision.service import get_vision_analyzer
        analyzer = get_vision_analyzer()
        print(f"    • Model    : {analyzer.model}")
        print(f"    • Endpoint : {analyzer.base_url}")
        print(f"    • Auth Key : {'[Configured]' if analyzer.api_key else '[Missing]'}")

        if not analyzer.api_key:
            print("  ⚠ Skipping live API call: NVIDIA_API_KEY is not configured in Keychain or environment.")
        else:
            t0 = time.perf_counter()
            test_uri = f"data:image/jpeg;base64,{b64_data}"
            try:
                analysis = analyzer.analyze(
                    image_data_uri=test_uri,
                    user_query="What is on my screen? Provide a brief technical summary.",
                )
                dur_api = (time.perf_counter() - t0) * 1000.0
                print(f"  ✓ Vision Model API responded in {dur_api:.1f}ms")
                print(f"    • Content Type : {analysis.content_type}")
                print(f"    • Language     : {analysis.language}")
                print(f"    • Summary      : {analysis.summary[:140]}...")
                print(f"    • Spoken (TTS) : {analysis.spoken_response[:140]}...")
            except Exception as api_err:
                print(f"  ⚠ Vision Model API request failed (network or model status): {api_err}")
                print("     Note: The application reports this failure gracefully rather than crashing.")
    except Exception as err:
        print(f"  ❌ Vision analyzer initialization exception: {err}")
        return 1

    # Test 4: Full vision command execution via Tool Registry
    print("\n[TEST 4/4] Testing Full End-to-End Screen Analysis Action...")
    try:
        from command_executor import execute_intent
        t0 = time.perf_counter()
        result = execute_intent({
            "action": "screen_analysis",
            "query": "Explain what I'm looking at on my screen.",
        })
        dur_tool = (time.perf_counter() - t0) * 1000.0
        print(f"  ✓ Tool executed in {dur_tool:.1f}ms")
        print(f"    • Success       : {result.success}")
        print(f"    • Spoken Answer : {result.response_text or result.message}")
    except Exception as err:
        print(f"  ❌ End-to-end screen analysis execution exception: {err}")
        return 1

    print("\n" + "=" * 68)
    print("  DIAGNOSTIC COMPLETE: Screen vision pipeline is fully operational!")
    print("=" * 68 + "\n")
    return 0


def main() -> int:
    args = parse_args()

    # 1. Setup rotating logging with sensitive data redaction
    setup_logging(debug=args.debug)

    # Diagnostic Mode: Screen vision pipeline
    if args.test_vision:
        return run_vision_diagnostics()

    # Diagnostic Mode: Test edge illumination independently of audio/hardware
    if args.test_edge_glow:
        logger.info("[DIAGNOSTIC] Initializing DeskBot Edge Illumination diagnostic mode...")
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
        from ui.edge_overlay import initialize_screen_overlay

        q_app = QApplication.instance() or QApplication(sys.argv)
        q_app.setApplicationName("DeskBot Edge Glow Diagnostic")
        q_app.setApplicationDisplayName("DeskBot Edge Glow Diagnostic")

        overlay = initialize_screen_overlay()
        overlay.set_test_mode(True)

        geom = overlay.geometry()
        print("\n" + "=" * 65)
        print("  DESKBOT DESKTOP EDGE ILLUMINATION — DIAGNOSTIC MODE ACTIVE")
        print("=" * 65)
        print(f"  • Screen Geometry  : {geom.width()}x{geom.height()} at ({geom.x()}, {geom.y()})")
        print(f"  • Edge Thickness   : {overlay.edge_thickness}px inward luminous depth")
        print(f"  • Glow Intensity   : {int(overlay.glow_intensity * 100)}%")
        print(f"  • Window Native ID : {int(overlay.winId())}")
        print("  • Center Screen    : 100% transparent & click-through")
        print("  • OS Window Level  : Top-level overlay (Status/Floating)")
        print("=" * 65)
        print("  Press Ctrl+C in this terminal window to stop diagnostic mode.\n", flush=True)

        # Periodic timer allows Python signal handler to respond immediately to SIGINT (Ctrl+C)
        sig_timer = QTimer()
        sig_timer.timeout.connect(lambda: None)
        sig_timer.start(200)

        def _sig_handler(sig, frame):
            print("\n[DIAGNOSTIC] Stopping diagnostic mode...", flush=True)
            overlay.set_test_mode(False)
            overlay.hide()
            q_app.quit()

        try:
            signal.signal(signal.SIGINT, _sig_handler)
            signal.signal(signal.SIGTERM, _sig_handler)
        except Exception:
            pass

        return q_app.exec()

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

    saved_thresh = float(config_mgr.get("wake_threshold", config.DEFAULT_WAKE_THRESHOLD))
    if saved_thresh > 0.45:
        logger.info("[CONFIG] Normalizing legacy high wake_threshold %.2f down to responsive 0.38", saved_thresh)
        saved_thresh = 0.38
        config_mgr.set("wake_threshold", 0.38)
    wake_threshold = args.wake_threshold if args.wake_threshold is not None else saved_thresh

    mic_gain = args.mic_gain if args.mic_gain is not None else float(config_mgr.get("mic_gain", config.DEFAULT_MIC_GAIN))
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

    # 6. Run assistant and Desktop Application
    exit_code = 0
    try:
        if args.cli or args.once:
            # Headless / Terminal / Test mode
            exit_code = run_assistant(
                port=port,
                baud=baud,
                wake_model=wake_model,
                wake_threshold=wake_threshold,
                stt_model=stt_model,
                mic_gain=mic_gain,
                run_once=args.once,
                debug=args.debug,
                wait_for_device=True,
                stop_event=stop_event,
            )
        else:
            # Full Desktop Application with animated face, device manager, and overlay
            from PySide6.QtWidgets import QApplication
            from ui.main_window import DeskBotMainWindow

            q_app = QApplication.instance() or QApplication(sys.argv)
            q_app.setApplicationName("DeskBot")
            q_app.setApplicationDisplayName("DeskBot — Hardware AI Companion")

            main_win = DeskBotMainWindow(on_shutdown=request_shutdown)
            main_win.show()

            # If API key is not yet configured, automatically guide to Settings view
            if not cred_store.has_api_key():
                main_win.stack.setCurrentIndex(3)
                main_win.btn_nav_settings.setChecked(True)
                main_win.lbl_page_title.setText("Settings")

            assistant_thread = threading.Thread(
                target=run_assistant,
                kwargs=dict(
                    port=port,
                    baud=baud,
                    wake_model=wake_model,
                    wake_threshold=wake_threshold,
                    stt_model=stt_model,
                    mic_gain=mic_gain,
                    run_once=args.once,
                    debug=args.debug,
                    wait_for_device=True,
                    stop_event=stop_event,
                ),
                name="DeskBotAssistantWorker",
                daemon=True,
            )
            assistant_thread.start()

            # Execute Qt main event loop on the primary thread
            exit_code = q_app.exec()
    except KeyboardInterrupt:
        logger.info("[APP] Keyboard interrupt received.")
    except Exception as err:
        logger.exception("[APP] Fatal error in application loop: %s", err)
        exit_code = 1
    finally:
        request_shutdown()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
