"""Audio recording and transcription via Whisper."""

import sys
import termios

import numpy as np
import readchar
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
        stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", callback=callback)
        stream.start()
        while readchar.readkey() not in ("\r", "\n", readchar.key.ENTER):
            pass
        recording = False
        stream.stop()
        stream.close()
    except Exception as e:
        recording = False
        print(f"Recording error: {e}")
        return None

    if not frames:
        return None
    audio = np.concatenate(frames, axis=0).flatten()
    # Convert int16 (-32768..32767) to float32 (-1.0..1.0) for Whisper
    return audio.astype(np.float32) / 32768.0


def transcribe(model, audio, fp16=False):
    """Transcribe audio using Whisper model."""
    result = model.transcribe(audio, fp16=fp16)
    return result["text"].strip()
