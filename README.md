# 🤖 DeskBot

An intelligent, expressive AI desktop companion robot powered by ESP32-S3 hardware and an advanced local Windows companion assistant engine.

---

## 🌟 Highlights & Architecture

DeskBot pairs an expressive physical robot face with a modular, low-latency AI desktop voice system:

- **Expressive OLED Face System**:
  - Live hardware state synchronization with custom eye geometry and status labels for every phase:
    - `IDLE`: Calm blinking and idling eyes.
    - `LISTENING`: Wide, alert eyes attentively awaiting speech.
    - `TRANSCRIBING`: Focused scanning pupils processing audio.
    - `THINKING`: Raised brow analyzing intent with AI brain.
    - `EXECUTING`: Narrowed, determined focus performing PC action.
    - `ERROR`: Confused tilted brows indicating safe fallback.
  - High-speed 400kHz Fast I2C and non-blocking streaming serial protocol.

- **Continuous Audio & Speech Pipeline**:
  - Real-time continuous 16kHz 16-bit mono audio streaming via I2S INMP441 mic at 921,600 baud.
  - Rolling PCM ring buffer ensuring zero audio dropouts or truncated speech beginnings.
  - Local neural wake-word detection with `openWakeWord` ("Hey Jarvis").
  - Adaptive WebRTC Voice Activity Detection (VAD) with pre-roll buffering.
  - Accelerated local Speech-to-Text via `faster-whisper`.

- **Nemotron AI Brain & Multi-Turn Conversation**:
  - Structured JSON intent reasoning using NVIDIA Nemotron.
  - **Multi-turn conversation context memory** with automatic TTL pruning and prompt formatting.
  - **Active Conversation Mode**: 7-second active listening window after every completed command allowing natural follow-ups without repeating the wake word.
  - Fast offline regex heuristics for instant sub-millisecond execution.

- **Extensible Action Registry & Safe PC Control**:
  - Deterministic Windows control with strict whitelist verification (**no arbitrary shell execution**).
  - Media & volume controls (`volume_up`, `volume_down`, `mute`, `unmute`).
  - Screen capture (`screenshot` saved to `Pictures/Screenshots`).
  - Safe application termination (`close_app` with system process protection).
  - Safe folder navigation (`open_folder` for Downloads, Documents, Projects, etc.).
  - VS Code workspace launcher (`open_project_in_vscode`).
  - Modular web search provider (`companion/tools/web_search.py`).
  - Real-time system & environmental info (`current_time`, `current_date`, `system_info`, `weather`).
  - Smart app launcher & media player (Spotify, YouTube, Windows apps).

---

## 🛠 Hardware Setup

- **ESP32-S3 DevKit** (or ESP32 dual-core)
- **INMP441 I2S Digital Microphone**:
  - `SCK` / `BCLK` &rarr; GPIO 14
  - `WS` / `LRC` &rarr; GPIO 15
  - `SD` / `DIN` &rarr; GPIO 32
  - `L/R` &rarr; GND (Left channel)
  - `VDD` &rarr; 3.3V
- **0.96" SSD1306 OLED Display (I2C)**:
  - `SDA` &rarr; GPIO 21
  - `SCL` &rarr; GPIO 22
  - `VCC` &rarr; 3.3V / 5V
  - `GND` &rarr; GND

---

## 🖥 Software Stack

### Firmware (`/src`)
- C++ / PlatformIO
- Adafruit SSD1306 & GFX Graphics Engine
- I2S DMA High-throughput streaming driver
- Non-blocking serial command listener

### Windows Companion (`/companion`)
- Python 3.10+
- `openwakeword`: Local neural wake word
- `faster-whisper`: GPU/CPU accelerated STT
- `webrtcvad`: Voice activity detection
- `openai`: NVIDIA Nemotron API client
- `psutil`, `Pillow`, `requests`: System metrics, screenshot capture, web info
- Centralized configuration: `companion/config.py`

---

## 🚀 Running DeskBot

### 1. Run Companion Assistant
```bash
python companion/continuous_assistant.py
```

Optional CLI flags:
- `--port COM4`: Serial port of ESP32 (default: `COM4`).
- `--baud 921600`: Baud rate (default: `921600`).
- `--conversation-timeout 7.0`: Follow-up active listening window in seconds.
- `--stt-model base`: Faster-Whisper model size (`tiny`, `base`, `small`).
- `--debug`: Enable verbose diagnostic logging.

### 2. Run Test Suite
```bash
python -m unittest discover companion/tests
```
All 64 unit and integration tests run in under 1 second.

---

## 👨‍💻 Author

**Ninad Vyas**  
Artificial Intelligence & Data Science Engineering  
Savitribai Phule Pune University