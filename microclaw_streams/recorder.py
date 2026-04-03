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
        stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=callback)
        stream.start()
        # Using readchar instead of input() to avoid terminal hang issues.
        # input() can block forever when terminal state is altered by rich/tty.setcbreak.
        # readchar manages its own terminal modes so it reliably detects Enter.
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
