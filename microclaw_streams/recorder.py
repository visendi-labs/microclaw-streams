"""Audio recording and transcription via Whisper."""

import sys
import termios

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000


def _restore_terminal():
    """Restore terminal to normal (cooked) mode."""
    try:
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        old[3] = old[3] | termios.ECHO | termios.ICANON
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except Exception:
        pass


def record_push_to_talk():
    """Record audio until Enter is pressed. Returns numpy array or None."""
    frames = []
    recording = True

    def callback(indata, frame_count, time_info, status):
        if recording:
            frames.append(indata.copy())

    try:
        _restore_terminal()
        stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=callback)
        stream.start()
        input()  # Enter to stop
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


def transcribe(model, audio):
    """Transcribe audio using Whisper model."""
    result = model.transcribe(audio, fp16=True)
    return result["text"].strip()
