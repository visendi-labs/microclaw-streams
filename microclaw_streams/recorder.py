"""Audio recording and transcription via Whisper."""

import select
import sys
import termios
import time
import tty

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000

# VAD parameters
VAD_ENERGY_THRESHOLD = 0.01   # RMS threshold to detect speech
VAD_SILENCE_DURATION = 1.5    # seconds of silence before we consider speech ended
VAD_MIN_SPEECH_DURATION = 0.5 # minimum seconds of speech to count as an utterance


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


class OpenMicRecorder:
    """Continuous recording with energy-based VAD. Yields audio chunks when speech ends."""

    def __init__(self):
        self.frames = []
        self.is_speaking = False
        self.silence_start = None
        self.speech_start = None
        self._stop = False
        self._stream = None

    def stop(self):
        self._stop = True
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()

    def record(self):
        """Generator that yields numpy audio arrays when an utterance is detected."""
        self._stop = False
        self.frames = []
        self.is_speaking = False
        self.silence_start = None
        self.speech_start = None

        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32",
            blocksize=int(SAMPLE_RATE * 0.1),  # 100ms chunks
        )
        self._stream.start()

        try:
            while not self._stop:
                data, overflowed = self._stream.read(int(SAMPLE_RATE * 0.1))
                chunk = data.flatten()
                rms = np.sqrt(np.mean(chunk ** 2))
                now = time.monotonic()

                if rms > VAD_ENERGY_THRESHOLD:
                    if not self.is_speaking:
                        self.is_speaking = True
                        self.speech_start = now
                    self.silence_start = None
                    self.frames.append(chunk)
                else:
                    if self.is_speaking:
                        self.frames.append(chunk)
                        if self.silence_start is None:
                            self.silence_start = now
                        elif now - self.silence_start >= VAD_SILENCE_DURATION:
                            # Speech ended — check minimum duration
                            speech_duration = now - self.speech_start
                            if speech_duration >= VAD_MIN_SPEECH_DURATION:
                                audio = np.concatenate(self.frames)
                                self.frames = []
                                self.is_speaking = False
                                self.silence_start = None
                                self.speech_start = None
                                yield audio
                            else:
                                # Too short, discard
                                self.frames = []
                                self.is_speaking = False
                                self.silence_start = None
                                self.speech_start = None
        finally:
            self._stream.stop()
            self._stream.close()
            self._stream = None
