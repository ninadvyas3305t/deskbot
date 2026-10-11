#ifndef EMBEDDED_ML_H
#define EMBEDDED_ML_H

#include <Arduino.h>
#include <stdint.h>
#include "audio_dsp.h"

// Number of output classes for wake detection: [SILENCE, BACKGROUND, HEY_JARVIS]
#define WAKE_NUM_CLASSES 3
#define WAKE_CLASS_JARVIS 2

// Number of command classification classes:
// [NONE/OTHER, CMD_OPEN, CMD_CANCEL, CMD_STATUS, CMD_REPEAT]
enum EmbeddedCommandID {
    CMD_NONE = 0,
    CMD_OPEN_APP = 1,
    CMD_CANCEL = 2,
    CMD_STATUS = 3,
    CMD_REPEAT = 4
};

struct WakeInferenceResult {
    bool detected;
    float confidence;
    uint32_t latencyMicros;
};

struct CommandInferenceResult {
    EmbeddedCommandID command;
    const char* commandName;
    float confidence;
    uint32_t latencyMicros;
};

class EmbeddedML {
public:
    EmbeddedML();
    void init();

    // Ingest a new 16-channel Mel frame into temporal sliding context
    void feedMelFrame(const float melFeatures[DSP_NUM_MEL_BINS]);

    // Run wake-word neural network inference on current temporal context
    WakeInferenceResult runWakeInference();

    // Run command classification neural network inference on captured command buffer
    CommandInferenceResult runCommandClassification();

    // Reset temporal contexts
    void resetWakeContext();
    void resetCommandContext();

    // Check if cooldown period is active
    bool isCooldownActive() const;

    // Get statistics
    uint32_t getTotalWakeDetections() const { return totalWakeDetections; }
    uint32_t getLastInferenceLatency() const { return lastInferenceLatencyUs; }

private:
    // Temporal context buffer: 32 frames x 16 features
    float contextBuffer[DSP_HISTORY_FRAMES][DSP_NUM_MEL_BINS];
    int contextHead;
    int framesCount;

    // Command utterance accumulation buffer: up to 48 frames (480ms)
    float cmdBuffer[48][DSP_NUM_MEL_BINS];
    int cmdBufferHead;

    // Detection state
    uint32_t lastWakeTime;
    uint32_t cooldownUntil;
    uint32_t totalWakeDetections;
    uint32_t lastInferenceLatencyUs;

    // Forward pass neural network layers (executed on Xtensa LX7)
    void forwardConv1D(const float input[DSP_HISTORY_FRAMES][DSP_NUM_MEL_BINS], float outputFeatures[32]);
    void forwardDenseWake(const float features[32], float probs[WAKE_NUM_CLASSES]);
    void forwardDenseCommand(const float features[32], float probs[5]);
};

#endif // EMBEDDED_ML_H
