#!/usr/bin/env python3
"""Push-to-talk voice conversation with Claude Code using local Whisper + macOS say."""

import subprocess
import json

import numpy as np
import sounddevice as sd
import whisper

SAMPLE_RATE = 16000
MODEL_SIZE = "turbo"  # tiny, base, small, medium, large, turbo


def record_push_to_talk():
    frames = []
    recording = True

    def callback(indata, frame_count, time_info, status):
        if recording:
            frames.append(indata.copy())

    stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=callback)
    stream.start()
    input()
    recording = False
    stream.stop()
    stream.close()

    if not frames:
        return None
    return np.concatenate(frames, axis=0).flatten()


def transcribe(model, audio):
    result = model.transcribe(audio, fp16=False)
    return result["text"].strip()


def say(text):
    subprocess.run(["say", "-v", "Samantha", "-r", "210", text])


def send_to_claude(text):
    print(f"\n> {text}\n")

    proc = subprocess.run(
        ["claude", "-p", text, "--output-format", "json", "--effort", "low"],
        capture_output=True, text=True,
    )

    try:
        response = json.loads(proc.stdout)["result"]
    except (json.JSONDecodeError, KeyError):
        response = proc.stdout.strip()

    print(response)
    say(response)
    return response


def main():
    print(f"Loading Whisper '{MODEL_SIZE}' model...")
    model = whisper.load_model(MODEL_SIZE)
    print("Ready!\n")

    while True:
        print("Press ENTER to start recording (Ctrl+C to quit)...")
        input()
        print("🎙  Recording... press ENTER to stop.")

        audio = record_push_to_talk()

        if audio is None or len(audio) < SAMPLE_RATE * 0.3:
            print("Too short, skipping.\n")
            continue

        print("Transcribing...")
        text = transcribe(model, audio)

        if not text:
            print("No speech detected.\n")
            continue

        send_to_claude(text)
        print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBye!")
