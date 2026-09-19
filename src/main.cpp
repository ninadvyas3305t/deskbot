#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

#include <LittleFS.h>
#include "driver/i2s.h"
#include "AudioFileSourceLittleFS.h"
#include "AudioGeneratorWAV.h"
#include "AudioOutputI2S.h"

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64

Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

int eyeOffsetX = 0;
int eyeOffsetY = 0;

// ================= WAV AUDIO =================

#define I2S_DOUT 15
#define I2S_BCLK 16
#define I2S_LRC 17
// ================= MICROPHONE =================

#define MIC_I2S_PORT I2S_NUM_1

#define MIC_SCK 4
#define MIC_WS  5
#define MIC_SD  6

#define SAMPLE_RATE 16000
#define MIC_BUFFER_SIZE 256

int32_t micSamples[MIC_BUFFER_SIZE];

bool microphoneReady = false;

AudioOutputI2S *audioOutput = nullptr;
AudioGeneratorWAV *wavPlayer = nullptr;
AudioFileSourceLittleFS *wavFile = nullptr;


// Play a WAV file from LittleFS
void startWav(const char *filename)
{
    Serial.print("Starting: ");
    Serial.println(filename);

    // Stop any currently playing sound
    if (wavPlayer != nullptr)
    {
        if (wavPlayer->isRunning())
        {
            wavPlayer->stop();
        }

        delete wavPlayer;
        wavPlayer = nullptr;
    }

    if (wavFile != nullptr)
    {
        delete wavFile;
        wavFile = nullptr;
    }

    wavFile = new AudioFileSourceLittleFS(filename);
    wavPlayer = new AudioGeneratorWAV();

    if (!wavPlayer->begin(wavFile, audioOutput))
    {
        Serial.print("Failed to start: ");
        Serial.println(filename);

        delete wavPlayer;
        wavPlayer = nullptr;

        delete wavFile;
        wavFile = nullptr;

        return;
    }
}

void updateAudio()
{
    if (wavPlayer != nullptr && wavPlayer->isRunning())
    {
        if (!wavPlayer->loop())
        {
            wavPlayer->stop();

            delete wavPlayer;
            wavPlayer = nullptr;

            delete wavFile;
            wavFile = nullptr;

            Serial.println("Audio finished.");
        }
    }
}

const int touchPin = 7;

bool lastTouchState = false;

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

    Serial.print("Current Mood: ");

    switch (currentMood)
    {
        case CALM:
            Serial.println("CALM");
            break;

        case CURIOUS:
            Serial.println("CURIOUS");
            break;

        case SLEEPY:
            Serial.println("SLEEPY");
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

// ================= SETUP =================
void setup()
{
    Serial.begin(115200);

    pinMode(touchPin, INPUT);

    Serial.println("DeskBot Face Engine Started");

    Wire.begin(8, 9);

    if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C))
    {
        while (true);
    }

    randomSeed(micros());

    lastInteraction = millis();

   // ================= AUDIO SETUP =================

Serial.println("Initializing LittleFS...");

if (!LittleFS.begin(true))
{
    Serial.println("LittleFS initialization FAILED!");

    while (true)
    {
        delay(1000);
    }
}

Serial.println("LittleFS initialized successfully.");

// Create I2S audio output
audioOutput = new AudioOutputI2S();

audioOutput->SetPinout(
    I2S_BCLK,
    I2S_LRC,
    I2S_DOUT
);

// Start with moderate volume
audioOutput->SetGain(0.35);

Serial.println("WAV audio initialized.");
// ================= MICROPHONE =================

setupMicrophone();



// ===============================================

randomSeed(micros());

lastInteraction = millis();

    // DeskBot welcome sound
    startWav("/welcome.wav");
    // ===============================================

    drawEyesOpen();
}

void loop()
{
    
    updateAudio();
    if (currentMood == CURIOUS && millis() > curiousUntil)
    {
        currentMood = CALM;
        drawEyesOpen();
    }

    if (currentMood == CALM &&
    millis() - lastInteraction > 30000)
    {
        currentMood = SLEEPY;

        drawEyesOpen();

        startWav("/sleepy.wav");
    }

    bool currentTouch = digitalRead(touchPin);

    // ================= TOUCH =================

    if (currentTouch && !lastTouchState)
    {
        Serial.println("Touch detected!");

        lastInteraction = millis();

        curiousUntil = millis() + 5000;

    // If DeskBot was sleeping, play wake sound
        if (currentMood == SLEEPY)
        {
            currentMood = CURIOUS;

            drawEyesOpen();

            startWav("/wake.wav");
        }
        else
        {
        // Normal touch response
            //startWav("/touch.wav");

            currentMood = CURIOUS;

            drawEyesOpen();

        // Curious reaction
            startWav("/touch.wav");
        }
}

    // ==========================================

    lastTouchState = currentTouch;

    if (millis() < nextBehaviorTime)
        return;

    chooseBehavior();

    switch (currentBehavior)
    {
        case IDLE:
            lookTo(0);

    // Stay idle for a natural random period
            nextBehaviorTime = millis() + random(2500, 7000);

            break;

        case LOOK_LEFT:

            lookTo(-4);

            delay(random(250,500));

            lookTo(0);

            nextBehaviorTime =
                millis() + random(2000, 5000);

            break;

        case LOOK_RIGHT:

            lookTo(4);

            delay(random(250,500));

            lookTo(0);

            nextBehaviorTime =
                millis() + random(2000, 5000);

            break;

        case BLINK:

            drawEyesClosed();

            delay(random(80,140));

            drawEyesOpen();

            nextBehaviorTime =
                millis() + random(3000, 7000);

            break;

        case DOUBLE_BLINK:

            drawEyesClosed();

            delay(random(80,120));

            drawEyesOpen();

            delay(random(100,180));

            drawEyesClosed();

            delay(random(80,120));

            drawEyesOpen();

            nextBehaviorTime =
                millis() + random(5000, 9000);

            break;
    }
}