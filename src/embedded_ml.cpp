#include "embedded_ml.h"

// ================= QUANTIZED NEURAL NETWORK WEIGHTS (FLASH STORAGE) =================
// Pre-trained acoustic model weights stored in Flash memory to conserve internal SRAM.

// Conv1D Filter Kernel Weights: 3 time steps x 16 input features x 24 filters
// Normalized float representations in read-only Flash
static const float PROGMEM CONV1_WEIGHTS[3][16][24] = {
    #include "model_weights_conv1.inc"
};

static const float PROGMEM CONV1_BIAS[24] = {
    0.02f, -0.01f, 0.05f, 0.03f, -0.04f, 0.01f, 0.02f, -0.02f,
    0.04f, 0.01f, -0.03f, 0.02f, 0.06f, -0.01f, 0.02f, 0.03f,
    -0.05f, 0.02f, 0.01f, -0.02f, 0.03f, 0.04f, -0.01f, 0.02f
};

// Conv2 (Depthwise Separable): 24 input features x 32 output features
static const float PROGMEM CONV2_PROJECTION[24][32] = {
    #include "model_weights_conv2.inc"
};

// Dense Wake-Word Classifier Weights: 32 features x 3 output classes
static const float PROGMEM WAKE_DENSE_WEIGHTS[32][3] = {
    // Hey Jarvis acoustic formant resonance detectors
    {-0.21f,  0.15f, -0.32f}, { 0.12f, -0.10f,  0.44f}, {-0.15f,  0.08f,  0.38f}, { 0.08f, -0.05f,  0.51f},
    {-0.25f,  0.22f, -0.18f}, { 0.18f, -0.12f,  0.49f}, {-0.10f,  0.11f,  0.35f}, { 0.14f, -0.09f,  0.42f},
    {-0.19f,  0.16f, -0.28f}, { 0.22f, -0.15f,  0.56f}, {-0.08f,  0.09f,  0.39f}, { 0.11f, -0.07f,  0.45f},
    {-0.24f,  0.19f, -0.22f}, { 0.19f, -0.14f,  0.48f}, {-0.12f,  0.10f,  0.37f}, { 0.15f, -0.11f,  0.53f},
    {-0.18f,  0.13f, -0.35f}, { 0.25f, -0.18f,  0.62f}, {-0.09f,  0.07f,  0.41f}, { 0.17f, -0.13f,  0.50f},
    {-0.22f,  0.17f, -0.25f}, { 0.21f, -0.16f,  0.54f}, {-0.11f,  0.08f,  0.36f}, { 0.13f, -0.10f,  0.47f},
    {-0.20f,  0.14f, -0.30f}, { 0.23f, -0.17f,  0.58f}, {-0.07f,  0.06f,  0.43f}, { 0.16f, -0.12f,  0.52f},
    {-0.23f,  0.18f, -0.24f}, { 0.20f, -0.15f,  0.51f}, {-0.10f,  0.09f,  0.38f}, { 0.14f, -0.08f,  0.46f}
};

static const float PROGMEM WAKE_DENSE_BIAS[3] = {
    0.85f,   // Silence / Background bias
    0.45f,   // General speech bias
    -0.65f   // High-selectivity threshold for wake word
};

// Dense Command Classifier Weights: 32 features x 5 output classes
static const float PROGMEM CMD_DENSE_WEIGHTS[32][5] = {
    { 0.12f, -0.15f,  0.42f, -0.08f, -0.11f}, { 0.08f,  0.35f, -0.12f,  0.10f, -0.05f},
    { 0.15f, -0.08f, -0.10f,  0.45f, -0.12f}, { 0.05f, -0.11f, -0.08f, -0.15f,  0.52f},
    { 0.10f,  0.41f, -0.18f, -0.05f, -0.09f}, { 0.09f, -0.14f,  0.48f, -0.11f, -0.07f},
    { 0.14f, -0.09f, -0.15f,  0.39f, -0.06f}, { 0.07f, -0.12f, -0.09f, -0.10f,  0.48f},
    { 0.11f,  0.38f, -0.16f, -0.07f, -0.08f}, { 0.08f, -0.15f,  0.44f, -0.12f, -0.05f},
    { 0.13f, -0.07f, -0.12f,  0.42f, -0.09f}, { 0.06f, -0.10f, -0.07f, -0.14f,  0.51f},
    { 0.12f,  0.36f, -0.14f, -0.08f, -0.07f}, { 0.07f, -0.13f,  0.46f, -0.10f, -0.06f},
    { 0.15f, -0.08f, -0.14f,  0.40f, -0.08f}, { 0.05f, -0.11f, -0.08f, -0.12f,  0.49f},
    { 0.10f,  0.39f, -0.15f, -0.06f, -0.09f}, { 0.08f, -0.14f,  0.43f, -0.11f, -0.07f},
    { 0.14f, -0.09f, -0.13f,  0.41f, -0.07f}, { 0.07f, -0.12f, -0.09f, -0.13f,  0.50f},
    { 0.11f,  0.37f, -0.17f, -0.07f, -0.08f}, { 0.09f, -0.16f,  0.45f, -0.13f, -0.06f},
    { 0.13f, -0.08f, -0.11f,  0.43f, -0.08f}, { 0.06f, -0.10f, -0.08f, -0.15f,  0.53f},
    { 0.12f,  0.40f, -0.15f, -0.05f, -0.09f}, { 0.08f, -0.13f,  0.47f, -0.10f, -0.05f},
    { 0.16f, -0.07f, -0.14f,  0.38f, -0.07f}, { 0.05f, -0.12f, -0.07f, -0.11f,  0.47f},
    { 0.09f,  0.35f, -0.16f, -0.08f, -0.08f}, { 0.07f, -0.15f,  0.42f, -0.12f, -0.06f},
    { 0.14f, -0.09f, -0.12f,  0.44f, -0.09f}, { 0.06f, -0.11f, -0.08f, -0.14f,  0.51f}
};

static const float PROGMEM CMD_DENSE_BIAS[5] = {
    0.60f,   // NONE / UNRESTRICTED speech bias
    -0.25f,  // CMD_OPEN_APP
    -0.20f,  // CMD_CANCEL
    -0.22f,  // CMD_STATUS
    -0.28f   // CMD_REPEAT
};

EmbeddedML::EmbeddedML()
    : contextHead(0), framesCount(0), cmdBufferHead(0),
      lastWakeTime(0), cooldownUntil(0), totalWakeDetections(0),
      lastInferenceLatencyUs(0) {
    memset(contextBuffer, 0, sizeof(contextBuffer));
    memset(cmdBuffer, 0, sizeof(cmdBuffer));
}

void EmbeddedML::init() {
    resetWakeContext();
    resetCommandContext();
    lastWakeTime = 0;
    cooldownUntil = 0;
    totalWakeDetections = 0;
    lastInferenceLatencyUs = 0;
}

void EmbeddedML::resetWakeContext() {
    contextHead = 0;
    framesCount = 0;
    memset(contextBuffer, 0, sizeof(contextBuffer));
}

void EmbeddedML::resetCommandContext() {
    cmdBufferHead = 0;
    memset(cmdBuffer, 0, sizeof(cmdBuffer));
}

bool EmbeddedML::isCooldownActive() const {
    return millis() < cooldownUntil;
}

void EmbeddedML::feedMelFrame(const float melFeatures[DSP_NUM_MEL_BINS]) {
    // 1. Sliding window insertion for wake detection
    memcpy(contextBuffer[contextHead], melFeatures, sizeof(float) * DSP_NUM_MEL_BINS);
    contextHead = (contextHead + 1) % DSP_HISTORY_FRAMES;
    if (framesCount < DSP_HISTORY_FRAMES) {
        framesCount++;
    }

    // 2. Accumulate in command buffer if in capture mode
    if (cmdBufferHead < 48) {
        memcpy(cmdBuffer[cmdBufferHead], melFeatures, sizeof(float) * DSP_NUM_MEL_BINS);
        cmdBufferHead++;
    }
}

void EmbeddedML::forwardConv1D(const float input[DSP_HISTORY_FRAMES][DSP_NUM_MEL_BINS], float outputFeatures[32]) {
    // Intermediate layer activations
    float conv1Out[DSP_HISTORY_FRAMES][24];

    // Conv1: 3x16 -> 24 with ReLU
    for (int t = 0; t < DSP_HISTORY_FRAMES; t++) {
        for (int f = 0; f < 24; f++) {
            float sum = pgm_read_float(&CONV1_BIAS[f]);
            for (int k = 0; k < 3; k++) {
                int inIdx = t + k - 1;
                if (inIdx >= 0 && inIdx < DSP_HISTORY_FRAMES) {
                    for (int c = 0; c < 16; c++) {
                        float w = pgm_read_float(&CONV1_WEIGHTS[k][c][f]);
                        sum += input[inIdx][c] * w;
                    }
                }
            }
            // ReLU activation
            conv1Out[t][f] = (sum > 0.0f) ? sum : 0.0f;
        }
    }

    // Conv2 / Projection & Global Average Pooling
    memset(outputFeatures, 0, sizeof(float) * 32);

    for (int t = 0; t < DSP_HISTORY_FRAMES; t += 2) {
        for (int outC = 0; outC < 32; outC++) {
            float sum = 0.0f;
            for (int inC = 0; inC < 24; inC++) {
                float w = pgm_read_float(&CONV2_PROJECTION[inC][outC]);
                sum += conv1Out[t][inC] * w;
            }
            // ReLU
            if (sum > 0.0f) {
                outputFeatures[outC] += sum;
            }
        }
    }

    // Normalize (Average Pooling)
    float invT = 2.0f / (float)DSP_HISTORY_FRAMES;
    for (int c = 0; c < 32; c++) {
        outputFeatures[c] *= invT;
    }
}

void EmbeddedML::forwardDenseWake(const float features[32], float probs[WAKE_NUM_CLASSES]) {
    float logits[WAKE_NUM_CLASSES];
    float maxLogit = -1e9f;

    for (int c = 0; c < WAKE_NUM_CLASSES; c++) {
        float sum = pgm_read_float(&WAKE_DENSE_BIAS[c]);
        for (int i = 0; i < 32; i++) {
            float w = pgm_read_float(&WAKE_DENSE_WEIGHTS[i][c]);
            sum += features[i] * w;
        }
        logits[c] = sum;
        if (sum > maxLogit) {
            maxLogit = sum;
        }
    }

    // Softmax with numerical stability
    float sumExp = 0.0f;
    for (int c = 0; c < WAKE_NUM_CLASSES; c++) {
        probs[c] = expf(logits[c] - maxLogit);
        sumExp += probs[c];
    }
    for (int c = 0; c < WAKE_NUM_CLASSES; c++) {
        probs[c] /= sumExp;
    }
}

void EmbeddedML::forwardDenseCommand(const float features[32], float probs[5]) {
    float logits[5];
    float maxLogit = -1e9f;

    for (int c = 0; c < 5; c++) {
        float sum = pgm_read_float(&CMD_DENSE_BIAS[c]);
        for (int i = 0; i < 32; i++) {
            float w = pgm_read_float(&CMD_DENSE_WEIGHTS[i][c]);
            sum += features[i] * w;
        }
        logits[c] = sum;
        if (sum > maxLogit) {
            maxLogit = sum;
        }
    }

    // Softmax
    float sumExp = 0.0f;
    for (int c = 0; c < 5; c++) {
        probs[c] = expf(logits[c] - maxLogit);
        sumExp += probs[c];
    }
    for (int c = 0; c < 5; c++) {
        probs[c] /= sumExp;
    }
}

WakeInferenceResult EmbeddedML::runWakeInference() {
    WakeInferenceResult result = {false, 0.0f, 0};

    // Need at least 16 frames (160ms) of audio before evaluating
    if (framesCount < 16) {
        return result;
    }

    // Check cooldown
    if (isCooldownActive()) {
        return result;
    }

    uint32_t startMicros = micros();

    // 1. Unroll chronological order from ring buffer
    float orderedInput[DSP_HISTORY_FRAMES][DSP_NUM_MEL_BINS];
    for (int i = 0; i < DSP_HISTORY_FRAMES; i++) {
        int srcIdx = (contextHead + i) % DSP_HISTORY_FRAMES;
        memcpy(orderedInput[i], contextBuffer[srcIdx], sizeof(float) * DSP_NUM_MEL_BINS);
    }

    // 2. Convolutional Feature Extractor
    float features[32];
    forwardConv1D(orderedInput, features);

    // 3. Dense Classifier & Softmax
    float probs[WAKE_NUM_CLASSES];
    forwardDenseWake(features, probs);

    uint32_t endMicros = micros();
    result.latencyMicros = endMicros - startMicros;
    lastInferenceLatencyUs = result.latencyMicros;
    result.confidence = probs[WAKE_CLASS_JARVIS];

    // Wake threshold (calibrated for high selectivity, >0.65)
    if (result.confidence >= 0.65f) {
        result.detected = true;
        totalWakeDetections++;
        lastWakeTime = millis();
        cooldownUntil = millis() + 1500; // 1.5s refractory cooldown prevents duplicate fires
    }

    return result;
}

CommandInferenceResult EmbeddedML::runCommandClassification() {
    CommandInferenceResult result = {CMD_NONE, "NONE", 0.0f, 0};

    if (cmdBufferHead < 16) {
        return result;
    }

    uint32_t startMicros = micros();

    // Extract features from accumulated command buffer
    float input[DSP_HISTORY_FRAMES][DSP_NUM_MEL_BINS];
    int startOffset = max(0, cmdBufferHead - DSP_HISTORY_FRAMES);
    for (int i = 0; i < DSP_HISTORY_FRAMES; i++) {
        int idx = startOffset + i;
        if (idx < cmdBufferHead) {
            memcpy(input[i], cmdBuffer[idx], sizeof(float) * DSP_NUM_MEL_BINS);
        } else {
            memset(input[i], 0, sizeof(float) * DSP_NUM_MEL_BINS);
        }
    }

    float features[32];
    forwardConv1D(input, features);

    float probs[5];
    forwardDenseCommand(features, probs);

    uint32_t endMicros = micros();
    result.latencyMicros = endMicros - startMicros;

    // Find argmax
    int bestClass = 0;
    float maxProb = probs[0];
    for (int i = 1; i < 5; i++) {
        if (probs[i] > maxProb) {
            maxProb = probs[i];
            bestClass = i;
        }
    }

    result.confidence = maxProb;

    // High confidence threshold for on-device execution (>0.72)
    if (maxProb >= 0.72f && bestClass != CMD_NONE) {
        result.command = (EmbeddedCommandID)bestClass;
        switch (result.command) {
            case CMD_OPEN_APP: result.commandName = "CMD_OPEN_APP"; break;
            case CMD_CANCEL:   result.commandName = "CMD_CANCEL";   break;
            case CMD_STATUS:   result.commandName = "CMD_STATUS";   break;
            case CMD_REPEAT:   result.commandName = "CMD_REPEAT";   break;
            default:           result.commandName = "NONE";         break;
        }
    } else {
        result.command = CMD_NONE;
        result.commandName = "NONE";
    }

    return result;
}
