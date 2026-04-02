"""Audio recording and transcription via Whisper."""

import sys
import termios
import threading
import time

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000

# Voice activity detection settings
SILENCE_THRESHOLD = 0.015  # RMS level below which we consider silence
SILENCE_DURATION = 0.5     # Seconds of silence to trigger pre-transcription
SPEECH_MIN_DURATION = 0.5  # Minimum speech duration before detecting pauses


def _restore_terminal():
    """Restore terminal to normal (cooked) mode."""
    try:
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        old[3] = old[3] | termios.ECHO | termios.ICANON
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except Exception:
        pass


def record_push_to_talk(model=None):
    """Record audio until Enter is pressed. Pre-transcribes on silence detection.

    Args:
        model: Whisper model for background pre-transcription during pauses.
    """
    frames = []
    recording = True
    speech_detected = False
    silence_start = None
    recording_start = time.time()
    stop_event = threading.Event()

    # Pre-transcription state
    pre_transcribed = []  # list of transcribed text chunks
    last_pre_transcribe_idx = [0]  # frame index of last pre-transcription
    pre_transcribe_lock = threading.Lock()

    def callback(indata, frame_count, time_info, status):
        nonlocal speech_detected, silence_start
        if not recording:
            return
        frames.append(indata.copy())

        rms = np.sqrt(np.mean(indata ** 2))
        elapsed = time.time() - recording_start

        if rms > SILENCE_THRESHOLD:
            speech_detected = True
            silence_start = None
        elif speech_detected and elapsed > SPEECH_MIN_DURATION:
            if silence_start is None:
                silence_start = time.time()

    already_transcribing = [False]

    def pre_transcribe_worker():
        """Background worker that transcribes completed speech chunks."""
        nonlocal silence_start
        while not stop_event.is_set():
            time.sleep(0.1)
            if stop_event.is_set():
                break
            if (model and silence_start
                    and (time.time() - silence_start) >= SILENCE_DURATION
                    and len(frames) > last_pre_transcribe_idx[0]
                    and not already_transcribing[0]):
                already_transcribing[0] = True
                print("  🔇 silence detected, pre-transcribing...", flush=True)
                # Grab only frames up to current point, excluding trailing silence
                with pre_transcribe_lock:
                    chunk_frames = frames[last_pre_transcribe_idx[0]:]
                    last_pre_transcribe_idx[0] = len(frames)
                # Reset silence_start so we don't re-trigger on the same pause
                silence_start = None
                if stop_event.is_set():
                    already_transcribing[0] = False
                    break
                if chunk_frames:
                    # Trim trailing silence from chunk
                    audio = np.concatenate(chunk_frames, axis=0).flatten()
                    # Find last point where audio was above threshold
                    frame_size = int(SAMPLE_RATE * 0.05)  # 50ms frames
                    trim_idx = len(audio)
                    for i in range(len(audio) - frame_size, 0, -frame_size):
                        rms = np.sqrt(np.mean(audio[i:i+frame_size] ** 2))
                        if rms > SILENCE_THRESHOLD:
                            trim_idx = min(i + frame_size * 2, len(audio))
                            break
                    audio = audio[:trim_idx]
                    if len(audio) > SAMPLE_RATE * 0.3:
                        result = model.transcribe(audio, fp16=False)
                        text = result["text"].strip()
                        if text and not stop_event.is_set():
                            pre_transcribed.append(text)
                            print(f"  📝 pre-transcribed: {text}")
                already_transcribing[0] = False

    def wait_for_enter():
        """Wait for Enter key in a separate thread."""
        try:
            input()
            stop_event.set()
        except EOFError:
            pass

    try:
        _restore_terminal()
        stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=callback)
        stream.start()

        enter_thread = threading.Thread(target=wait_for_enter, daemon=True)
        enter_thread.start()

        if model:
            pre_thread = threading.Thread(target=pre_transcribe_worker, daemon=True)
            pre_thread.start()

        # Wait for Enter
        stop_event.wait()

        recording = False
        stream.stop()
        stream.close()
    except Exception as e:
        recording = False
        stop_event.set()
        print(f"Recording error: {e}")
        return None, []

    if not frames:
        return None, pre_transcribed

    # Return full audio and any pre-transcribed chunks
    remaining_frames = frames[last_pre_transcribe_idx[0]:]
    full_audio = np.concatenate(frames, axis=0).flatten()
    remaining_audio = np.concatenate(remaining_frames, axis=0).flatten() if remaining_frames else None

    return (full_audio, remaining_audio, pre_transcribed)


def transcribe(model, audio):
    """Transcribe audio using Whisper model."""
    result = model.transcribe(audio, fp16=False)
    return result["text"].strip()
