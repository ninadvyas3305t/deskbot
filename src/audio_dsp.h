#ifndef AUDIO_DSP_H
#define AUDIO_DSP_H

#include <Arduino.h>
#include <stdint.h>
#include <math.h>

// Audio DSP constants for 16 kHz audio
#define DSP_SAMPLE_RATE 16000
#define DSP_FRAME_LEN   320   // 20 ms window
#define DSP_FRAME_STEP  160   // 10 ms step (50% overlap)
#define DSP_NUM_MEL_BINS 16   // 16 Mel filterbank channels
#define DSP_HISTORY_FRAMES 32 // 32 frames = 320 ms temporal context

class AudioDSP {
public:
    AudioDSP();
    void init();

    // Process a chunk of 16-bit PCM samples and extract Mel filterbank features
    // Returns true when a new 20ms frame has been computed
    bool processSample(int16_t sample, float melFeaturesOut[DSP_NUM_MEL_BINS]);

    // Feed buffer of samples
    int processBuffer(const int16_t* samples, int count, float featuresBuffer[][DSP_NUM_MEL_BINS], int maxFrames);

    // Get current energy/volume level (0.0 to 1.0)
    float getCurrentRMS() const { return currentRms; }

    // Reset feature extractor state
    void reset();

private:
    int16_t sampleWindow[DSP_FRAME_LEN];
    int sampleWindowIndex;
    int16_t prevSample; // For pre-emphasis filter
    float currentRms;

    // Precomputed Hamming window
    float hammingWindow[DSP_FRAME_LEN];

    // Simple fixed Mel-scale filterbank center frequencies and widths
    void computeLogMel(const float* windowedSamples, float melOut[DSP_NUM_MEL_BINS]);
};

#endif // AUDIO_DSP_H
