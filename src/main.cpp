#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64

Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

int eyeOffsetX = 0;
int eyeOffsetY = 0;
const int touchPin = 7;
bool lastTouchState = false;
unsigned long curiousUntil = 0;

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

void drawEyesOpen()
{
    display.clearDisplay();

    switch(currentMood)
    {
        case CALM:

            display.fillRoundRect(28 + eyeOffsetX, 20 + eyeOffsetY, 24, 24, 8, SSD1306_WHITE);
            display.fillRoundRect(76 + eyeOffsetX, 20 + eyeOffsetY, 24, 24, 8, SSD1306_WHITE);
            break;

        case CURIOUS:

            // Taller eyes
            display.fillRoundRect(28 + eyeOffsetX, 16 + eyeOffsetY, 24, 32, 8, SSD1306_WHITE);
            display.fillRoundRect(76 + eyeOffsetX, 16 + eyeOffsetY, 24, 32, 8, SSD1306_WHITE);
            break;

        case SLEEPY:

            // Half-open eyes
            display.fillRoundRect(28 + eyeOffsetX, 28 + eyeOffsetY, 24, 12, 6, SSD1306_WHITE);
            display.fillRoundRect(76 + eyeOffsetX, 28 + eyeOffsetY, 24, 12, 6, SSD1306_WHITE);
            break;
    }

    display.display();
}

void drawEyesClosed()
{
    display.clearDisplay();

    display.fillRoundRect(28 + eyeOffsetX, 30 + eyeOffsetY, 24, 4, 2, SSD1306_WHITE);
    display.fillRoundRect(76 + eyeOffsetX, 30 + eyeOffsetY, 24, 4, 2, SSD1306_WHITE);

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

    switch(currentMood)
    {
        case CALM:

            if (r < 50)
                currentBehavior = IDLE;
            else if (r < 70)
                currentBehavior = BLINK;
            else if (r < 85)
                currentBehavior = LOOK_LEFT;
            else if (r < 95)
                currentBehavior = LOOK_RIGHT;
            else
                currentBehavior = DOUBLE_BLINK;

            break;

        case CURIOUS:

            if (r < 20)
                currentBehavior = IDLE;
            else if (r < 35)
                currentBehavior = BLINK;
            else if (r < 60)
                currentBehavior = LOOK_LEFT;
            else if (r < 85)
                currentBehavior = LOOK_RIGHT;
            else
                currentBehavior = DOUBLE_BLINK;

            break;

        case SLEEPY:

            if (r < 70)
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

    switch(currentMood)
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

    randomSeed(micros());   // Initialize random number generator

    drawEyesOpen();
}

void loop()
{
    if (currentMood == CURIOUS && millis() > curiousUntil)
    {
        currentMood = CALM;
    
    }
    bool currentTouch = digitalRead(touchPin);

    if (currentTouch && !lastTouchState)
    {
        Serial.println("Touch detected!");

        currentMood = CURIOUS;

        curiousUntil = millis() + 5000;
    }

    lastTouchState = currentTouch;

    if (millis() < nextBehaviorTime)
        return;
    if (random(100) < 10)
    {
    chooseMood();
    }

    chooseBehavior();

    switch(currentBehavior)
    {
        case IDLE:

            lookTo(0);

            nextBehaviorTime = millis() + random(2000,5000);

            break;

        case LOOK_LEFT:

            lookTo(-4);
            delay(300);
            lookTo(0);

            nextBehaviorTime = millis() + random(1500,3000);

            break;

        case LOOK_RIGHT:

            lookTo(4);
            delay(300);
            lookTo(0);

            nextBehaviorTime = millis() + random(1500,3000);

            break;

        case BLINK:

            drawEyesClosed();
            delay(120);
            drawEyesOpen();

            nextBehaviorTime = millis() + random(2500,5000);

            break;

        case DOUBLE_BLINK:

            drawEyesClosed();
            delay(100);

            drawEyesOpen();
            delay(120);

            drawEyesClosed();
            delay(100);

            drawEyesOpen();

            nextBehaviorTime = millis() + random(4000,7000);

            break;
    }
}