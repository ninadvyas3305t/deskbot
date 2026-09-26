import serial
import wave
import time
from collections import deque

import webrtcvad


PORT = "COM4"
BAUD = 921600

SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2

OUTPUT_FILE = "test_recording.wav"

# Safety limit so the program can never record forever.
MAX_RECORD_SECONDS = 30

# WebRTC VAD settings.
# 0 = least aggressive
# 3 = most aggressive
VAD_MODE = 2

# WebRTC supports 10, 20, or 30 ms frames.
FRAME_DURATION_MS = 30

FRAME_SIZE = int(
    SAMPLE_RATE * FRAME_DURATION_MS / 1000
) * SAMPLE_WIDTH

# Keep the audio immediately before speech detection.
PRE_ROLL_DURATION_MS = 300

PRE_ROLL_FRAMES = int(
    PRE_ROLL_DURATION_MS / FRAME_DURATION_MS
)

# How long silence must continue before recording stops.
SILENCE_DURATION_SECONDS = 1.0

SILENCE_FRAMES = int(
    SILENCE_DURATION_SECONDS * 1000 / FRAME_DURATION_MS
)


def wait_for_stream_start(ser):
    """Wait until the ESP32 confirms that audio streaming has started."""

    print("Waiting for STREAM_START...")

    start_wait = time.time()

    while True:

        if time.time() - start_wait > 10:
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
            return


def save_wav(audio_data):
    """Save raw PCM audio as a WAV file."""

    with wave.open(OUTPUT_FILE, "wb") as wav:

        wav.setnchannels(CHANNELS)
        wav.setsampwidth(SAMPLE_WIDTH)
        wav.setframerate(SAMPLE_RATE)

        wav.writeframes(audio_data)


def main():

    print("Connecting to DeskBot...")

    ser = serial.Serial(
        PORT,
        BAUD,
        timeout=1
    )

    print(f"Connected to {PORT}")

    # Give the ESP32 a moment after opening serial.
    time.sleep(0.5)

    print()
    print("Starting microphone stream...")

    ser.write(b"START_STREAM\n")
    ser.flush()

    audio_data = bytearray()

    try:

        wait_for_stream_start(ser)

        print()
        print("Microphone stream started.")
        print("Listening for speech...")
        print("Speak now.")

        vad = webrtcvad.Vad(VAD_MODE)

        speech_detected = False
        silence_frames = 0

        pre_roll = deque(
            maxlen=PRE_ROLL_FRAMES
        )

        start_time = time.time()

        buffer = bytearray()

        while True:

            # -------------------------------------------------
            # Safety timeout
            # -------------------------------------------------

            if time.time() - start_time > MAX_RECORD_SECONDS:

                print()
                print("Maximum recording time reached.")

                break

            # -------------------------------------------------
            # Receive serial audio
            # -------------------------------------------------

            chunk = ser.read(4096)

            if not chunk:
                continue

            buffer.extend(chunk)

            # -------------------------------------------------
            # Process complete VAD frames
            # -------------------------------------------------

            while len(buffer) >= FRAME_SIZE:

                frame = bytes(
                    buffer[:FRAME_SIZE]
                )

                del buffer[:FRAME_SIZE]

                is_speech = vad.is_speech(
                    frame,
                    SAMPLE_RATE
                )

                # -------------------------------------------------
                # Speech detected
                # -------------------------------------------------

                if is_speech:

                    if not speech_detected:

                        speech_detected = True

                        print()
                        print("Speech detected.")

                        # Add audio immediately before speech
                        # was detected so the beginning isn't clipped.
                        for previous_frame in pre_roll:
                            audio_data.extend(previous_frame)

                    audio_data.extend(frame)

                    silence_frames = 0

                # -------------------------------------------------
                # Silence detected
                # -------------------------------------------------

                else:

                    if speech_detected:

                        # Keep a small amount of trailing silence
                        # in the recording.
                        audio_data.extend(frame)

                        silence_frames += 1

                        if silence_frames >= SILENCE_FRAMES:

                            print()
                            print("End of speech detected.")

                            raise StopIteration

                    else:

                        # Keep the most recent audio while waiting
                        # for speech to begin.
                        pre_roll.append(frame)

    except StopIteration:

        pass

    finally:

        print()
        print("Stopping microphone stream...")

        try:

            ser.write(
                b"STOP_STREAM\n"
            )

            ser.flush()

        except serial.SerialException:

            pass

        time.sleep(0.1)

        ser.close()

    # ---------------------------------------------------------
    # Save recording
    # ---------------------------------------------------------

    if not audio_data:

        print()
        print("No speech was detected.")

        return

    print()
    print(
        f"Captured {len(audio_data)} bytes"
    )

    save_wav(audio_data)

    print()
    print("Recording complete!")
    print(
        f"Saved as: {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()