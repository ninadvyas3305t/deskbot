#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "driver/i2s.h"

#include "audio_dsp.h"
#include "embedded_ml.h"
#include "protocol.h"
#include "state_machine.h"

AudioDSP audioDSP;
EmbeddedML embeddedML;
DeviceStateMachine deviceStateMachine;

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64

Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

int eyeOffsetX = 0;
int eyeOffsetY = 0;

// ================= SPEAKER PINS (POSTPONED & SILENCED) =================
// Pulled LOW to prevent MAX98357A amplifier crackle while hardware is being redesigned.
#define SPK_DOUT 15
#define SPK_BCLK 16
#define SPK_LRC  17

// ================= MICROPHONE (INMP441) =================
#define MIC_I2S_PORT I2S_NUM_1

#define MIC_SCK 4
#define MIC_WS  5
#define MIC_SD  6

#define SAMPLE_RATE 16000
#define MIC_BUFFER_SIZE 256
#define STREAM_CHUNK_SAMPLES 256
#define RECORD_BAUD 921600

int32_t micSamples[MIC_BUFFER_SIZE];
bool microphoneReady = false;

const int touchPin = 7;
bool lastTouchState = false;
unsigned long lastTouchTime = 0;

unsigned long curiousUntil = 0;
unsigned long lastInteraction = 0;

enum Mood
{
    CALM,
    CURIOUS,
    SLEEPY
};

Mood currentMood = CALM;

// ================= ASSISTANT UI STATES =================
enum AssistantUIState
{
    UI_IDLE,
    UI_LISTENING,
    UI_TRANSCRIBING,
    UI_THINKING,
    UI_EXECUTING,
    UI_SPEAKING,
    UI_ERROR
};

AssistantUIState currentUIState = UI_IDLE;

// ================= BLINK TIMING & PHASES =================
enum BlinkPhase
{
    BLINK_PHASE_IDLE,         // Eyes open, waiting for next blink
    BLINK_PHASE_CLOSING,      // Squashing down (~32ms)
    BLINK_PHASE_CLOSED,       // Slit line (~50ms)
    BLINK_PHASE_OPENING,      // Expanding up (~32ms)
    BLINK_PHASE_DOUBLE_PAUSE  // Brief open pause between double-blinks (~130ms)
};

BlinkPhase blinkPhase = BLINK_PHASE_IDLE;
unsigned long nextBlinkTime = 0;
unsigned long blinkPhaseEndTime = 0;
bool isDoubleBlinkActive = false;
bool isSecondBlinkDone = false;
int blinkCounter = 0;

// ================= IDLE NON-BLOCKING GLANCE =================
enum GlanceState
{
    GLANCE_CENTER,
    GLANCE_LEFT,
    GLANCE_RIGHT
};

GlanceState glanceState = GLANCE_CENTER;
unsigned long nextGlanceTime = 0;
unsigned long glanceReturnTime = 0;

// Helper to determine natural blink delay based on state
unsigned long getNextBlinkDelay(AssistantUIState state)
{
    if (state == UI_LISTENING)
    {
        // Attentive state: steady 3.0 to 4.5 seconds
        return random(3000, 4500);
    }
    if (state == UI_EXECUTING)
    {
        // Focused state: 2.8 to 4.2 seconds
        return random(2800, 4200);
    }
    if (state == UI_THINKING)
    {
        // Thinking state: 2.5 to 4.0 seconds
        return random(2500, 4000);
    }
    if (state == UI_SPEAKING)
    {
        // Expressive talking state: 2.2 to 3.8 seconds
        return random(2200, 3800);
    }

    // UI_IDLE / CALM / CURIOUS / SLEEPY:
    blinkCounter++;
    // Occasional relaxed breath pause every 5th blink
    if (blinkCounter % 5 == 0)
    {
        return random(4000, 5200);
    }

    // Standard natural blink interval: 2.0 to 3.8 seconds with modest variation
    return random(2000, 3800);
}

bool shouldDoubleBlink(AssistantUIState state)
{
    // Double blinks add lively personality during IDLE / CALM / CURIOUS
    if (state != UI_IDLE) return false;
    if (currentMood == SLEEPY) return false;
    return (random(100) < 18); // ~18% chance
}

void resetBlinkState()
{
    blinkPhase = BLINK_PHASE_IDLE;
    isDoubleBlinkActive = false;
    isSecondBlinkDone = false;
    nextBlinkTime = millis() + getNextBlinkDelay(currentUIState);
}

// ================= RENDERING ENGINE =================
// blinkStage:
//   0 = Open eyes
//   1 = Closing squish (~50% height)
//   2 = Closed slit (4px height)
//   3 = Opening recovery (~70% height)
void renderCurrentFace(int blinkStage = 0)
{
    display.clearDisplay();

    switch (currentUIState)
    {
        case UI_IDLE:
            switch (currentMood)
            {
                case CALM:
                    if (blinkStage == 0)
                    {
                        // Open: 24x24 at y=20 (center Y=32)
                        display.fillRoundRect(28 + eyeOffsetX, 20 + eyeOffsetY, 24, 24, 8, SSD1306_WHITE);
                        display.fillRoundRect(76 + eyeOffsetX, 20 + eyeOffsetY, 24, 24, 8, SSD1306_WHITE);
                        display.fillCircle(40 + eyeOffsetX, 32 + eyeOffsetY, 4, SSD1306_BLACK);
                        display.fillCircle(88 + eyeOffsetX, 32 + eyeOffsetY, 4, SSD1306_BLACK);
                    }
                    else if (blinkStage == 1)
                    {
                        // Closing: 24x12 at y=26 (radius 4)
                        display.fillRoundRect(28 + eyeOffsetX, 26 + eyeOffsetY, 24, 12, 4, SSD1306_WHITE);
                        display.fillRoundRect(76 + eyeOffsetX, 26 + eyeOffsetY, 24, 12, 4, SSD1306_WHITE);
                    }
                    else if (blinkStage == 2)
                    {
                        // Closed slit: 24x4 at y=30 (radius 2)
                        display.fillRoundRect(28 + eyeOffsetX, 30 + eyeOffsetY, 24, 4, 2, SSD1306_WHITE);
                        display.fillRoundRect(76 + eyeOffsetX, 30 + eyeOffsetY, 24, 4, 2, SSD1306_WHITE);
                    }
                    else if (blinkStage == 3)
                    {
                        // Opening: 24x18 at y=23 (radius 6)
                        display.fillRoundRect(28 + eyeOffsetX, 23 + eyeOffsetY, 24, 18, 6, SSD1306_WHITE);
                        display.fillRoundRect(76 + eyeOffsetX, 23 + eyeOffsetY, 24, 18, 6, SSD1306_WHITE);
                        display.fillCircle(40 + eyeOffsetX, 32 + eyeOffsetY, 3, SSD1306_BLACK);
                        display.fillCircle(88 + eyeOffsetX, 32 + eyeOffsetY, 3, SSD1306_BLACK);
                    }
                    break;

                case CURIOUS:
                    if (blinkStage == 0)
                    {
                        // Open: 24x32 at y=16 (center Y=32)
                        display.fillRoundRect(28 + eyeOffsetX, 16 + eyeOffsetY, 24, 32, 8, SSD1306_WHITE);
                        display.fillRoundRect(76 + eyeOffsetX, 16 + eyeOffsetY, 24, 32, 8, SSD1306_WHITE);
                        display.fillCircle(40 + eyeOffsetX, 32 + eyeOffsetY, 4, SSD1306_BLACK);
                        display.fillCircle(88 + eyeOffsetX, 32 + eyeOffsetY, 4, SSD1306_BLACK);
                    }
                    else if (blinkStage == 1)
                    {
                        // Closing: 24x16 at y=24 (radius 5)
                        display.fillRoundRect(28 + eyeOffsetX, 24 + eyeOffsetY, 24, 16, 5, SSD1306_WHITE);
                        display.fillRoundRect(76 + eyeOffsetX, 24 + eyeOffsetY, 24, 16, 5, SSD1306_WHITE);
                    }
                    else if (blinkStage == 2)
                    {
                        // Closed: 24x4 at y=30 (radius 2)
                        display.fillRoundRect(28 + eyeOffsetX, 30 + eyeOffsetY, 24, 4, 2, SSD1306_WHITE);
                        display.fillRoundRect(76 + eyeOffsetX, 30 + eyeOffsetY, 24, 4, 2, SSD1306_WHITE);
                    }
                    else if (blinkStage == 3)
                    {
                        // Opening: 24x24 at y=20 (radius 7)
                        display.fillRoundRect(28 + eyeOffsetX, 20 + eyeOffsetY, 24, 24, 7, SSD1306_WHITE);
                        display.fillRoundRect(76 + eyeOffsetX, 20 + eyeOffsetY, 24, 24, 7, SSD1306_WHITE);
                        display.fillCircle(40 + eyeOffsetX, 32 + eyeOffsetY, 3, SSD1306_BLACK);
                        display.fillCircle(88 + eyeOffsetX, 32 + eyeOffsetY, 3, SSD1306_BLACK);
                    }
                    break;

                case SLEEPY:
                    if (blinkStage == 0)
                    {
                        // Open: 24x12 at y=28 (center Y=34)
                        display.fillRoundRect(28 + eyeOffsetX, 28 + eyeOffsetY, 24, 12, 6, SSD1306_WHITE);
                        display.fillRoundRect(76 + eyeOffsetX, 28 + eyeOffsetY, 24, 12, 6, SSD1306_WHITE);
                    }
                    else if (blinkStage == 1)
                    {
                        // Closing: 24x8 at y=30 (radius 3)
                        display.fillRoundRect(28 + eyeOffsetX, 30 + eyeOffsetY, 24, 8, 3, SSD1306_WHITE);
                        display.fillRoundRect(76 + eyeOffsetX, 30 + eyeOffsetY, 24, 8, 3, SSD1306_WHITE);
                    }
                    else if (blinkStage == 2)
                    {
                        // Closed: 24x4 at y=32 (radius 2)
                        display.fillRoundRect(28 + eyeOffsetX, 32 + eyeOffsetY, 24, 4, 2, SSD1306_WHITE);
                        display.fillRoundRect(76 + eyeOffsetX, 32 + eyeOffsetY, 24, 4, 2, SSD1306_WHITE);
                    }
                    else if (blinkStage == 3)
                    {
                        // Opening: 24x10 at y=29 (radius 4)
                        display.fillRoundRect(28 + eyeOffsetX, 29 + eyeOffsetY, 24, 10, 4, SSD1306_WHITE);
                        display.fillRoundRect(76 + eyeOffsetX, 29 + eyeOffsetY, 24, 10, 4, SSD1306_WHITE);
                    }
                    break;
            }
            break;

        case UI_LISTENING:
            // Alert attentive eyes (center Y=31) + text
            display.setTextSize(1);
            display.setTextColor(SSD1306_WHITE);
            display.setCursor(38, 54);
            display.print("LISTENING");

            if (blinkStage == 0)
            {
                // Open: 24x34 at y=14
                display.fillRoundRect(28, 14, 24, 34, 10, SSD1306_WHITE);
                display.fillRoundRect(76, 14, 24, 34, 10, SSD1306_WHITE);
                display.fillCircle(40, 31, 5, SSD1306_BLACK);
                display.fillCircle(88, 31, 5, SSD1306_BLACK);
            }
            else if (blinkStage == 1)
            {
                // Closing: 24x16 at y=23
                display.fillRoundRect(28, 23, 24, 16, 5, SSD1306_WHITE);
                display.fillRoundRect(76, 23, 24, 16, 5, SSD1306_WHITE);
            }
            else if (blinkStage == 2)
            {
                // Closed: 24x4 at y=29
                display.fillRoundRect(28, 29, 24, 4, 2, SSD1306_WHITE);
                display.fillRoundRect(76, 29, 24, 4, 2, SSD1306_WHITE);
            }
            else if (blinkStage == 3)
            {
                // Opening: 24x26 at y=18
                display.fillRoundRect(28, 18, 24, 26, 8, SSD1306_WHITE);
                display.fillRoundRect(76, 18, 24, 26, 8, SSD1306_WHITE);
                display.fillCircle(40, 31, 4, SSD1306_BLACK);
                display.fillCircle(88, 31, 4, SSD1306_BLACK);
            }
            break;

        case UI_TRANSCRIBING:
            // Hearing eyes looking up-left (center Y=31) + text
            display.setTextSize(1);
            display.setTextColor(SSD1306_WHITE);
            display.setCursor(44, 54);
            display.print("HEARING");

            if (blinkStage == 0)
            {
                // Open: 24x26 at y=18
                display.fillRoundRect(28, 18, 24, 26, 8, SSD1306_WHITE);
                display.fillRoundRect(76, 18, 24, 26, 8, SSD1306_WHITE);
                display.fillCircle(36, 25, 4, SSD1306_BLACK);
                display.fillCircle(84, 25, 4, SSD1306_BLACK);
            }
            else if (blinkStage == 1)
            {
                display.fillRoundRect(28, 24, 24, 14, 5, SSD1306_WHITE);
                display.fillRoundRect(76, 24, 24, 14, 5, SSD1306_WHITE);
            }
            else if (blinkStage == 2)
            {
                display.fillRoundRect(28, 29, 24, 4, 2, SSD1306_WHITE);
                display.fillRoundRect(76, 29, 24, 4, 2, SSD1306_WHITE);
            }
            else if (blinkStage == 3)
            {
                display.fillRoundRect(28, 21, 24, 20, 6, SSD1306_WHITE);
                display.fillRoundRect(76, 21, 24, 20, 6, SSD1306_WHITE);
                display.fillCircle(36, 25, 3, SSD1306_BLACK);
                display.fillCircle(84, 25, 3, SSD1306_BLACK);
            }
            break;

        case UI_THINKING:
            // Curious raised left eye (left center Y=29, right center Y=32) + text
            display.setTextSize(1);
            display.setTextColor(SSD1306_WHITE);
            display.setCursor(40, 54);
            display.print("THINKING");

            if (blinkStage == 0)
            {
                // Left raised (24x30 at y=14), Right normal (24x24 at y=20)
                display.fillRoundRect(28, 14, 24, 30, 8, SSD1306_WHITE);
                display.fillRoundRect(76, 20, 24, 24, 8, SSD1306_WHITE);
                display.fillCircle(40, 28, 4, SSD1306_BLACK);
                display.fillCircle(88, 32, 4, SSD1306_BLACK);
            }
            else if (blinkStage == 1)
            {
                display.fillRoundRect(28, 22, 24, 14, 4, SSD1306_WHITE);
                display.fillRoundRect(76, 26, 24, 12, 4, SSD1306_WHITE);
            }
            else if (blinkStage == 2)
            {
                display.fillRoundRect(28, 27, 24, 4, 2, SSD1306_WHITE);
                display.fillRoundRect(76, 30, 24, 4, 2, SSD1306_WHITE);
            }
            else if (blinkStage == 3)
            {
                display.fillRoundRect(28, 18, 24, 22, 6, SSD1306_WHITE);
                display.fillRoundRect(76, 23, 24, 18, 6, SSD1306_WHITE);
                display.fillCircle(40, 28, 3, SSD1306_BLACK);
                display.fillCircle(88, 32, 3, SSD1306_BLACK);
            }
            break;

        case UI_EXECUTING:
            // Determined focused eyes (center Y=33) + text
            display.setTextSize(1);
            display.setTextColor(SSD1306_WHITE);
            display.setCursor(37, 54);
            display.print("EXECUTING");

            if (blinkStage == 0)
            {
                // Open: 24x18 at y=24
                display.fillRoundRect(28, 24, 24, 18, 6, SSD1306_WHITE);
                display.fillRoundRect(76, 24, 24, 18, 6, SSD1306_WHITE);
                display.fillCircle(40, 33, 4, SSD1306_BLACK);
                display.fillCircle(88, 33, 4, SSD1306_BLACK);
            }
            else if (blinkStage == 1)
            {
                display.fillRoundRect(28, 28, 24, 10, 3, SSD1306_WHITE);
                display.fillRoundRect(76, 28, 24, 10, 3, SSD1306_WHITE);
            }
            else if (blinkStage == 2)
            {
                display.fillRoundRect(28, 31, 24, 4, 2, SSD1306_WHITE);
                display.fillRoundRect(76, 31, 24, 4, 2, SSD1306_WHITE);
            }
            else if (blinkStage == 3)
            {
                display.fillRoundRect(28, 26, 24, 14, 5, SSD1306_WHITE);
                display.fillRoundRect(76, 26, 24, 14, 5, SSD1306_WHITE);
                display.fillCircle(40, 33, 3, SSD1306_BLACK);
                display.fillCircle(88, 33, 3, SSD1306_BLACK);
            }
            break;

        case UI_SPEAKING:
            // Animated talking face (center Y=30) + mouth + text
            display.setTextSize(1);
            display.setTextColor(SSD1306_WHITE);
            display.setCursor(40, 54);
            display.print("SPEAKING");
            display.fillRoundRect(54, 38, 20, 8, 3, SSD1306_WHITE);

            if (blinkStage == 0)
            {
                // Open: 24x28 at y=16
                display.fillRoundRect(28, 16, 24, 28, 8, SSD1306_WHITE);
                display.fillRoundRect(76, 16, 24, 28, 8, SSD1306_WHITE);
                display.fillCircle(40, 30, 4, SSD1306_BLACK);
                display.fillCircle(88, 30, 4, SSD1306_BLACK);
            }
            else if (blinkStage == 1)
            {
                display.fillRoundRect(28, 23, 24, 14, 4, SSD1306_WHITE);
                display.fillRoundRect(76, 23, 24, 14, 4, SSD1306_WHITE);
            }
            else if (blinkStage == 2)
            {
                display.fillRoundRect(28, 28, 24, 4, 2, SSD1306_WHITE);
                display.fillRoundRect(76, 28, 24, 4, 2, SSD1306_WHITE);
            }
            else if (blinkStage == 3)
            {
                display.fillRoundRect(28, 19, 24, 22, 6, SSD1306_WHITE);
                display.fillRoundRect(76, 19, 24, 22, 6, SSD1306_WHITE);
                display.fillCircle(40, 30, 3, SSD1306_BLACK);
                display.fillCircle(88, 30, 3, SSD1306_BLACK);
            }
            break;

        case UI_ERROR:
            // Slanted brows, sad eyes, text ERROR
            display.fillRoundRect(28, 26, 24, 16, 6, SSD1306_WHITE);
            display.fillRoundRect(76, 26, 24, 16, 6, SSD1306_WHITE);
            display.fillCircle(38, 34, 3, SSD1306_BLACK);
            display.fillCircle(90, 34, 3, SSD1306_BLACK);
            display.drawLine(26, 22, 54, 27, SSD1306_WHITE);
            display.drawLine(74, 27, 102, 22, SSD1306_WHITE);
            display.setTextSize(1);
            display.setTextColor(SSD1306_WHITE);
            display.setCursor(48, 54);
            display.print("ERROR");
            break;
    }

    display.display();
}

// Backward-compatible wrappers
void drawPupils()
{
    display.fillCircle(40 + eyeOffsetX, 32 + eyeOffsetY, 4, SSD1306_BLACK);
    display.fillCircle(88 + eyeOffsetX, 32 + eyeOffsetY, 4, SSD1306_BLACK);
}

void drawEyesOpen()
{
    renderCurrentFace(0);
}

void drawEyesClosed()
{
    renderCurrentFace(2);
}

void drawStateFace(AssistantUIState state)
{
    currentUIState = state;
    resetBlinkState();
    renderCurrentFace(0);
}

void applyAssistantState(const String &cmd)
{
    AssistantUIState newState = currentUIState;

    if (cmd == "STATE_IDLE")
    {
        newState = UI_IDLE;
        currentMood = CALM;
        eyeOffsetX = 0;
        eyeOffsetY = 0;
        glanceState = GLANCE_CENTER;
    }
    else if (cmd == "STATE_LISTENING")
    {
        newState = UI_LISTENING;
        eyeOffsetX = 0;
        eyeOffsetY = 0;
    }
    else if (cmd == "STATE_TRANSCRIBING")
    {
        newState = UI_TRANSCRIBING;
        eyeOffsetX = 0;
        eyeOffsetY = 0;
    }
    else if (cmd == "STATE_THINKING")
    {
        newState = UI_THINKING;
        eyeOffsetX = 0;
        eyeOffsetY = 0;
    }
    else if (cmd == "STATE_EXECUTING")
    {
        newState = UI_EXECUTING;
        eyeOffsetX = 0;
        eyeOffsetY = 0;
    }
    else if (cmd == "STATE_SPEAKING")
    {
        newState = UI_SPEAKING;
        eyeOffsetX = 0;
        eyeOffsetY = 0;
    }
    else if (cmd == "STATE_FOLLOW_UP")
    {
        newState = UI_LISTENING;
        eyeOffsetX = 0;
        eyeOffsetY = 0;
    }
    else if (cmd == "STATE_ERROR")
    {
        newState = UI_ERROR;
        eyeOffsetX = 0;
        eyeOffsetY = 0;
    }

    currentUIState = newState;
    resetBlinkState();
    renderCurrentFace(0);
}

// Non-blocking glance & mood engine for IDLE
void updateIdleMoodAndGlance()
{
    if (currentUIState != UI_IDLE)
        return;

    unsigned long now = millis();

    // Mood transitions
    if (currentMood == CURIOUS && now > curiousUntil)
    {
        currentMood = CALM;
        renderCurrentFace(0);
    }
    else if (currentMood == CALM && (now - lastInteraction > 30000))
    {
        currentMood = SLEEPY;
        renderCurrentFace(0);
    }

    // Glances only occur when eyes are open and not sleepy
    if (blinkPhase != BLINK_PHASE_IDLE || currentMood == SLEEPY)
        return;

    if (glanceState == GLANCE_CENTER)
    {
        if (now >= nextGlanceTime)
        {
            if (random(100) < 50)
            {
                eyeOffsetX = -4;
                glanceState = GLANCE_LEFT;
            }
            else
            {
                eyeOffsetX = 4;
                glanceState = GLANCE_RIGHT;
            }
            glanceReturnTime = now + random(400, 700);
            nextGlanceTime = now + random(8000, 15000);
            renderCurrentFace(0);
        }
    }
    else
    {
        if (now >= glanceReturnTime)
        {
            eyeOffsetX = 0;
            glanceState = GLANCE_CENTER;
            renderCurrentFace(0);
        }
    }
}

// Non-blocking smooth blink animation engine
void updateFaceAnimation()
{
    // Do not blink in ERROR state
    if (currentUIState == UI_ERROR)
        return;

    unsigned long now = millis();

    switch (blinkPhase)
    {
        case BLINK_PHASE_IDLE:
            if (now >= nextBlinkTime)
            {
                isDoubleBlinkActive = shouldDoubleBlink(currentUIState);
                isSecondBlinkDone = false;
                blinkPhase = BLINK_PHASE_CLOSING;
                blinkPhaseEndTime = now + 32;
                renderCurrentFace(1); // Closing squish frame
            }
            break;

        case BLINK_PHASE_CLOSING:
            if (now >= blinkPhaseEndTime)
            {
                blinkPhase = BLINK_PHASE_CLOSED;
                blinkPhaseEndTime = now + 50;
                renderCurrentFace(2); // Closed slit frame
            }
            break;

        case BLINK_PHASE_CLOSED:
            if (now >= blinkPhaseEndTime)
            {
                blinkPhase = BLINK_PHASE_OPENING;
                blinkPhaseEndTime = now + 32;
                renderCurrentFace(3); // Opening recovery frame
            }
            break;

        case BLINK_PHASE_OPENING:
            if (now >= blinkPhaseEndTime)
            {
                if (isDoubleBlinkActive && !isSecondBlinkDone)
                {
                    // Transition to brief open pause between double-blinks
                    blinkPhase = BLINK_PHASE_DOUBLE_PAUSE;
                    blinkPhaseEndTime = now + random(120, 160);
                    renderCurrentFace(0); // Open eyes during pause
                }
                else
                {
                    // Single blink or second blink finished
                    blinkPhase = BLINK_PHASE_IDLE;
                    isDoubleBlinkActive = false;
                    isSecondBlinkDone = false;
                    nextBlinkTime = now + getNextBlinkDelay(currentUIState);
                    renderCurrentFace(0); // Return fully open
                }
            }
            break;

        case BLINK_PHASE_DOUBLE_PAUSE:
            if (now >= blinkPhaseEndTime)
            {
                // Trigger second blink
                isSecondBlinkDone = true;
                blinkPhase = BLINK_PHASE_CLOSING;
                blinkPhaseEndTime = now + 28;
                renderCurrentFace(1); // Closing frame
            }
            break;
    }
}

// ================= MICROPHONE SETUP =================
void setupMicrophone()
{
    i2s_config_t i2s_config = {
        .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
        .sample_rate = SAMPLE_RATE,
        .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
        .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
        .communication_format = I2S_COMM_FORMAT_STAND_I2S,
        .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
        .dma_buf_count = 12,
        .dma_buf_len = 128,
        .use_apll = false,
        .tx_desc_auto_clear = false,
        .fixed_mclk = 0
    };

    i2s_pin_config_t pin_config = {
        .bck_io_num = MIC_SCK,
        .ws_io_num = MIC_WS,
        .data_out_num = I2S_PIN_NO_CHANGE,
        .data_in_num = MIC_SD
    };

    Serial.println("Initializing microphone...");

    if (i2s_driver_install(
            MIC_I2S_PORT,
            &i2s_config,
            0,
            NULL) != ESP_OK)
    {
        Serial.println("Microphone I2S installation FAILED!");
        microphoneReady = false;
        return;
    }

    if (i2s_set_pin(
            MIC_I2S_PORT,
            &pin_config) != ESP_OK)
    {
        Serial.println("Microphone pin setup FAILED!");
        microphoneReady = false;
        return;
    }

    microphoneReady = true;
    Serial.println("Microphone initialized successfully.");
}

void checkTouchSensor()
{
    bool currentTouch = digitalRead(touchPin);
    if (currentTouch && !lastTouchState && (millis() - lastTouchTime > 400))
    {
        lastTouchTime = millis();
        Protocol::sendTouchTrigger();
        Serial.print("\nTOUCH_TRIGGER\n");
        Serial.flush();
        lastInteraction = millis();
        curiousUntil = millis() + 5000;

        if (currentUIState == UI_IDLE)
        {
            currentMood = CURIOUS;
            eyeOffsetX = 0;
            eyeOffsetY = 0;
            glanceState = GLANCE_CENTER;
            resetBlinkState();
            renderCurrentFace(0);
        }
    }
    lastTouchState = currentTouch;
}

String serialCmdBuffer = "";

void recordAudio()
{
    if (!microphoneReady)
    {
        Serial.println("MIC_NOT_READY");
        return;
    }

    Serial.println("STREAM_START");
    Serial.flush();

    bool streaming = true;

    while (streaming)
    {
        size_t bytesRead = 0;

        i2s_read(
            MIC_I2S_PORT,
            micSamples,
            sizeof(micSamples),
            &bytesRead,
            portMAX_DELAY
        );

        int count = bytesRead / sizeof(int32_t);

        for (int i = 0; i < count; i++)
        {
            // Convert INMP441 32-bit I2S sample to 16-bit PCM
            int16_t pcmSample = (int16_t)(micSamples[i] >> 16);

            Serial.write(
                (uint8_t *)&pcmSample,
                sizeof(pcmSample)
            );
        }

        // Check TTP223 touch sensor
        checkTouchSensor();

        // Non-blocking serial command processor
        while (Serial.available())
        {
            char c = (char)Serial.read();
            if (c == '\n' || c == '\r')
            {
                serialCmdBuffer.trim();
                if (serialCmdBuffer.length() > 0)
                {
                    if (serialCmdBuffer == "STOP_STREAM")
                    {
                        streaming = false;
                    }
                    else if (serialCmdBuffer.startsWith("STATE_"))
                    {
                        applyAssistantState(serialCmdBuffer);
                    }
                    serialCmdBuffer = "";
                }
            }
            else if (serialCmdBuffer.length() < 32)
            {
                serialCmdBuffer += c;
            }
        }

        // Non-blocking face animation and glance updates during streaming
        updateIdleMoodAndGlance();
        updateFaceAnimation();
    }

    Serial.flush();
    Serial.println();
    Serial.println("STREAM_END");
}

void recordAndClassifyCommand()
{
    if (!microphoneReady)
    {
        deviceStateMachine.resetToIdle();
        return;
    }

    Protocol::sendAudioStreamStart();
    Serial.println("STREAM_START");
    Serial.flush();

    embeddedML.resetCommandContext();

    unsigned long captureStartTime = millis();
    unsigned long lastSpeechTime = millis();
    bool speechEnded = false;
    bool activeStreaming = true;

    while (activeStreaming && (millis() - captureStartTime < 6500) && !speechEnded)
    {
        size_t bytesRead = 0;
        i2s_read(MIC_I2S_PORT, micSamples, sizeof(micSamples), &bytesRead, pdMS_TO_TICKS(15));

        if (bytesRead > 0)
        {
            int count = bytesRead / sizeof(int32_t);
            float melFrame[DSP_NUM_MEL_BINS];

            for (int i = 0; i < count; i++)
            {
                int16_t pcmSample = (int16_t)(micSamples[i] >> 16);

                // Stream PCM sample to desktop companion
                Serial.write((uint8_t *)&pcmSample, sizeof(pcmSample));

                if (audioDSP.processSample(pcmSample, melFrame))
                {
                    embeddedML.feedMelFrame(melFrame);

                    if (audioDSP.getCurrentRMS() > 0.040f)
                    {
                        lastSpeechTime = millis();
                    }
                }
            }
        }

        // Detect end of utterance: after at least 1.0s, silence for >600ms
        if ((millis() - captureStartTime > 1000) && (millis() - lastSpeechTime > 600))
        {
            speechEnded = true;
        }

        checkTouchSensor();

        // Check if companion sent commands during stream
        while (Serial.available())
        {
            char c = (char)Serial.read();
            if (c == '\n' || c == '\r')
            {
                serialCmdBuffer.trim();
                if (serialCmdBuffer.length() > 0)
                {
                    if (serialCmdBuffer == "STOP_STREAM")
                    {
                        activeStreaming = false;
                    }
                    else if (serialCmdBuffer.startsWith("STATE_"))
                    {
                        applyAssistantState(serialCmdBuffer);
                    }
                    serialCmdBuffer = "";
                }
            }
            else if (serialCmdBuffer.length() < 32)
            {
                serialCmdBuffer += c;
            }
        }

        updateFaceAnimation();
    }

    Serial.flush();
    Serial.println();
    Serial.println("STREAM_END");
    Protocol::sendAudioStreamEnd();

    // Run embedded ML command classification on captured utterance
    CommandInferenceResult cmdRes = embeddedML.runCommandClassification();
    if (cmdRes.command != CMD_NONE)
    {
        Protocol::sendCommandClassified(cmdRes.commandName, cmdRes.confidence, cmdRes.latencyMicros);
    }
    else
    {
        Protocol::sendUnrestrictedSpeech(cmdRes.confidence);
    }

    deviceStateMachine.transitionTo(DEV_STATE_WAITING_COMPANION, "Utterance captured");
}

void handleSerialCommand()
{
    while (Serial.available())
    {
        char c = (char)Serial.read();
        if (c == '\n' || c == '\r')
        {
            serialCmdBuffer.trim();
            if (serialCmdBuffer.length() > 0)
            {
                if (serialCmdBuffer == "START_STREAM")
                {
                    serialCmdBuffer = "";
                    recordAudio();
                    return;
                }
                else if (serialCmdBuffer.startsWith("STATE_"))
                {
                    applyAssistantState(serialCmdBuffer);
                    if (serialCmdBuffer == "STATE_IDLE")
                    {
                        deviceStateMachine.resetToIdle();
                    }
                    else if (serialCmdBuffer == "STATE_SPEAKING")
                    {
                        deviceStateMachine.transitionTo(DEV_STATE_SPEAKING);
                    }
                    else if (serialCmdBuffer == "STATE_THINKING")
                    {
                        deviceStateMachine.transitionTo(DEV_STATE_PROCESSING);
                    }
                }
                else if (serialCmdBuffer == "PING")
                {
                    Protocol::sendStatus(deviceStateMachine.getStateName(), esp_get_free_heap_size(), millis() / 1000);
                }
                else if (serialCmdBuffer == "RESET_WAKE")
                {
                    embeddedML.resetWakeContext();
                }
                serialCmdBuffer = "";
            }
        }
        else if (serialCmdBuffer.length() < 32)
        {
            serialCmdBuffer += c;
        }
    }
}

// ================= SETUP =================
void setup()
{
    Serial.begin(921600);

    // SILENCE SPEAKER PINS: Actively drive speaker pins LOW to eliminate amplifier crackling
    pinMode(SPK_DOUT, OUTPUT);
    digitalWrite(SPK_DOUT, LOW);
    pinMode(SPK_BCLK, OUTPUT);
    digitalWrite(SPK_BCLK, LOW);
    pinMode(SPK_LRC, OUTPUT);
    digitalWrite(SPK_LRC, LOW);

    pinMode(touchPin, INPUT_PULLDOWN);

    Wire.begin(8, 9);
    Wire.setClock(400000); // 400kHz Fast I2C for non-blocking OLED rendering

    if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C))
    {
        while (true);
    }

    randomSeed(micros());
    lastInteraction = millis();
    nextBlinkTime = millis() + random(1800, 2800);
    nextGlanceTime = millis() + random(6000, 10000);

    setupMicrophone();

    // Initialize On-Device DSP and Embedded Machine Learning engines
    audioDSP.init();
    embeddedML.init();
    deviceStateMachine.resetToIdle();

    // Announce device identity and capabilities over serial
    Protocol::sendDeviceReady("2.0.0", "ESP32-S3-N8", false, 8);

    renderCurrentFace(0);
}

void loop()
{
    handleSerialCommand();
    checkTouchSensor();
    deviceStateMachine.update();

    // 1. On-device Wake Word Detection when IDLE or WAITING_COMPANION
    if (microphoneReady &&
        (deviceStateMachine.getCurrentState() == DEV_STATE_IDLE ||
         deviceStateMachine.getCurrentState() == DEV_STATE_WAITING_COMPANION))
    {
        size_t bytesRead = 0;
        esp_err_t err = i2s_read(MIC_I2S_PORT, micSamples, sizeof(micSamples), &bytesRead, pdMS_TO_TICKS(10));
        if (err == ESP_OK && bytesRead > 0)
        {
            int count = bytesRead / sizeof(int32_t);
            float melFrame[DSP_NUM_MEL_BINS];

            for (int i = 0; i < count; i++)
            {
                int16_t pcmSample = (int16_t)(micSamples[i] >> 16);
                if (audioDSP.processSample(pcmSample, melFrame))
                {
                    embeddedML.feedMelFrame(melFrame);

                    WakeInferenceResult wakeRes = embeddedML.runWakeInference();
                    if (wakeRes.detected)
                    {
                        // Emit framed wake-word event
                        Protocol::sendWakeDetected(wakeRes.confidence, wakeRes.latencyMicros);

                        // Immediate responsive transition
                        deviceStateMachine.transitionTo(DEV_STATE_COMMAND_CAPTURE, "Embedded wake word detected");
                        applyAssistantState("STATE_LISTENING");
                        lastInteraction = millis();
                        curiousUntil = millis() + 6000;
                        break;
                    }
                }
            }
        }
    }

    // 2. Command Capture & Embedded Inference
    if (deviceStateMachine.getCurrentState() == DEV_STATE_COMMAND_CAPTURE)
    {
        recordAndClassifyCommand();
    }

    // 3. Periodic framed Heartbeat (every 12 seconds)
    static unsigned long lastHeartbeatTime = 0;
    static uint32_t heartbeatSeq = 0;
    if (millis() - lastHeartbeatTime > 12000)
    {
        lastHeartbeatTime = millis();
        Protocol::sendHeartbeat(heartbeatSeq++, millis());
    }

    // 4. Non-blocking face animation and glance
    updateIdleMoodAndGlance();
    updateFaceAnimation();
}
