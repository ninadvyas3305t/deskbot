#include <Arduino.h>

void setup()
{
    Serial.begin(115200);

    pinMode(LED_BUILTIN, OUTPUT);

    Serial.println();
    Serial.println("================================");
    Serial.println(" DeskBot Boot Successful!");
    Serial.println(" ESP32-S3 is alive!");
    Serial.println("================================");
}

void loop()
{
    digitalWrite(LED_BUILTIN, HIGH);
    delay(500);

    digitalWrite(LED_BUILTIN, LOW);
    delay(500);
}