import argparse
import os
import time
from pathlib import Path

import serial
from openwakeword.model import Model


PORT = "COM4"
BAUD = 921600

SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2

# WebRTC/OpenWakeWord works with 16-bit PCM.
# openWakeWord processes 80 ms chunks particularly well.
CHUNK_SAMPLES = 1280
CHUNK_BYTES = CHUNK_SAMPLES * SAMPLE_WIDTH
DEFAULT_MODEL = os.getenv("DESKBOT_WAKE_MODEL", "hey_jarvis")
DEFAULT_THRESHOLD = float(os.getenv("DESKBOT_WAKE_THRESHOLD", "0.35"))


def model_label(model_reference: str) -> str:
    """Return the prediction key used by openWakeWord for a model reference."""

    if model_reference in {
        "alexa",
        "hey_jarvis",
        "hey_mycroft",
        "hey_rhasspy",
        "timer",
        "weather",
    }:
        return model_reference

    return Path(model_reference).stem


def create_model(model_reference: str) -> tuple[Model, str]:
    """Load one built-in or custom openWakeWord model."""

    path = Path(model_reference)

    if path.suffix and not path.is_file():
        raise FileNotFoundError(
            f"Wake-word model not found: {path}\n"
            "Set DESKBOT_WAKE_MODEL to a built-in model name or a valid .onnx/.tflite path."
        )

    return (
        Model(wakeword_models=[model_reference], inference_framework="onnx"),
        model_label(model_reference),
    )


def wait_for_stream_start(ser):
    """Wait for the ESP32 to confirm that streaming has started."""

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


def main():

    parser = argparse.ArgumentParser(
        description="Test a DeskBot wake-word model against the ESP32 stream."
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Built-in model name or path to a custom .onnx/.tflite model.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help="Activation confidence from 0 to 1.",
    )
    args = parser.parse_args()

    if not 0 < args.threshold <= 1:
        raise ValueError("--threshold must be greater than 0 and no more than 1.")

    print("Loading wake-word model...")

    model, label = create_model(args.model)

    print("Wake-word model loaded.")
    print()

    print("Connecting to DeskBot...")

    ser = serial.Serial(
        PORT,
        BAUD,
        timeout=1
    )

    print(f"Connected to {PORT}")

    time.sleep(0.5)

    print()
    print("Starting microphone stream...")

    ser.write(b"START_STREAM\n")
    ser.flush()

    try:

        wait_for_stream_start(ser)

        print()
        print("Microphone stream started.")
        print()
        print("Listening for wake word...")
        print(f'Model: {args.model}')
        print(f"Threshold: {args.threshold:.2f}")
        print()

        buffer = bytearray()

        while True:

            chunk = ser.read(4096)

            if not chunk:
                continue

            buffer.extend(chunk)

            while len(buffer) >= CHUNK_BYTES:

                audio_chunk = bytes(
                    buffer[:CHUNK_BYTES]
                )

                del buffer[:CHUNK_BYTES]

                # Convert raw PCM bytes to int16 samples.
                import numpy as np

                audio_array = np.frombuffer(
                    audio_chunk,
                    dtype=np.int16
                )

                prediction = model.predict(
                    audio_array
                )

                score = prediction.get(label, 0)

                if score >= args.threshold:

                    print()
                    print(
                        "🔥 WAKE WORD DETECTED!"
                    )

                    print(
                        f"Confidence: {score:.3f}"
                    )

                    print()

                    return

    finally:

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


if __name__ == "__main__":
    main()
