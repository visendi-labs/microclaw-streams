"""CLI entry point for MicroClaw Streams."""

import argparse
import atexit
import sys
import tty
import termios

import whisper

from .recorder import record_push_to_talk, transcribe, SAMPLE_RATE, _restore_terminal
from .claude import send_to_claude, get_session_id, set_session_id
from .speaker import is_interrupted

MODEL_SIZE = "base"  # tiny, base, small, medium, large, turbo

MODE_MAP = {
    "a": ("auto-approve", "Edit,Write,Bash,Read,Glob,Grep,WebSearch,WebFetch"),
}


def _print_session_id():
    """Print the session ID on exit so the user can resume later."""
    sid = get_session_id()
    if sid:
        print(f"\nSession ID: {sid}")
        print(f"Resume with: microclaw-streams --resume {sid}")


def _get_key():
    """Read a single keypress without waiting for Enter."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def main():
    parser = argparse.ArgumentParser(
        prog="microclaw-streams",
        description="MicroClaw Streams — Push-to-talk voice conversations powered by Whisper (local) and Claude Code. "
                    "Whisper runs entirely on your machine — no audio is sent to the cloud.",
    )
    parser.add_argument("--resume", "-r", metavar="SESSION_ID",
                        help="Resume a previous conversation by session ID")
    parser.add_argument("--model", "-m", default=MODEL_SIZE,
                        choices=["tiny", "base", "small", "medium", "large", "turbo"],
                        help="Whisper model size (default: turbo)")
    parser.add_argument("--language", "-l", default="auto",
                        help="Language for Whisper transcription (default: auto). E.g. 'en', 'sv', 'de'")
    parser.add_argument("--fp16", action="store_true",
                        help="Use half-precision (fp16) for Whisper inference (requires CUDA GPU)")
    parser.add_argument("--effort", "-e", default="low",
                        choices=["low", "medium", "high", "max"],
                        help="Claude effort level (default: low)")
    args = parser.parse_args()

    if args.resume:
        set_session_id(args.resume)
        print(f"Resuming session: {args.resume}")

    atexit.register(_print_session_id)

    effort_levels = ["low", "medium", "high", "max"]
    effort_idx = effort_levels.index(args.effort)
    effort = args.effort

    language_options = ["auto", "en", "sv", "de", "fr", "es", "ja", "zh"]
    if args.language not in language_options:
        language_options.insert(1, args.language)
    lang_idx = language_options.index(args.language)
    language = args.language

    print(f"Loading Whisper '{args.model}' model locally (no audio leaves your machine)...")
    model = whisper.load_model(args.model)
    B = "\033[1m"
    R = "\033[0m"
    D = "\033[2m"

    print(f"{B}Ready!{R}\n")

    while True:
        print(f"{B}ENTER{R}=record  {B}A{R}=auto-approve  {B}T{R}=manually type input  {B}E{R}=effort [{B}{effort}{R}]  {B}L{R}=lang [{B}{language}{R}]  ")

        key = _get_key()
        if key == "\x03":  # Ctrl+C
            raise KeyboardInterrupt
        if key == "e":
            effort_idx = (effort_idx + 1) % len(effort_levels)
            effort = effort_levels[effort_idx]
            print(f"Effort set to: {B}{effort}{R}")
            continue
        if key == "l":
            lang_idx = (lang_idx + 1) % len(language_options)
            language = language_options[lang_idx]
            print(f"Language set to: {B}{language}{R}")
            continue
        if key == "t":
            _restore_terminal()
            print("Type your message: ", end="", flush=True)
            text = input().strip()
            if text:
                send_to_claude(text, effort=effort)
                print()
            continue

        mode = MODE_MAP.get(key)
        if mode:
            label, allowed_tools = mode
            print(f"{B}Recording{R} ({label} ON) ... press ENTER to stop.")
        else:
            allowed_tools = "WebSearch,WebFetch"
            print(f"{B}Recording{R} ... press ENTER to stop.")

        _restore_terminal()
        audio = record_push_to_talk()

        if audio is None or len(audio) < SAMPLE_RATE * 0.3:
            print("Too short, skipping.\n")
            continue

        print(f"{D}Transcribing...{R}")
        text = transcribe(model, audio, fp16=args.fp16, language=language)

        if not text:
            print(f"{D}No speech detected.{R}\n")
            continue

        send_to_claude(text, allowed_tools=allowed_tools, effort=effort)
        print()

        # If speech was interrupted by Enter, go straight into recording
        if is_interrupted():
            print(f"{B}Recording{R} ... press ENTER to stop.")
            _restore_terminal()
            audio = record_push_to_talk()
            if audio is not None and len(audio) >= SAMPLE_RATE * 0.3:
                print(f"{D}Transcribing...{R}")
                text = transcribe(model, audio, fp16=args.fp16, language=language)
                if text:
                    send_to_claude(text, effort=effort)
                    print()


def run():
    """Entry point wrapper with KeyboardInterrupt handling."""
    try:
        main()
    except KeyboardInterrupt:
        print("\nBye!")
