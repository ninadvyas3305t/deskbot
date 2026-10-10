# Implementation Plan: DeskBot 2.0 Desktop Application

## 1. Executive Summary & Product Vision
DeskBot 2.0 upgrades the DeskBot project from a background system-tray Python assistant into a commercial-grade, futuristic desktop companion application. 

The software pairs with an ESP32-S3 hardware companion (featuring an INMP441 I2S microphone, SSD1306 OLED display, and TTP223 touch sensor) and provides a unified, cross-platform interface on Windows and macOS.

Key Deliverables:
1. **Futuristic Hardware Companion UI**: A cohesive desktop application built with PySide6 featuring an obsidian/cyan design system.
2. **Central Animated Face**: Scalable, vector-rendered, fluidly animated recreation of the physical OLED face with antialiased shapes, natural blinking, eye tracking, and synchronized assistant expressions.
3. **Screen-Edge Illumination Overlay**: A transparent, click-through ambient overlay (inspired by Google Lens) that illuminates screen edges during wake, listening, thinking, and executing phases, engineered not to contaminate screenshots.
4. **Live Assistant Integration**: Thread-safe event bridge connecting the existing `AssistantStateMachine`, `AppLifecycleManager`, `AudioEngine`, and `command_executor` to the GUI without duplicating logic or blocking the UI.
5. **USB & Hardware Management**: Live auto-discovery of ESP32 devices, non-blocking serial handshaking, audio meter testing, and OLED diagnostics.
6. **Guided Wi-Fi Management**: Step-by-step provisioning interface for wireless transport and access point modes.
7. **Activity Inspector & Diagnostics**: Structured, redacted history of voice interactions, transcripts, AI intents, and tool executions.
8. **Structured Settings System**: Configuration for appearance, face physics, illumination, speech, devices, AI credentials, and permissions.
9. **Offline-Ready Architecture**: Decoupled AI provider abstractions supporting local deterministic tools, local Whisper STT, and future local LLMs.
10. **Cross-Platform Verification & Packaging**: Full automated test suite and packaging validation for macOS (.app/.dmg) and Windows (.exe).

---

## 2. Current Architecture & Audit Findings

### Working Components (Preserved):
- **Continuous Assistant Pipeline** (`companion/continuous_assistant.py`): Continuous 16kHz PCM streaming over serial (921,600 baud), rolling ring buffer, WebRTC VAD, and follow-up interaction window.
- **Wake Word Engine** (`companion/wake_word.py`): openWakeWord detection ("Hey Jarvis") with refractory cooldown.
- **Local STT** (`companion/speech_to_text.py`): Faster-Whisper CPU/GPU transcription.
- **Dual Brain Reasoning** (`companion/ai_brain.py`): Zero-latency deterministic regex router + NVIDIA Nemotron/Llama 3.1 70B structured JSON intent classifier.
- **Tool Execution Registry** (`companion/command_executor.py`): App launching, web search, media control, volume, AST calculator, file tools, and screenshot capture to Desktop.
- **Visual Intelligence** (`companion/vision/`): In-process CoreGraphics capture on macOS, image Lanczos optimization, Llama 3.2 Vision inspection.
- **Platform Layer** (`companion/platform_layer/`): System Keychain vault (`keyring`), rotating logs with redaction, autostart, permissions (`CGPreflightScreenCaptureAccess`, `AVFoundation`).
- **Test Suite**: 214 unit and integration tests currently passing (`companion/tests/`).

### Identified Gaps & User Feedback Audit:
- **Desktop Face Deficiency**: The previous face consisted of two mechanical square eyes with black pupils inside an oversized cyan radial glow. It felt static, generic, and unalive.
- **DASAI Mochi Alignment**: Redesign the face to faithfully follow the **DASAI Mochi** automotive/desktop companion aesthetic:
  - Luminous organic pill/lozenge capsule eyes without pupils.
  - Floating breathing idle movement and smooth squashing blinks.
  - Expressive state morphs: attentive tall capsules (`LISTENING`), asymmetric quizzical tilt (`THINKING`), laser-focused lozenges (`EXECUTING`), bouncy speech reactivity (`SPEAKING`), and iconic inverted-U smiling crescents `^ ^` (`FOLLOW_UP` / `SUCCESS`).
  - Sleek dark obsidian glass visor with soft specular reflection instead of an oversized fuzzy cyan blob.
- **Top Header Status Buttons**: The previous top-right buttons had harsh solid green and red rectangular fills (`#00E676` and `#FF3D71`). Replace with understated, compact status indicators with subtle translucent pills and glowing status dots.
- **Sidebar & Action Button Emojis**: Replace generic emojis (`🏠`, `🔌`, `📜`, `⚙️`, `🎙️`, `🔍`, `📸`) with a consistent, professional vector-inspired icon system.
- **Conversation Area**: Redesign the transcript area from bordered input boxes into a clean, modern conversation stream with distinct typography and layout hierarchy.

---

## 3. Technology Stack & Design System

### Technology Stack:
- **UI Framework**: PySide6 (Qt 6.12+).
  - *Rationale*: Native performance, hardware-accelerated 2D/3D graphics, frameless transparent window capabilities, click-through window attributes, and seamless integration with the existing Python backend.
- **Face Engine**: Custom Qt Graphics / QPainter component with high-DPI antialiasing, cubic Bezier curves, and spring-physics animations.
- **Overlay Engine**: Qt transparent frameless overlay with click-through attributes (`Qt.WindowTransparentForInput`, `Qt.WindowStaysOnTopHint`), multi-monitor support, and screenshot exclusion.
- **Thread Bridge**: Qt `QObject` with `Signal`/`Slot` architecture for thread-safe UI updates from the background `DeskBotAssistantWorker`.

### Futuristic Companion Design System:
- **Palette**:
  - Background (Deep Space): `#090C10`
  - Card / Panel Surface: `#111622`
  - Elevated Surface: `#161D2D`
  - Border / Outline: `#212C42`
  - Glow / Primary Accent: `#00E5FF` (Cyber Cyan)
  - Secondary Accent: `#7C4DFF` (Electric Violet)
  - Success: `#00E676` (Neon Mint)
  - Warning / Alert: `#FFB300` (Amber)
  - Error: `#FF3D71` (Neon Coral)
  - Text Primary: `#FFFFFF`
  - Text Secondary: `#8B9BB4`
- **Typography**:
  - System sans-serif: `SF Pro Display`, `Inter`, `Segoe UI`, `Helvetica Neue`.
  - Monospace (diagnostics/code): `SF Mono`, `JetBrains Mono`, `Consolas`.
- **Dimensions & Layout**:
  - Main Window: 980 x 660 (fixed minimum 900 x 600, responsive resizing).
  - Left Navigation Bar: 72px compact sidebar with high-contrast SVG-style icons.
  - Central Face Stage: 420 x 260 prominent viewport with subtle ambient glow.

---

## 4. Architectural Blueprint & Component Modules

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        DeskBot Desktop Window                          │
│                                                                        │
│  ┌──────────┐ ┌──────────────────────────────────────────────────────┐ │
│  │ Sidebar  │ │                   Header Bar                         │ │
│  │          │ │  [Device Status] [WiFi Status] [Mic] [Dev Mode] [Tray│ │
│  │  [Home]  │ ├──────────────────────────────────────────────────────┤ │
│  │          │ │                                                      │ │
│  │ [Devices]│ │               DESKBOT ANIMATED FACE                  │ │
│  │          │ │           (Scalable Vector Face Engine)              │ │
│  │[Activity]│ │                                                      │ │
│  │          │ │  State: [IDLE / LISTENING / THINKING / SPEAKING]     │ │
│  │[Settings]│ ├──────────────────────────────────────────────────────┤ │
│  │          │ │  Transcript Card / Recent Action / Live Controls     │ │
│  └──────────┘ └──────────────────────────────────────────────────────┘ │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Qt Signals & Slots
┌───────────────────────────────────▼────────────────────────────────────┐
│                    DeskBot Event & Bridge Layer                        │
│                (companion/ui/bridge.py & controller.py)                │
└───────────▲───────────────────────▲──────────────────────▲─────────────┘
            │                       │                      │
┌───────────┴───────────┐ ┌─────────┴──────────┐ ┌─────────┴────────────┐
│ Assistant Engine      │ │ Device Manager     │ │ Screen Overlay       │
│ - AssistantState      │ │ - Auto-discovery   │ │ - Transparent Canvas │
│ - Faster-Whisper STT  │ │ - Serial Handshake │ │ - Edge Pulse Shader  │
│ - openWakeWord        │ │ - Wi-Fi Manager    │ │ - Click-through      │
│ - Nemotron AI / Tools │ │ - Audio streaming  │ │ - Screenshot-safe    │
└───────────────────────┘ └────────────────────┘ └──────────────────────┘
```

---

## 5. Implementation Status & Verification Milestones

### Phase 1: Bridge Layer & Event Architecture (`companion/ui/bridge.py`) — [COMPLETED]
- Implemented `DeskBotBridge(QObject)` with Qt signals:
  - `state_changed(str, str, str)` (old_state, new_state, context)
  - `wake_detected(float)` (confidence)
  - `touch_triggered()` (capacitive touch)
  - `speech_start()` & `speech_end()`
  - `transcript_received(str)` (user command)
  - `ai_intent_resolved(str)` (action)
  - `direct_answer_emitted(str)` (AI response)
  - `tool_executed(str, bool, str)` (tool, success, message)
  - `audio_level_updated(float)` (live mic meter)
  - `device_status_changed(bool, str, str)` (connected, port, description)
  - `wifi_status_changed(bool, str, str)` (connected, mode, target)
  - `activity_logged(dict)` (audit log event)
- Integrated into `AssistantStateMachine` via `_safe_get_bridge()` helper.
- Module aliasing in `sys.modules` prevents duplicate class identities.
- *Verification*: `test_ui_bridge.py` passed (5/5 tests).

### Phase 2: Vector Animated Face Engine (`companion/ui/face_engine.py`) — [COMPLETED]
- Implemented `DeskBotFaceWidget(QWidget)` with antialiased `QPainter`.
- Exact visual reproduction of physical OLED expressions:
  - **IDLE/CALM**: Rounded-rect eyes (aspect 1:1), centered pupils, natural blinking timer, micro-saccade eye darts.
  - **LISTENING**: Heightened vertical aperture (tall alert eyes), wide pupils, subtle cyan audio reactivity pulse.
  - **TRANSCRIBING**: Pupils scanning top-left.
  - **THINKING**: Asymmetric raised eyebrow / questioning eye height, smooth oscillation.
  - **EXECUTING**: Focused narrow eyes, determined posture.
  - **SPEAKING**: Expressive animated eye curves and joyful smiling mouth aperture.
  - **ERROR**: Slanted downward brow lines, puzzled pupils.
  - **SLEEPY/OFFLINE**: Half-closed relaxed eyelids with calm breathing glow.
- 60 FPS smooth transitions via `QTimer` with ease-in-out interpolation and audio reactivity.
- *Verification*: `test_face_engine.py` passed (4/4 tests).

### Phase 3: Screen-Edge Illumination Overlay (`companion/ui/edge_overlay.py`) — [COMPLETED]
- Implemented `ScreenEdgeOverlay(QWidget)`:
  - Frameless, stays-on-top, click-through (`Qt.WindowTransparentForInput | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool`).
  - Screen boundary tracking with linear & radial gradient illumination.
  - Color palette mapped to assistant states (Listening cyan, Transcribing blue, Thinking magenta, Executing emerald, Speaking electric blue).
  - Multi-monitor / primary display geometry support.
  - Automatic screenshot suppression hook (`suppress_for_screenshot(duration_ms=300)`) integrated into `capture_raw_screen()`.
- *Verification*: `test_edge_overlay.py` passed (5/5 tests).

### Phase 4: Main Desktop Window & Navigation (`companion/ui/main_window.py`) — [COMPLETED]
- Cohesive 980x660 window with 200px obsidian navigation sidebar and view switching:
  - **Home View** (`views/home_view.py`): Central face stage, live state pill, real-time transcript card, Push-To-Talk trigger, on-demand screen inspect.
  - **Devices View** (`views/devices_view.py`): Serial auto-detection card, port selector, interactive microphone meter, OLED face tester, guided Wi-Fi provisioning.
  - **Activity View** (`views/activity_view.py`): Chronological event timeline, category badges, secret token redaction (`nvapi-••••`), search filter.
  - **Settings View** (`views/settings_view.py`): NVIDIA NIM credential vault, wake sensitivity, Faster-Whisper model selector, edge overlay toggle, macOS privacy settings links.
- *Verification*: `test_main_window.py` passed (4/4 tests).

### Phase 5: USB Auto-Discovery & Wi-Fi Management — [COMPLETED]
- Auto-discovery probes candidate ports without hardcoded ports.
- Guided Wi-Fi interface supporting Station and SoftAP configuration modes.
- Seamless hotplug reconnect integrated with `DeskBotBridge`.
- *Verification*: Device discovery unit tests passed.

### Phase 6: System Tray, Packaging & Unified Entrypoint (`companion/app.py`) — [COMPLETED]
- Updated `companion/app.py` to launch the modern PySide6 desktop application by default.
- Native `QSystemTrayIcon` minimize-to-tray and close-to-tray support.
- Headless CLI fallback (`--cli`) fully preserved.
- Updated `build/deskbot-macos.spec` with PySide6 hidden imports.
- *Verification*: Full test suite execution across all 234 tests (230 passed, 4 skipped, 0 failed).

---

## 6. Verification Summary

```text
======================== 231 passed, 4 skipped in 4.43s ========================
```
- Total test cases: 235
- Passed: 231
- Skipped: 4 (Windows-specific SAPI tests on macOS)
- Failed: 0
- Regressions: 0
- Visual Verification: Rendered and validated offscreen previews for all DASAI Mochi moods (`IDLE`, `LISTENING`, `THINKING`, `FOLLOW_UP`, `SPEAKING`) and full desktop UI layout (`deskbot_main_window.png`).
- Codebase Cleanliness: Zero 8-digit hex colors in QSS, zero generic emojis in UI buttons/navigation.


