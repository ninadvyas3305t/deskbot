import serial
import wave
import time

PORT = "COM4"
BAUD = 921600

SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2

OUTPUT_FILE = "test_recording.wav"

# Maximum safety limit.
# The PC will normally stop the stream when we tell it to.
MAX_RECORD_SECONDS = 30

EXPECTED_MAX_BYTES = (
    SAMPLE_RATE
    * MAX_RECORD_SECONDS
    * SAMPLE_WIDTH
)


print("Connecting to DeskBot...")

ser = serial.Serial(
    PORT,
    BAUD,
    timeout=1
)

print(f"Connected to {PORT}")

# Give the ESP32 a moment after opening the serial port.
time.sleep(0.5)

print("Starting microphone stream...")

ser.write(b"START_STREAM\n")
ser.flush()

# ---------------------------------------------------------
# Wait for STREAM_START
# ---------------------------------------------------------

start_wait = time.time()

while True:

    if time.time() - start_wait > 10:
        ser.close()
        raise RuntimeError(
            "Timed out waiting for STREAM_START from ESP32."
        )

    line = ser.readline()

    if not line:
        continue

    text = line.decode(
        "ascii",
        errors="ignore"
    ).strip()

    if text:
        print(text)

    if text == "STREAM_START":
        break


print("Microphone stream started.")
print("Receiving audio...")

audio_data = bytearray()

start_receive = time.time()

while True:

    # Safety timeout.
    if time.time() - start_receive > MAX_RECORD_SECONDS:

        print(
            "\nMaximum recording time reached."
        )

        ser.write(b"STOP_STREAM\n")
        ser.flush()

        break

    chunk = ser.read(4096)

    if chunk:
        audio_data.extend(chunk)

    # Don't allow the buffer to grow beyond the safety limit.
    if len(audio_data) >= EXPECTED_MAX_BYTES:

        print(
            "\nMaximum audio buffer reached."
        )

        ser.write(b"STOP_STREAM\n")
        ser.flush()

        break


print(f"Received {len(audio_data)} bytes")

# ---------------------------------------------------------
# Save WAV
# ---------------------------------------------------------

ser.close()

with wave.open(OUTPUT_FILE, "wb") as wav:

    wav.setnchannels(CHANNELS)
    wav.setsampwidth(SAMPLE_WIDTH)
    wav.setframerate(SAMPLE_RATE)
    wav.writeframes(audio_data)

print()
print("Recording complete!")
print(f"Saved as: {OUTPUT_FILE}")