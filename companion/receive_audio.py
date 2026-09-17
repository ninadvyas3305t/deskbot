import serial
import wave

PORT = "COM4"
BAUD = 921600

SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16-bit PCM

RECORD_SECONDS = 3
OUTPUT_FILE = "test_recording.wav"

EXPECTED_BYTES = (
    SAMPLE_RATE
    * RECORD_SECONDS
    * SAMPLE_WIDTH
)

print("Connecting to DeskBot...")

ser = serial.Serial(
    PORT,
    BAUD,
    timeout=2
)

print(f"Connected to {PORT}")
print("Waiting for recording...")

# Wait for the ESP32 to announce the start.
while True:
    line = ser.readline()

    if not line:
        continue

    text = line.decode(
        "ascii",
        errors="ignore"
    ).strip()

    print(text)

    if text == "RECORDING_START":
        break

print("🎤 Recording received from DeskBot...")
print(f"Expected audio: {EXPECTED_BYTES} bytes")

audio_data = bytearray()

while len(audio_data) < EXPECTED_BYTES:

    remaining = EXPECTED_BYTES - len(audio_data)

    chunk = ser.read(
        min(4096, remaining)
    )

    if chunk:
        audio_data.extend(chunk)

print(f"Received {len(audio_data)} bytes")

ser.close()

# Create WAV file.
with wave.open(
    OUTPUT_FILE,
    "wb"
) as wav:

    wav.setnchannels(CHANNELS)
    wav.setsampwidth(SAMPLE_WIDTH)
    wav.setframerate(SAMPLE_RATE)
    wav.writeframes(audio_data)

print()
print("✅ Audio capture complete!")
print(f"Saved as: {OUTPUT_FILE}")