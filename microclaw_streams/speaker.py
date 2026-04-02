"""Voice output via macOS say command with multi-language support."""

import random
import re
import select
import subprocess
import sys

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


def split_sentences(text):
    """Split text into sentences."""
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return [p for p in parts if p]


def say(text, lang=None):
    """Speak text sentence by sentence; press Space to interrupt."""
    global _interrupted
    voices = LANG_VOICES.get(lang, [DEFAULT_VOICE])
    for sentence in split_sentences(text):
        if _interrupted:
            break
        voice = random.choice(voices)
        rate = str(random.randint(200, 220))
        proc = subprocess.Popen(["say", "-v", voice, "-r", rate, sentence])
        while proc.poll() is None:
            if select.select([sys.stdin], [], [], 0.1)[0]:
                ch = sys.stdin.read(1)
                if ch == " ":
                    proc.terminate()
                    proc.wait()
                    _interrupted = True
                    print("(interrupted)")
                    break


def reset_interrupted():
    """Reset the interrupted flag."""
    global _interrupted
    _interrupted = False


def is_interrupted():
    """Check if speech was interrupted."""
    return _interrupted
