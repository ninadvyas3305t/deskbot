# 🤖 DeskBot — Cross-Platform Plug-and-Play AI Companion Robot

[![Tests](https://img.shields.io/badge/tests-197%20passed-brightgreen.svg)]()
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11%20%7C%20macOS%20(Apple%20Silicon%20%26%20Intel)-blue.svg)]()
[![Hardware](https://img.shields.io/badge/hardware-ESP32--S3%20%7C%20I2S%20Mic%20%7C%20OLED%20Face-orange.svg)]()
[![AI Engine](https://img.shields.io/badge/AI%20Brain-NVIDIA%20Nemotron%20%2B%20Llama%203.2%20Vision-purple.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**DeskBot** is an expressive, physical AI desktop companion robot paired with a production-grade, cross-platform desktop application. Combining physical hardware (ESP32-S3, high-fidelity I2S microphone, animated OLED robotic face, capacitive touch sensor) with a modular AI engine (local wake-word detection, fast-path deterministic heuristics, deep cloud reasoning, and visual screen intelligence), DeskBot transforms how you interact with your computer.

---

## 📥 Downloads & Distributables

DeskBot is packaged as a standalone desktop application—**no Python installation, terminal commands, or manual dependency setup required for end users.**

| Operating System | Architecture | Package Format | Download |
| :--- | :--- | :--- | :--- |
| **Windows 11 / 10** | 64-bit (x86_64) | Setup Installer (`.exe`) | [**DeskBotSetup-Windows-x64.exe**](https://github.com/ninadvyas/deskbot/releases/latest) |
| **macOS Apple Silicon** | M1 / M2 / M3 / M4 (arm64) | Drag-and-Drop Disk Image (`.dmg`) | [**DeskBot-macOS-arm64.dmg**](https://github.com/ninadvyas/deskbot/releases/latest) |
| **macOS Intel** | 64-bit (x86_64) | Drag-and-Drop Disk Image (`.dmg`) | [**DeskBot-macOS-x64.dmg**](https://github.com/ninadvyas/deskbot/releases/latest) |

```text
Download DeskBot → Run Installer / Open DMG → One-Time Setup Wizard → Plug in ESP32 via USB → "DeskBot ready."
```

---

## 🌟 Key Capabilities

### 1. Physical Companion Hardware
- **Expressive OLED Face**: Synchronized real-time facial expressions on a 0.96" SSD1306 OLED display:
  - `IDLE`: Relaxed blinking and gaze tracking.
  - `LISTENING`: Alert, wide eyes actively receiving speech.
  - `TRANSCRIBING`: Scanning pupils processing acoustic data.
  - `THINKING`: Raised brow analyzing intent with AI brain.
  - `SPEAKING`: Expressive communicative pupils.
  - `EXECUTING`: Determined focus executing PC action.
  - `ERROR`: Confused brow with automatic recovery.
- **Hardware Push-To-Talk**: Capacitive TTP223 touch sensor on GPIO 4 for instant activation without speaking the wake word.
- **Continuous 16kHz Audio Stream**: Direct DMA-buffered I2S streaming over USB serial at 921,600 baud.
- **Seamless USB Hotplug**: Unplugging the device never crashes the software; DeskBot smoothly enters `WAITING_FOR_DEVICE` and automatically reconnects upon reinsertion.

### 2. Fast Acoustic & Speech Pipeline
- **Rolling PCM Ring Buffer**: Continuous rolling audio buffer captures the first syllable of your command without truncation.
- **Neural Wake-Word**: Lightweight local `openWakeWord` ("Hey Jarvis") with acoustic refractory cooldown to eliminate false self-triggers.
- **WebRTC VAD**: Dynamic voice activity detection with pre-roll buffering and adaptive silence thresholding.
- **Local Whisper STT**: High-accuracy Speech-to-Text powered by `faster-whisper` (runs locally on CPU/GPU).
- **Multi-Turn Follow-Ups**: 7-second active listening window after every task ("*Is that all?*") enabling natural back-to-back commands without repeating "Hey Jarvis".

### 3. Visual Screen Intelligence & Code Understanding
- **On-Demand Vision Inspection**: Powered by NVIDIA NIM `meta/llama-3.2-11b-vision-instruct`.
- DeskBot captures your screen in real time and understands visible code and user interfaces without needing access to underlying source files.
- Works across **VS Code, JetBrains IDEs, terminals, browsers, PDFs, documentation, YouTube tutorials, and online editors**.
- Dynamic image scaling optimizes capture dimensions to <4 tiles, achieving **~3 second end-to-end screen analysis**.

### 4. Dual Reasoning Brain & Developer Mode
- **Zero-Latency Fast Path**: Sub-millisecond offline regex router for common desktop tasks (volume, media, app launching, time, screenshots).
- **Cloud Reasoning Brain**: NVIDIA Nemotron / Llama-3.1 70B with structured JSON schema output and conversation context memory.
- **Developer Mode**: Workspace project inspection, semantic file search, recursive grep, targeted file reading, safe editing, and fuzzy deletion confirmation.

### 5. Cross-Platform Desktop Integration
- **System Tray & Menu Bar**: Native status icon with dynamic mood indicator, Settings dialog, log viewer, autostart toggle, and manual reconnect.
- **OS Native Credential Vault**: Stores your NVIDIA API key securely inside macOS Keychain or Windows Credential Manager via `keyring`. Zero plaintext keys on disk.
- **Automatic Autostart**: Seamless "Start with System" support via macOS LaunchAgent and Windows Registry Run key.
- **Privacy & Permissions**: Proactive microphone and screen recording permission checks with actionable guidance.

---

## 🔌 Hardware Setup & Wiring

### Components
1. **ESP32-S3 DevKit** (or dual-core ESP32)
2. **INMP441 I2S Digital Omnidirectional Microphone**
3. **0.96" SSD1306 I2C OLED Display (128x64)**
4. **TTP223 Capacitive Touch Sensor** (Push-to-Talk)

### Pinout Diagram

| Sensor / Module | Pin | ESP32-S3 GPIO | Description |
| :--- | :--- | :--- | :--- |
| **INMP441 Mic** | `SCK` / `BCLK` | `GPIO 14` | I2S Bit Clock |
| | `WS` / `LRC` | `GPIO 15` | I2S Word Select / Left-Right Clock |
| | `SD` / `DIN` | `GPIO 32` | I2S Serial Data Out |
| | `L/R` | `GND` | Left Channel Select |
| | `VDD` | `3.3V` | Power Supply |
| | `GND` | `GND` | Common Ground |
| **SSD1306 OLED** | `SDA` | `GPIO 21` | I2C Data Line (400kHz Fast Mode) |
| | `SCL` | `GPIO 22` | I2C Clock Line |
| | `VCC` | `3.3V` / `5V` | Power Supply |
| | `GND` | `GND` | Common Ground |
| **TTP223 Touch** | `SIG` / `IO` | `GPIO 4` | Digital Touch Trigger (Active High) |
| | `VCC` | `3.3V` | Power Supply |
| | `GND` | `GND` | Common Ground |

---

## 🚀 Demonstration Guide (For Recruiter & Evaluation Demos)

To demonstrate DeskBot live to recruiters, evaluators, or team members, follow this recommended walkthrough:

### Scenario 1: Wake Word, System Control & Conversational Follow-Up
1. Say: `"Hey Jarvis"`
2. Robot eyes widen to alert `LISTENING` state.
3. Say: `"Open YouTube and play Starboy by The Weeknd"`
4. Robot enters `TRANSCRIBING` &rarr; `EXECUTING`, opens the browser directly to the song, and asks:
   > *"Is that all?"*
5. Respond naturally without the wake word:
   > *"No, turn the volume up and mute Discord"*
6. DeskBot adjusts the system volume, manages the app, and confirms:
   > *"Volume increased. Discord muted. Is that all?"*
7. Say: *"Yes, thank you"* &rarr; DeskBot responds *"Alright"* and returns to `IDLE` with gentle blinking.

### Scenario 2: Visual Screen Intelligence & Code Understanding
1. Open any piece of code on your screen (in VS Code, a browser tab, or even a paused YouTube tutorial video).
2. Say: `"Hey Jarvis, what am I looking at on my screen?"` or `"Hey Jarvis, explain the bug in this function"`
3. DeskBot captures the active display, scales the image into optimal vision tiles, queries Llama 3.2 Vision, and speaks an articulate, context-aware explanation of the code displayed before you.

### Scenario 3: Hardware Push-to-Talk
1. In a noisy room, simply tap the physical capacitive touch sensor on DeskBot.
2. The robot immediately jumps to `LISTENING` mode without needing acoustic wake detection.

### Scenario 4: Hardware Hotplug Resilience
1. While DeskBot is running in the system tray, unplug the USB cable from your computer.
2. The menu bar icon changes to gray standby (`WAITING_FOR_DEVICE`), and the application continues running without crashing.
3. Plug the USB cable back in.
4. DeskBot detects the serial port, executes the handshake probe, announces *"DeskBot reconnected"*, and returns to `READY`.

---

## 💻 Developer & Source Setup

If you wish to modify the code or contribute to DeskBot:

### 1. Clone & Set Up Environment
```bash
git clone https://github.com/ninadvyas/deskbot.git
cd deskbot

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate    # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r companion/requirements.txt
pip install pyinstaller pytest
```

### 2. Run Desktop Application
```bash
# Launch GUI Desktop App with System Tray / Menu Bar
python companion/app.py

# Or run in console-only CLI mode
python companion/app.py --cli --debug
```

### 3. Flash ESP32 Firmware
DeskBot firmware is built using PlatformIO:
```bash
pio run -t upload
```

### 4. Run Automated Tests
DeskBot includes a comprehensive test suite (197 unit and integration tests covering the platform layer, device discovery, speech detectors, fast-path intent matching, vision pipeline, and file safety tools):
```bash
pytest companion/tests/
```

### 5. Build Standalone Distributables Locally
- **macOS (`.app` and `.dmg`)**:
  ```bash
  ./scripts/build_macos.sh
  ```
- **Windows (`.exe` installer)**:
  ```powershell
  pyinstaller --clean -y build/deskbot.spec
  & "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer/deskbot_setup.iss
  ```

---

## 🔒 Security & Privacy Architecture

- **No Plaintext Secrets**: API keys are saved exclusively in your operating system's native hardware-backed vault (macOS Keychain or Windows Credential Manager).
- **Redacted Logging**: All logs written to `logs/deskbot.log` pass through a regex redaction filter, preventing sensitive API tokens from leaking into logs or crash dumps.
- **Protected File Operations**: File modification and deletion tools in Developer Mode strictly validate target paths, forbid system directory modifications, and mandate explicit voice confirmation before any destructive action.
- **Zero Background Cloud Audio**: Audio is streamed strictly across local USB serial to local memory; wake-word detection and VAD run 100% locally on your machine.

---

## 📄 License

DeskBot is licensed under the [MIT License](LICENSE).