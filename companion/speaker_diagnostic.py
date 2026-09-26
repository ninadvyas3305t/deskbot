"""DeskBot Isolated Speaker & Amplifier Diagnostic Runner.

Interactive test runner for evaluating ESP32-S3 -> I2S -> MAX98357A -> Speaker.
Zero assumptions on speaker impedance (supports 4-Ohm and 8-Ohm).
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("pyserial is required. Install via: pip install pyserial")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BUILD_BIN = PROJECT_ROOT / ".pio" / "build" / "speaker-diagnostic" / "firmware.factory.bin"

DEFAULT_PORT = os.getenv("DESKBOT_PORT", "COM4")
DEFAULT_BAUD = 921600


def find_esp32_port() -> Optional[str]:
    """Scan available serial ports for ESP32 / CH343."""
    ports = serial.tools.list_ports.comports()
    for p in ports:
        if "CH34" in p.description or "USB Serial" in p.description or "ESP" in p.description:
            return p.device
    for p in ports:
        if p.device != "COM1":
            return p.device
    return None


def flash_diagnostic_firmware(port: str) -> bool:
    """Flash the pre-compiled speaker-diagnostic firmware to ESP32."""
    if not BUILD_BIN.is_file():
        print(f"[ERROR] Firmware binary not found at: {BUILD_BIN}")
        print("Please build it first with: pio run -e speaker-diagnostic")
        return False

    print(f"\n[FLASH] Flashing speaker diagnostic firmware to {port} @ {DEFAULT_BAUD} baud...")
    esptool_py = Path.home() / ".platformio" / "packages" / "tool-esptoolpy" / "esptool.py"
    python_exe = Path.home() / ".platformio" / "penv" / "Scripts" / "python.exe"

    if not esptool_py.is_file() or not python_exe.is_file():
        print(f"[ERROR] PlatformIO esptool not found at {esptool_py}")
        return False

    args = [
        str(python_exe),
        str(esptool_py),
        "--chip", "esp32s3",
        "--port", port,
        "--baud", str(DEFAULT_BAUD),
        "write-flash",
        "0x0000",
        str(BUILD_BIN),
    ]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    import subprocess
    res = subprocess.run(args, env=env)
    if res.returncode == 0:
        print("[FLASH] Successfully flashed speaker diagnostic firmware!\n")
        time.sleep(1.0)
        return True
    else:
        print(f"[ERROR] Flashing failed with exit code: {res.returncode}")
        return False


class DiagnosticRunner:
    """Manages bidirectional serial communication and interactive diagnostic menu."""

    def __init__(self, port: str, baud: int = DEFAULT_BAUD):
        self.port = port
        self.baud = baud
        self.ser: Optional[serial.Serial] = None
        self.running = False
        self.reader_thread: Optional[threading.Thread] = None

    def connect(self) -> bool:
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=0.1)
            time.sleep(0.5)
            self.running = True
            self.reader_thread = threading.Thread(target=self._read_serial, daemon=True)
            self.reader_thread.start()
            return True
        except Exception as err:
            print(f"[ERROR] Could not open {self.port}: {err}")
            return False

    def _read_serial(self) -> None:
        """Background thread streaming messages from ESP32."""
        while self.running and self.ser and self.ser.is_open:
            try:
                line = self.ser.readline()
                if line:
                    text = line.decode("utf-8", errors="ignore").rstrip()
                    if text:
                        print(f"  [ESP32] {text}")
            except Exception:
                break

    def send(self, char: str) -> None:
        if self.ser and self.ser.is_open:
            try:
                self.ser.write(char.encode("ascii"))
                self.ser.flush()
            except Exception as err:
                print(f"[ERROR] Failed to send: {err}")

    def close(self) -> None:
        self.running = False
        if self.ser and self.ser.is_open:
            try:
                self.send("s")  # Silence output before closing
                time.sleep(0.1)
                self.ser.close()
            except Exception:
                pass


def print_diagnostic_matrix():
    print("""
========================================================================
                 DIAGNOSTIC CONCLUSION DECISION MATRIX
========================================================================
A. Speaker/amplifier appears healthy:
   - 1 kHz tone is clean and steady across 25%, 40%, 60%.
   - Sweep plays smoothly across 300Hz-4kHz without harsh buzzing.
   - Speech multitone is recognizable without severe breakup.

B. Speaker produces distortion at higher levels:
   - Clean at 25%-40%, but crackles/buzzes at 60%-80%.
   - (Causes: acoustic enclosure vibration, speaker excursion limit,
      or amplifier power supply sagging on 5V rail).

C. Software/I2S problem likely:
   - Completely silent despite correct wiring, OR cyclic digital clicking
     independent of amplitude (BCLK/LRC clock mismatch or pin reversal).
   - Test by pressing 'p' to swap BCLK (16) and LRC (17).

D. Power/wiring problem likely:
   - Random erratic pops, loud static, or MAX98357A LED cuts out.
   - (Causes: loose GND jumper, VIN voltage drop, floating SD_MODE pin).

E. Speaker may be damaged/defective:
   - Distorted, raspy, or muffled scraping sound even at low 20-25% amplitude
     across all frequencies (damaged voice coil or torn surround).

F. Inconclusive:
   - Silent on all tests or erratic behavior. Check wiring checklist below.
========================================================================
""")


def interactive_session(runner: DiagnosticRunner):
    print("\n" + "=" * 65)
    print("         DESKBOT ISOLATED SPEAKER & AMPLIFIER DIAGNOSTIC")
    print("=" * 65)
    print("I2S Master Config: 16kHz | 16-bit Stereo (32 BCLK/frame) | Standard Philips I2S")
    print("Pin Defaults: DIN=GPIO 15 | BCLK=GPIO 16 | LRC=GPIO 17")
    print("Impedance: None assumed (supports both 4-Ohm and 8-Ohm)")
    print("-" * 65)
    print("Controls:")
    print("  [1] TEST 1: Continuous 1 kHz Sine Tone (at 25% conservative amplitude)")
    print("      [a] 25% amplitude  |  [b] 40% amplitude")
    print("      [c] 60% amplitude  |  [d] 80% amplitude")
    print("  [2] TEST 2: Frequency Sweep (300 Hz -> 500 Hz -> 1 kHz -> 2 kHz -> 4 kHz)")
    print("  [3] TEST 3: Speech-Like Harmonic Pattern (150Hz + 600Hz + 1800Hz)")
    print("  [4] TEST 4: Low vs High Amplitude Comparison (25% -> 50% -> 75% for 3s each)")
    print("  [p] SWAP CLOCK PINS (toggle BCLK=16/LRC=17 <-> BCLK=17/LRC=16)")
    print("  [+] / [-] Nudge amplitude up / down by 5%")
    print("  [s] / [0] STOP audio / Mute (output zero samples)")
    print("  [m] View Diagnostic Decision Matrix")
    print("  [q] Quit diagnostic session")
    print("-" * 65)

    # Start with silence
    runner.send("s")

    while True:
        try:
            cmd = input("\nEnter Command [1-4, a-d, p, +, -, s, m, q]: ").strip().lower()
            if not cmd:
                continue

            if cmd == "q":
                runner.send("s")
                break
            elif cmd == "m":
                print_diagnostic_matrix()
            elif cmd in ["1", "a", "b", "c", "d", "2", "3", "4", "p", "+", "-", "s", "0", "h"]:
                runner.send(cmd)
                time.sleep(0.3)
            else:
                print(f"Unknown command: '{cmd}'. Press 'h' for menu or 'q' to quit.")
        except (KeyboardInterrupt, EOFError):
            runner.send("s")
            break

    print("\nSession ended. Speaker output muted.")


def main():
    print("=== DeskBot Hardware Speaker Diagnostic ===")
    port = DEFAULT_PORT

    # Check if port is connected, or wait for user to plug in
    connected_port = find_esp32_port()
    if connected_port:
        port = connected_port
        print(f"[PORT] Detected ESP32 on {port}")
    else:
        print(f"[PORT] Waiting for ESP32 on {port}...")
        print("Please ensure your ESP32 is plugged in via USB!")
        for _ in range(10):
            p = find_esp32_port()
            if p:
                port = p
                print(f"[PORT] Found ESP32 on {port}!")
                break
            time.sleep(1.0)

    # Prompt whether to flash
    flash_choice = input(f"\nDo you want to flash the speaker diagnostic firmware to {port}? (Y/n): ").strip().lower()
    if flash_choice != "n":
        ok = flash_diagnostic_firmware(port)
        if not ok:
            print("Flashing failed. Exiting.")
            return 1

    # Connect serial runner
    runner = DiagnosticRunner(port=port)
    if not runner.connect():
        print(f"Failed to connect to {port}. Please verify connection and retry.")
        return 1

    time.sleep(1.0)
    runner.send("h")  # Trigger initial status output from ESP32
    time.sleep(0.5)

    interactive_session(runner)
    runner.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
