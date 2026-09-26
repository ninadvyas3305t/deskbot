#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "driver/i2s.h"

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

enum Behavior
{
    IDLE,
    LOOK_LEFT,
    LOOK_RIGHT,
    BLINK,
    DOUBLE_BLINK
};

enum Mood
{
    CALM,
    CURIOUS,
    SLEEPY
};

Behavior currentBehavior = IDLE;
Mood currentMood = CALM;

unsigned long nextBehaviorTime = 0;

void drawPupils()
{
    display.fillCircle(
        40 + eyeOffsetX,
        32 + eyeOffsetY,
        4,
        SSD1306_BLACK);

    display.fillCircle(
        88 + eyeOffsetX,
        32 + eyeOffsetY,
        4,
        SSD1306_BLACK);
}

void drawEyesOpen()
{
    display.clearDisplay();

    switch (currentMood)
    {
        case CALM:
            display.fillRoundRect(
                28 + eyeOffsetX,
                20 + eyeOffsetY,
                24,
                24,
                8,
                SSD1306_WHITE);

            drawPupils();

            display.fillRoundRect(
                76 + eyeOffsetX,
                20 + eyeOffsetY,
                24,
                24,
                8,
                SSD1306_WHITE);

            drawPupils();
            break;

        case CURIOUS:
            display.fillRoundRect(
                28 + eyeOffsetX,
                16 + eyeOffsetY,
                24,
                32,
                8,
                SSD1306_WHITE);

            drawPupils();

            display.fillRoundRect(
                76 + eyeOffsetX,
                16 + eyeOffsetY,
                24,
                32,
                8,
                SSD1306_WHITE);

            drawPupils();
            break;

        case SLEEPY:
            display.fillRoundRect(
                28 + eyeOffsetX,
                28 + eyeOffsetY,
                24,
                12,
                6,
                SSD1306_WHITE);

            display.fillRoundRect(
                76 + eyeOffsetX,
                28 + eyeOffsetY,
                24,
                12,
                6,
                SSD1306_WHITE);
            break;
    }

    display.display();
}

void drawEyesClosed()
{
    display.clearDisplay();

    display.fillRoundRect(
        28 + eyeOffsetX,
        30 + eyeOffsetY,
        24,
        4,
        2,
        SSD1306_WHITE);

    display.fillRoundRect(
        76 + eyeOffsetX,
        30 + eyeOffsetY,
        24,
        4,
        2,
        SSD1306_WHITE);

    display.display();
}

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

void drawStateFace(AssistantUIState state)
{
    display.clearDisplay();

    switch (state)
    {
        case UI_IDLE:
            display.fillRoundRect(28, 20, 24, 24, 8, SSD1306_WHITE);
            display.fillRoundRect(76, 20, 24, 24, 8, SSD1306_WHITE);
            display.fillCircle(40, 32, 4, SSD1306_BLACK);
            display.fillCircle(88, 32, 4, SSD1306_BLACK);
            break;

        case UI_LISTENING:
            // Alert / wide attentive open eyes
            display.fillRoundRect(28, 14, 24, 34, 10, SSD1306_WHITE);
            display.fillRoundRect(76, 14, 24, 34, 10, SSD1306_WHITE);
            display.fillCircle(40, 31, 5, SSD1306_BLACK);
            display.fillCircle(88, 31, 5, SSD1306_BLACK);
            display.setTextSize(1);
            display.setTextColor(SSD1306_WHITE);
            display.setCursor(38, 54);
            display.print("LISTENING");
            break;

        case UI_TRANSCRIBING:
            // Hearing / transcribing: eyes looking up & left
            display.fillRoundRect(28, 18, 24, 26, 8, SSD1306_WHITE);
            display.fillRoundRect(76, 18, 24, 26, 8, SSD1306_WHITE);
            display.fillCircle(36, 25, 4, SSD1306_BLACK);
            display.fillCircle(84, 25, 4, SSD1306_BLACK);
            display.setTextSize(1);
            display.setTextColor(SSD1306_WHITE);
            display.setCursor(44, 54);
            display.print("HEARING");
            break;

        case UI_THINKING:
            // Curious / thinking: one eye slightly raised
            display.fillRoundRect(28, 14, 24, 30, 8, SSD1306_WHITE);
            display.fillRoundRect(76, 20, 24, 24, 8, SSD1306_WHITE);
            display.fillCircle(40, 28, 4, SSD1306_BLACK);
            display.fillCircle(88, 32, 4, SSD1306_BLACK);
            display.setTextSize(1);
            display.setTextColor(SSD1306_WHITE);
            display.setCursor(40, 54);
            display.print("THINKING");
            break;

        case UI_EXECUTING:
            // Focused / determined eyes
            display.fillRoundRect(28, 24, 24, 18, 6, SSD1306_WHITE);
            display.fillRoundRect(76, 24, 24, 18, 6, SSD1306_WHITE);
            display.fillCircle(40, 33, 4, SSD1306_BLACK);
            display.fillCircle(88, 33, 4, SSD1306_BLACK);
            display.setTextSize(1);
            display.setTextColor(SSD1306_WHITE);
            display.setCursor(37, 54);
            display.print("EXECUTING");
            break;

        case UI_SPEAKING:
            // Talking / responding face: bright animated eyes with open smile
            display.fillRoundRect(28, 16, 24, 28, 8, SSD1306_WHITE);
            display.fillRoundRect(76, 16, 24, 28, 8, SSD1306_WHITE);
            display.fillCircle(40, 30, 4, SSD1306_BLACK);
            display.fillCircle(88, 30, 4, SSD1306_BLACK);
            display.fillRoundRect(54, 38, 20, 8, 3, SSD1306_WHITE);
            display.setTextSize(1);
            display.setTextColor(SSD1306_WHITE);
            display.setCursor(40, 54);
            display.print("SPEAKING");
            break;

        case UI_ERROR:
            // Confused / sad eyes with slanted brows
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

void applyAssistantState(const String &cmd)
{
    if (cmd == "STATE_IDLE")
    {
        currentUIState = UI_IDLE;
        currentMood = CALM;
        eyeOffsetX = 0;
        eyeOffsetY = 0;
        drawStateFace(UI_IDLE);
    }
    else if (cmd == "STATE_LISTENING")
    {
        currentUIState = UI_LISTENING;
        drawStateFace(UI_LISTENING);
    }
    else if (cmd == "STATE_TRANSCRIBING")
    {
        currentUIState = UI_TRANSCRIBING;
        drawStateFace(UI_TRANSCRIBING);
    }
    else if (cmd == "STATE_THINKING")
    {
        currentUIState = UI_THINKING;
        drawStateFace(UI_THINKING);
    }
    else if (cmd == "STATE_EXECUTING")
    {
        currentUIState = UI_EXECUTING;
        drawStateFace(UI_EXECUTING);
    }
    else if (cmd == "STATE_SPEAKING")
    {
        currentUIState = UI_SPEAKING;
        drawStateFace(UI_SPEAKING);
    }
    else if (cmd == "STATE_FOLLOW_UP")
    {
        currentUIState = UI_LISTENING;
        drawStateFace(UI_LISTENING);
    }
    else if (cmd == "STATE_ERROR")
    {
        currentUIState = UI_ERROR;
        drawStateFace(UI_ERROR);
    }
}


void lookTo(int targetX)
{
    while (eyeOffsetX != targetX)
    {
        if (eyeOffsetX < targetX)
            eyeOffsetX++;
        else
            eyeOffsetX--;

        drawEyesOpen();
        delay(40);
    }
}

void chooseBehavior()
{
    int r = random(100);

    switch (currentMood)
    {
        case CALM:
            if (r < 55)
                currentBehavior = IDLE;
            else if (r < 70)
                currentBehavior = BLINK;
            else if (r < 82)
                currentBehavior = LOOK_LEFT;
            else if (r < 94)
                currentBehavior = LOOK_RIGHT;
            else
                currentBehavior = DOUBLE_BLINK;
            break;

        case CURIOUS:
            if (r < 25)
                currentBehavior = IDLE;
            else if (r < 42)
                currentBehavior = BLINK;
            else if (r < 62)
                currentBehavior = LOOK_LEFT;
            else if (r < 82)
                currentBehavior = LOOK_RIGHT;
            else
                currentBehavior = DOUBLE_BLINK;
            break;

        case SLEEPY:
            if (r < 78)
                currentBehavior = IDLE;
            else
                currentBehavior = BLINK;
            break;
    }
}

void chooseMood()
{
    int r = random(100);

    if (r < 60)
        currentMood = CALM;
    else if (r < 90)
        currentMood = CURIOUS;
    else
        currentMood = SLEEPY;
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
        .dma_buf_count = 8,
        .dma_buf_len = 64,
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
        bool currentTouch = digitalRead(touchPin);
        if (currentTouch && !lastTouchState && (millis() - lastTouchTime > 400))
        {
            lastTouchTime = millis();
            Serial.print("\nTOUCH_TRIGGER_\n");
            Serial.flush();
        }
        lastTouchState = currentTouch;

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
    }

    Serial.flush();
    Serial.println();
    Serial.println("STREAM_END");
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

    Serial.println("DeskBot Face Engine Started (Speaker Audio Disabled)");

    Wire.begin(8, 9);
    Wire.setClock(400000); // 400kHz Fast I2C for non-blocking OLED rendering

    if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C))
    {
        while (true);
    }

    randomSeed(micros());
    lastInteraction = millis();

    setupMicrophone();

    drawEyesOpen();
}

void loop()
{
    handleSerialCommand();

    // When an active assistant state is showing, hold the face and skip idle behaviors
    if (currentUIState != UI_IDLE)
        return;

    if (currentMood == CURIOUS && millis() > curiousUntil)
    {
        currentMood = CALM;
        drawEyesOpen();
    }

    if (currentMood == CALM && millis() - lastInteraction > 30000)
    {
        currentMood = SLEEPY;
        drawEyesOpen();
    }

    bool currentTouch = digitalRead(touchPin);

    // ================= TOUCH =================
    if (currentTouch && !lastTouchState && (millis() - lastTouchTime > 400))
    {
        lastTouchTime = millis();
        Serial.print("\nTOUCH_TRIGGER\n");
        Serial.flush();
        lastInteraction = millis();
        curiousUntil = millis() + 5000;

        if (currentMood == SLEEPY)
        {
            currentMood = CURIOUS;
            drawEyesOpen();
        }
        else
        {
            currentMood = CURIOUS;
            drawEyesOpen();
        }
    }
    lastTouchState = currentTouch;

    if (millis() < nextBehaviorTime)
        return;

    chooseBehavior();

    switch (currentBehavior)
    {
        case IDLE:
            lookTo(0);
            nextBehaviorTime = millis() + random(2500, 7000);
            break;

        case LOOK_LEFT:
            lookTo(-4);
            delay(random(250, 500));
            lookTo(0);
            nextBehaviorTime = millis() + random(2000, 5000);
            break;

        case LOOK_RIGHT:
            lookTo(4);
            delay(random(250, 500));
            lookTo(0);
            nextBehaviorTime = millis() + random(2000, 5000);
            break;

        case BLINK:
            drawEyesClosed();
            delay(random(80, 140));
            drawEyesOpen();
            nextBehaviorTime = millis() + random(3000, 7000);
            break;

        case DOUBLE_BLINK:
            drawEyesClosed();
            delay(random(80, 120));
            drawEyesOpen();
            delay(random(100, 180));
            drawEyesClosed();
            delay(random(80, 120));
            drawEyesOpen();
            nextBehaviorTime = millis() + random(5000, 9000);
            break;
    }
}