#include <Arduino.h>
#include "driver/i2s.h"

#define MIC_I2S_PORT I2S_NUM_1

#define MIC_SCK 4
#define MIC_WS  5
#define MIC_SD  6

#define SAMPLE_RATE 16000
#define RECORD_SECONDS 3

#define SAMPLES_PER_BUFFER 256

int32_t samples[SAMPLES_PER_BUFFER];

void setup()
{
    Serial.begin(921600);
    delay(1000);

    Serial.println();
    Serial.println("=== DeskBot Audio Capture Test ===");

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

    Serial.println("Installing microphone I2S...");

    if (i2s_driver_install(
            MIC_I2S_PORT,
            &i2s_config,
            0,
            NULL) != ESP_OK)
    {
        Serial.println("I2S INSTALL FAILED!");
        while (true)
            delay(1000);
    }

    if (i2s_set_pin(
            MIC_I2S_PORT,
            &pin_config) != ESP_OK)
    {
        Serial.println("I2S PIN SETUP FAILED!");
        while (true)
            delay(1000);
    }

    Serial.println("Microphone ready.");
    Serial.println("Waiting 2 seconds...");

    delay(2000);

    Serial.println("RECORDING_START");

    // Tell the PC exactly how many bytes are coming.
    uint32_t totalSamples =
        SAMPLE_RATE * RECORD_SECONDS;

    uint32_t samplesSent = 0;

    while (samplesSent < totalSamples)
    {
        size_t bytesRead = 0;

        i2s_read(
            MIC_I2S_PORT,
            samples,
            sizeof(samples),
            &bytesRead,
            portMAX_DELAY);

        int count = bytesRead / sizeof(int32_t);

        for (int i = 0;
             i < count && samplesSent < totalSamples;
             i++)
        {
            // Convert INMP441's 32-bit container
            // to signed 16-bit PCM.
            int16_t pcmSample = (int16_t)(samples[i] >> 16);

            Serial.write(
                (uint8_t *)&pcmSample,
                sizeof(pcmSample));

            samplesSent++;
        }
    }

    Serial.println();
    Serial.println("RECORDING_END");

    Serial.flush();

    Serial.println("Capture complete.");
}

void loop()
{
    delay(1000);
}