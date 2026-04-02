#!/usr/bin/env python3
"""Push-to-talk voice conversation with Claude Code using local Whisper + macOS say."""

import argparse
import atexit
import re
import subprocess
import json
import select
import sys
import tty
import termios
import threading

import random

import numpy as np
import sounddevice as sd
import whisper

SAMPLE_RATE = 16000
MODEL_SIZE = "turbo"  # tiny, base, small, medium, large, turbo

VOICE_RE = re.compile(r'<v(?:\s+lang="([a-z]{2})")?>(.*?)</v>', re.DOTALL)

SYSTEM_PROMPT = (
    "You are in a live voice conversation. The user is speaking to you via speech-to-text. "
    "Keep responses concise and conversational. "
    "You MUST wrap the part of your response that should be spoken aloud in <v></v> tags. "
    "You can specify the language with a lang attribute, e.g. <v lang=\"sv\"> for Swedish, "
    "<v lang=\"en\"> for English, <v lang=\"de\"> for German, etc. Use the ISO 639-1 two-letter code. "
    "Default is English if no lang attribute is given. Match the language to whatever the user is speaking. "
    "Put code, file paths, technical details, and anything not suitable for speech outside the tags. "
    "You are free to output any other content (code, explanations, etc.) outside of <v> tags — "
    "it will be displayed to the user in the terminal but not spoken aloud. "
    "You MUST ALWAYS include a <v> section in every response. Never omit it.\n"
    "IMPORTANT: Always prioritize being interactive and responsive. Give a quick spoken acknowledgment "
    "or summary first (in <v> tags) before doing any heavy thinking, research, or tool calls. "
    "If a task takes multiple steps, provide brief spoken updates along the way so the user is never "
    "left waiting in silence.\n"
    "When sharing plans, documents, code, or any detailed content, keep the <v> part short — "
    "just say something like 'Here, take a look at this plan' or 'Check out the output below.' "
    "Then put the actual plan, document, or detailed content OUTSIDE the <v> tags so it appears "
    "in the terminal as readable text rather than being spoken aloud. "
    "IMPORTANT: When you write a plan to a file (e.g. via plan mode), you MUST also include the plan "
    "content directly in your response text outside the <v> tags, because the user can only see "
    "your response output in the terminal — they cannot see files you write to separately.\n"
    "SPEECH NATURALNESS: The text inside <v> tags is spoken aloud using macOS `say`. "
    "To make your speech sound more natural, you are encouraged to embed these inline commands "
    "directly in your <v> text:\n"
    "- [[rate N]] — change speech rate mid-sentence (e.g. [[rate 230]])\n"
    "- [[pitch N]] — adjust pitch (default ~45, range 30-60, e.g. [[pitch 48]] for slightly higher)\n"
    "- [[slnc N]] — insert a pause of N milliseconds (e.g. [[slnc 150]] for a natural breath pause between clauses)\n"
    "- [[emph +]] — emphasize the next word\n"
    "Use these sparingly and naturally — add slight pauses between clauses, "
    "emphasize key words, and vary pitch subtly to avoid sounding robotic."
)

_session_id = None


def print_session_id():
    """Print the session ID on exit so the user can resume later."""
    if _session_id:
        print(f"\n🔑 Session ID: {_session_id}")
        print(f"   Resume with: python voice-claude.py --resume {_session_id}")


def get_key():
    """Read a single keypress without waiting for Enter."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


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
    result = model.transcribe(audio, fp16=False)
    return result["text"].strip()


def split_sentences(text):
    """Split text into sentences."""
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return [p for p in parts if p]


LANG_VOICES = {
    "sv": ["Alva (Premium)"],
    "en": ["Karen (Premium)"],
    "de": ["Anna"],
    "fr": ["Amélie"],
    "it": ["Alice"],
    "es": ["Marisol (Premium)"],
    "ja": ["Kyoko"],
    "ko": ["Yuna"],
    "zh": ["Ting-Ting"],
    "nl": ["Ellen"],
    "pt": ["Luciana"],
}
DEFAULT_VOICE = "Karen (Premium)"

_interrupted = False


def say(text, lang=None):
    """Speak text sentence by sentence; press Enter to interrupt."""
    global _interrupted
    voices = LANG_VOICES.get(lang, [DEFAULT_VOICE])
    for sentence in split_sentences(text):
        if _interrupted:
            break
        voice = random.choice(voices)
        rate = str(random.randint(200, 220))
        proc = subprocess.Popen(["say", "-v", voice, "-r", rate, sentence])
        while proc.poll() is None:
            # Check if Space was pressed (non-blocking)
            if select.select([sys.stdin], [], [], 0.1)[0]:
                ch = sys.stdin.read(1)
                if ch == " ":
                    proc.terminate()
                    proc.wait()
                    _interrupted = True
                    print("(interrupted)")
                    break


def send_to_claude(text, allowed_tools=None):
    """Send a message to Claude via print mode, using session_id for conversation continuity."""
    global _session_id, _interrupted
    _interrupted = False
    print(f"\n> {text}\n")

    cmd = ["claude", "-p", text, "--output-format", "stream-json", "--verbose",
           "--system-prompt", SYSTEM_PROMPT]
    if allowed_tools:
        cmd += ["--allowedTools", allowed_tools]
    if _session_id:
        cmd += ["--resume", _session_id]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    full_response = []
    spoken_so_far = 0  # track how much of the accumulated text we've already spoken
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        # Capture session_id from init event
        if event.get("type") == "system" and event.get("subtype") == "init":
            _session_id = event.get("session_id")
        elif event.get("type") == "assistant" and "message" in event:
            for block in event["message"].get("content", []):
                if block.get("type") == "text":
                    print(block["text"], flush=True)
                    full_response.append(block["text"])
        elif event.get("type") == "result" and "result" in event:
            if not full_response:
                print(event["result"], flush=True)
                full_response.append(event["result"])

        # Check for complete <v> tags in new content and speak incrementally
        accumulated = "".join(full_response)
        unseen = accumulated[spoken_so_far:]
        for match in VOICE_RE.finditer(unseen):
            if _interrupted:
                break
            say(match.group(2), lang=match.group(1))
        # Advance spoken_so_far to end of last complete </v> tag
        last_close = unseen.rfind("</v>")
        if last_close != -1:
            spoken_so_far += last_close + len("</v>")

    proc.wait()
    response = "".join(full_response)
    print()

    # Speak any remaining v tags that arrived after the last check
    remaining = response[spoken_so_far:]
    for match in VOICE_RE.finditer(remaining):
        if _interrupted:
            break
        say(match.group(2), lang=match.group(1))

    return response


def main():
    global _session_id
    parser = argparse.ArgumentParser(description="Voice conversation with Claude Code")
    parser.add_argument("--resume", "-r", metavar="SESSION_ID",
                        help="Resume a previous conversation by session ID")
    args = parser.parse_args()

    if args.resume:
        _session_id = args.resume
        print(f"📂 Resuming session: {_session_id}")

    atexit.register(print_session_id)

    print(f"Loading Whisper '{MODEL_SIZE}' model...")
    model = whisper.load_model(MODEL_SIZE)
    print("Ready!\n")

    while True:
        print("Press: ENTER=record  A=auto-approve  W=web search  (Ctrl+C to quit)")
        key = get_key()
        if key == "\x03":  # Ctrl+C
            raise KeyboardInterrupt

        MODE_MAP = {
            "a": ("auto-approve", "Edit,Write,Bash,Read"),
            "w": ("web search", "WebSearch,WebFetch"),
        }

        mode = MODE_MAP.get(key)
        if mode:
            label, allowed_tools = mode
            print(f"🎙  Recording ({label} ON)... press ENTER to stop.")
        else:
            allowed_tools = None
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

        send_to_claude(text, allowed_tools=allowed_tools)
        print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBye!")
