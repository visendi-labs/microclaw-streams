"""Audio recording and transcription via Whisper."""

import select
import sys
import termios
import tty

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000


def _wait_for_enter():
    """Block until Enter is pressed, polling stdin in cbreak mode."""
    fd = sys.stdin.fileno()
    old_attrs = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while True:
            if select.select([sys.stdin], [], [], 0.1)[0]:
                ch = sys.stdin.read(1)
                if ch in ("\r", "\n"):
                    return
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)


def record_push_to_talk():
    """Record audio until Enter is pressed. Returns numpy array or None."""
    frames = []
    recording = True

    def callback(indata, frame_count, time_info, status):
        if recording:
            frames.append(indata.copy())

    try:
        stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=callback)
        stream.start()
        _wait_for_enter()
        recording = False
        stream.stop()
        stream.close()
    except Exception as e:
        recording = False
        print(f"Recording error: {e}")
        return None

    if not frames:
        return None
    return np.concatenate(frames, axis=0).flatten()


def transcribe(model, audio, fp16=False, language="en"):
    """Transcribe audio using Whisper model."""
    kwargs = dict(
        fp16=fp16,
        condition_on_previous_text=False,
        beam_size=1,
    )
    if language != "auto":
        kwargs["language"] = language
    result = model.transcribe(audio, **kwargs)
    return result["text"].strip()
