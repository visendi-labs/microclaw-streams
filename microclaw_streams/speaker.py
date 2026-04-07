"""Voice output via macOS say command with multi-language support."""

import random
import re
import select
import subprocess
import sys

# Preferred voices per language, in priority order (first available wins).
LANG_VOICES = {
    "sv": ["Alva (Premium)", "Alva"],
    "en": ["Karen (Premium)", "Karen", "Samantha"],
    "de": ["Anna (Premium)", "Anna"],
    "fr": ["Amélie (Premium)", "Amélie"],
    "it": ["Alice (Premium)", "Alice"],
    "es": ["Marisol (Premium)", "Marisol", "Mónica"],
    "ja": ["Kyoko (Premium)", "Kyoko"],
    "ko": ["Yuna (Premium)", "Yuna"],
    "zh": ["Ting-Ting (Premium)", "Ting-Ting"],
    "nl": ["Ellen (Premium)", "Ellen"],
    "pt": ["Luciana (Premium)", "Luciana"],
}
DEFAULT_VOICES = ["Karen (Premium)", "Karen", "Samantha"]

_available_voices: set[str] | None = None


def _get_available_voices() -> set[str]:
    """Return set of voices installed on this system (cached)."""
    global _available_voices
    if _available_voices is None:
        try:
            out = subprocess.check_output(["say", "-v", "?"], text=True)
            _available_voices = {line.split(maxsplit=1)[0].strip()
                                 for line in out.splitlines() if line.strip()}
            # Also store full names (e.g. "Alva (Premium)") by re-parsing
            _available_voices = set()
            for line in out.splitlines():
                # Format: "Name  lang  # description"
                match = re.match(r'^(.+?)\s{2,}\w', line)
                if match:
                    _available_voices.add(match.group(1).strip())
        except Exception:
            _available_voices = set()
    return _available_voices


def _pick_voice(lang: str | None) -> str:
    """Pick the best available voice for a language."""
    candidates = LANG_VOICES.get(
        lang, DEFAULT_VOICES) if lang else DEFAULT_VOICES
    available = _get_available_voices()
    for voice in candidates:
        if voice in available:
            return voice
    # Last resort: return the last candidate and hope for the best
    return candidates[-1]


_interrupted = False


def split_sentences(text):
    """Split text into sentences."""
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return [p for p in parts if p]


def say(text, lang=None):
    """Speak text sentence by sentence; press Space to interrupt."""
    global _interrupted
    voice = _pick_voice(lang)
    for sentence in split_sentences(text):
        if _interrupted:
            break
        proc = subprocess.Popen(["say", "-v", voice, "-r", "190", sentence + " [[slnc 300]]"])
        while proc.poll() is None:
            if select.select([sys.stdin], [], [], 0.1)[0]:
                ch = sys.stdin.read(1)
                if ch in (" ", "\r", "\n"):
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
