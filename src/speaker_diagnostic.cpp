#include <Arduino.h>
#include "driver/i2s.h"
#include <math.h>

// ============================================================================
// DeskBot Isolated Speaker & Amplifier Diagnostic Engine
// Hardware: ESP32-S3 -> I2S -> MAX98357A -> Speaker
// Supports both 4-Ohm and 8-Ohm speaker loads (zero impedance assumptions made)
// ============================================================================

#define I2S_PORT I2S_NUM_0
#define SAMPLE_RATE 16000
#define BUFFER_SAMPLES 256

// Default MAX98357A pin wiring:
// DIN  (Data Out from ESP32) = GPIO 15
// BCLK (Bit Clock)           = GPIO 16 (default)
// LRC  (Word Select / LRCLK) = GPIO 17 (default)
// Note: Pressing 'p' in serial console toggles BCLK and LRC (16 <-> 17)
int pin_dout = 15;
int pin_bclk = 16;
int pin_lrc  = 17;

enum DiagnosticMode {
    MODE_SILENCE,
    MODE_SINE_1KHZ,
    MODE_SWEEP,
    MODE_SPEECH_LIKE,
    MODE_AMP_COMPARISON
};

DiagnosticMode currentMode = MODE_SILENCE;
float currentAmplitude = 0.25f; // Conservative initial amplitude (25%)
float currentFrequency = 1000.0f;

// Phase accumulators for continuous smooth synthesis (zero pops / clicks)
double phase_main = 0.0;
double phase_f0 = 0.0;
double phase_f1 = 0.0;
double phase_f2 = 0.0;
double phase_env = 0.0;

// State tracking for automated sweeps and comparisons
unsigned long modeStartTime = 0;
int sweepStage = 0;
int ampCompStage = 0;

int16_t stereoBuffer[BUFFER_SAMPLES * 2]; // Interleaved L, R, L, R

void logDiagnosticHeader() {
    Serial.println();
    Serial.println("====================================================");
    Serial.println("[SPEAKER TEST]");
    Serial.println("Impedance assumption: NONE (MAX98357A supports 4-Ohm and 8-Ohm)");
    Serial.printf("Sample rate: %d Hz\n", SAMPLE_RATE);
    Serial.println("Bit depth: 16-bit");
    Serial.println("I2S format: I2S_COMM_FORMAT_STAND_I2S (Philips Standard)");
    Serial.println("Channels: Stereo (L+R duplicated, 32 BCLK cycles/frame)");
    Serial.printf("Pins: DOUT=GPIO %d, BCLK=GPIO %d, LRC=GPIO %d\n", pin_dout, pin_bclk, pin_lrc);
    Serial.printf("Amplitude: %d%% (Peak: %d / 32767)\n", (int)(currentAmplitude * 100 + 0.5f), (int)(currentAmplitude * 32767.0f));
    Serial.printf("Frequency: %.1f Hz\n", currentFrequency);
    Serial.println("====================================================");
}

void printMenu() {
    Serial.println();
    Serial.println("--- DESKBOT SPEAKER DIAGNOSTIC MENU ---");
    Serial.println(" [1] Test 1: Continuous 1 kHz Sine Wave (starts at 25%)");
    Serial.println("     [a] 25% Amplitude (Safe / Conservative)");
    Serial.println("     [b] 40% Amplitude");
    Serial.println("     [c] 60% Amplitude");
    Serial.println("     [d] 80% Amplitude");
    Serial.println(" [2] Test 2: Frequency Sweep (300Hz -> 500Hz -> 1kHz -> 2kHz -> 4kHz @ 25%)");
    Serial.println(" [3] Test 3: Speech-Like Multi-Tone Audio Pattern (150Hz + 600Hz + 1800Hz @ 25%)");
    Serial.println(" [4] Test 4: Low vs High Amplitude Comparison (25% -> 50% -> 75% for 3s each)");
    Serial.println(" [+] / [-] Adjust Amplitude by +/- 5%");
    Serial.println(" [p] Swap BCLK and LRC pins (toggle GPIO 16 <-> 17 at runtime)");
    Serial.println(" [s] or [0] Stop / Silence Output");
    Serial.println(" [h] Show this menu");
    Serial.println("---------------------------------------");
    Serial.printf("Current Status: Mode=%d, Amp=%d%%, Pins: DIN=%d, BCLK=%d, LRC=%d\n",
                  currentMode, (int)(currentAmplitude * 100 + 0.5f), pin_dout, pin_bclk, pin_lrc);
    Serial.println();
}

bool initI2S() {
    i2s_driver_uninstall(I2S_PORT);

    i2s_config_t i2s_config = {
        .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX),
        .sample_rate = SAMPLE_RATE,
        .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
        .channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT, // Stereo: 32 BCLK cycles per frame
        .communication_format = I2S_COMM_FORMAT_STAND_I2S,
        .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
        .dma_buf_count = 8,
        .dma_buf_len = BUFFER_SAMPLES,
        .use_apll = false,
        .tx_desc_auto_clear = true, // Clear DMA descriptors on underrun to prevent pops/buzzing
        .fixed_mclk = 0
    };

    i2s_pin_config_t pin_config = {
        .bck_io_num = pin_bclk,
        .ws_io_num = pin_lrc,
        .data_out_num = pin_dout,
        .data_in_num = I2S_PIN_NO_CHANGE
    };

    esp_err_t err = i2s_driver_install(I2S_PORT, &i2s_config, 0, NULL);
    if (err != ESP_OK) {
        Serial.printf("[ERROR] i2s_driver_install failed: 0x%x\n", err);
        return false;
    }

    err = i2s_set_pin(I2S_PORT, &pin_config);
    if (err != ESP_OK) {
        Serial.printf("[ERROR] i2s_set_pin failed: 0x%x\n", err);
        return false;
    }

    i2s_zero_dma_buffer(I2S_PORT);
    return true;
}

void swapPins() {
    int temp = pin_bclk;
    pin_bclk = pin_lrc;
    pin_lrc = temp;
    Serial.printf("[PINS] Swapped clock pins! Now: BCLK=GPIO %d, LRC=GPIO %d\n", pin_bclk, pin_lrc);
    if (initI2S()) {
        Serial.println("[PINS] I2S reinitialized successfully with new pin mapping.");
        logDiagnosticHeader();
    } else {
        Serial.println("[ERROR] Failed to reinitialize I2S after pin swap.");
    }
}

void setMode1(float amp) {
    currentMode = MODE_SINE_1KHZ;
    currentAmplitude = amp;
    currentFrequency = 1000.0f;
    phase_main = 0.0;
    Serial.printf("[TEST] 1kHz %d%%\n", (int)(currentAmplitude * 100 + 0.5f));
    logDiagnosticHeader();
}

void setMode2() {
    currentMode = MODE_SWEEP;
    currentAmplitude = 0.25f;
    sweepStage = 0;
    modeStartTime = millis();
    currentFrequency = 300.0f;
    phase_main = 0.0;
    Serial.println("[TEST] Starting Frequency Sweep (300Hz -> 500Hz -> 1kHz -> 2kHz -> 4kHz @ 25%)");
    Serial.println("[TEST] Sweep: 300 Hz (25%)");
    logDiagnosticHeader();
}

void setMode3() {
    currentMode = MODE_SPEECH_LIKE;
    currentAmplitude = 0.25f;
    phase_f0 = 0.0;
    phase_f1 = 0.0;
    phase_f2 = 0.0;
    phase_env = 0.0;
    Serial.println("[TEST] Speech-Like Multitone (F0=150Hz, F1=600Hz, F2=1800Hz @ 25%)");
    logDiagnosticHeader();
}

void setMode4() {
    currentMode = MODE_AMP_COMPARISON;
    ampCompStage = 0;
    currentAmplitude = 0.25f;
    currentFrequency = 1000.0f;
    modeStartTime = millis();
    phase_main = 0.0;
    Serial.println("[TEST] Starting Low vs High Amplitude Comparison");
    Serial.println("[TEST] 1kHz 25%");
    logDiagnosticHeader();
}

void setSilence() {
    currentMode = MODE_SILENCE;
    Serial.println("[TEST] Output Stopped (Mute / Silence)");
}

void handleSerial() {
    while (Serial.available()) {
        char c = (char)Serial.read();
        if (c == '\r' || c == '\n' || c == ' ') continue;

        switch (c) {
            case '1':
                setMode1(0.25f);
                break;
            case 'a':
            case 'A':
                setMode1(0.25f);
                break;
            case 'b':
            case 'B':
                setMode1(0.40f);
                break;
            case 'c':
            case 'C':
                setMode1(0.60f);
                break;
            case 'd':
            case 'D':
                setMode1(0.80f);
                break;
            case '2':
                setMode2();
                break;
            case '3':
                setMode3();
                break;
            case '4':
                setMode4();
                break;
            case '+':
                currentAmplitude = min(0.95f, currentAmplitude + 0.05f);
                Serial.printf("[AMPLITUDE] Increased to %d%% (Peak: %d)\n",
                              (int)(currentAmplitude * 100 + 0.5f), (int)(currentAmplitude * 32767.0f));
                break;
            case '-':
                currentAmplitude = max(0.05f, currentAmplitude - 0.05f);
                Serial.printf("[AMPLITUDE] Decreased to %d%% (Peak: %d)\n",
                              (int)(currentAmplitude * 100 + 0.5f), (int)(currentAmplitude * 32767.0f));
                break;
            case 'p':
            case 'P':
                swapPins();
                break;
            case 's':
            case 'S':
            case '0':
                setSilence();
                break;
            case 'h':
            case 'H':
            case '?':
                printMenu();
                break;
            default:
                Serial.printf("[CMD] Unknown key: '%c'. Send 'h' for menu.\n", c);
                break;
        }
    }
}

void generateAndSendAudio() {
    const double twoPi = 6.28318530717958647692;

    switch (currentMode) {
        case MODE_SILENCE:
            memset(stereoBuffer, 0, sizeof(stereoBuffer));
            break;

        case MODE_SINE_1KHZ: {
            double phaseStep = twoPi * currentFrequency / SAMPLE_RATE;
            float peakAmp = currentAmplitude * 32767.0f;

            for (int i = 0; i < BUFFER_SAMPLES; i++) {
                int16_t sample = (int16_t)(sin(phase_main) * peakAmp);
                stereoBuffer[i * 2]     = sample; // Left channel
                stereoBuffer[i * 2 + 1] = sample; // Right channel

                phase_main += phaseStep;
                if (phase_main >= twoPi) phase_main -= twoPi;
            }
            break;
        }

        case MODE_SWEEP: {
            unsigned long elapsed = millis() - modeStartTime;
            float targetFreq = 300.0f;

            if (elapsed < 2000) {
                targetFreq = 300.0f;
                if (sweepStage != 0) {
                    sweepStage = 0;
                    Serial.println("[TEST] Sweep: 300 Hz (25%)");
                }
            } else if (elapsed < 4000) {
                targetFreq = 500.0f;
                if (sweepStage != 1) {
                    sweepStage = 1;
                    Serial.println("[TEST] Sweep: 500 Hz (25%)");
                }
            } else if (elapsed < 6000) {
                targetFreq = 1000.0f;
                if (sweepStage != 2) {
                    sweepStage = 2;
                    Serial.println("[TEST] Sweep: 1000 Hz (25%)");
                }
            } else if (elapsed < 8000) {
                targetFreq = 2000.0f;
                if (sweepStage != 3) {
                    sweepStage = 3;
                    Serial.println("[TEST] Sweep: 2000 Hz (25%)");
                }
            } else if (elapsed < 10000) {
                targetFreq = 4000.0f;
                if (sweepStage != 4) {
                    sweepStage = 4;
                    Serial.println("[TEST] Sweep: 4000 Hz (25%)");
                }
            } else {
                Serial.println("[TEST] Frequency sweep complete! Returning to silence.");
                currentMode = MODE_SILENCE;
                memset(stereoBuffer, 0, sizeof(stereoBuffer));
                break;
            }

            currentFrequency = targetFreq;
            double phaseStep = twoPi * currentFrequency / SAMPLE_RATE;
            float peakAmp = currentAmplitude * 32767.0f;

            for (int i = 0; i < BUFFER_SAMPLES; i++) {
                int16_t sample = (int16_t)(sin(phase_main) * peakAmp);
                stereoBuffer[i * 2]     = sample;
                stereoBuffer[i * 2 + 1] = sample;

                phase_main += phaseStep;
                if (phase_main >= twoPi) phase_main -= twoPi;
            }
            break;
        }

        case MODE_SPEECH_LIKE: {
            // Syllabic speech cadence (3.5 Hz) and vowel formants (F0=150Hz, F1=600Hz, F2=1800Hz)
            double step_env = twoPi * 3.5 / SAMPLE_RATE;
            double step_f0  = twoPi * 150.0 / SAMPLE_RATE;
            double step_f1  = twoPi * 600.0 / SAMPLE_RATE;
            double step_f2  = twoPi * 1800.0 / SAMPLE_RATE;
            float peakAmp   = currentAmplitude * 32767.0f;

            for (int i = 0; i < BUFFER_SAMPLES; i++) {
                // Bell envelope
                double env = 0.5 * (1.0 + sin(phase_env));
                // Combined harmonic formants
                double comp = 0.50 * sin(phase_f0) + 0.30 * sin(phase_f1) + 0.20 * sin(phase_f2);
                int16_t sample = (int16_t)(comp * env * peakAmp);

                stereoBuffer[i * 2]     = sample;
                stereoBuffer[i * 2 + 1] = sample;

                phase_env += step_env;
                if (phase_env >= twoPi) phase_env -= twoPi;

                phase_f0 += step_f0;
                if (phase_f0 >= twoPi) phase_f0 -= twoPi;

                phase_f1 += step_f1;
                if (phase_f1 >= twoPi) phase_f1 -= twoPi;

                phase_f2 += step_f2;
                if (phase_f2 >= twoPi) phase_f2 -= twoPi;
            }
            break;
        }

        case MODE_AMP_COMPARISON: {
            unsigned long elapsed = millis() - modeStartTime;
            double phaseStep = twoPi * 1000.0 / SAMPLE_RATE;

            if (elapsed < 3000) {
                if (ampCompStage != 0) {
                    ampCompStage = 0;
                    currentAmplitude = 0.25f;
                    Serial.println("[TEST] 1kHz 25%");
                }
            } else if (elapsed < 6000) {
                if (ampCompStage != 1) {
                    ampCompStage = 1;
                    currentAmplitude = 0.50f;
                    Serial.println("[TEST] 1kHz 50%");
                }
            } else if (elapsed < 9000) {
                if (ampCompStage != 2) {
                    ampCompStage = 2;
                    currentAmplitude = 0.75f;
                    Serial.println("[TEST] 1kHz 75%");
                }
            } else {
                Serial.println("[TEST] Amplitude comparison finished! Output returning to silence.");
                Serial.println("[DIAGNOSTIC] Listen report: Did you observe clean audio, distortion, crackling, or silence?");
                currentMode = MODE_SILENCE;
                memset(stereoBuffer, 0, sizeof(stereoBuffer));
                break;
            }

            float peakAmp = currentAmplitude * 32767.0f;
            for (int i = 0; i < BUFFER_SAMPLES; i++) {
                int16_t sample = (int16_t)(sin(phase_main) * peakAmp);
                stereoBuffer[i * 2]     = sample;
                stereoBuffer[i * 2 + 1] = sample;

                phase_main += phaseStep;
                if (phase_main >= twoPi) phase_main -= twoPi;
            }
            break;
        }
    }

    size_t bytesWritten = 0;
    i2s_write(I2S_PORT, stereoBuffer, sizeof(stereoBuffer), &bytesWritten, portMAX_DELAY);
}

void setup() {
    Serial.begin(921600);
    delay(200);

    Serial.println("\n\nDeskBot Hardware Speaker Diagnostic Starting...");
    if (initI2S()) {
        Serial.println("I2S Audio Output Driver initialized successfully.");
    } else {
        Serial.println("[ERROR] I2S Driver failed to initialize!");
    }

    logDiagnosticHeader();
    printMenu();
}

void loop() {
    handleSerial();
    generateAndSendAudio();
}
