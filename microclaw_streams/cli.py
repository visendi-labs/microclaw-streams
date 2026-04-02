"""CLI entry point for MicroClaw Streams."""

import argparse
import atexit
import sys
import tty
import termios

import whisper

from .recorder import record_push_to_talk, transcribe, SAMPLE_RATE
from .claude import send_to_claude, get_session_id, set_session_id

MODEL_SIZE = "turbo"  # tiny, base, small, medium, large, turbo

MODE_MAP = {
    "a": ("auto-approve", "Edit,Write,Bash,Read"),
    "w": ("web search", "WebSearch,WebFetch"),
}


def _print_session_id():
    """Print the session ID on exit so the user can resume later."""
    sid = get_session_id()
    if sid:
        print(f"\n🔑 Session ID: {sid}")
        print(f"   Resume with: microclaw-streams --resume {sid}")


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
        description="MicroClaw Streams — Push-to-talk voice conversations powered by Whisper and Claude Code",
    )
    parser.add_argument("--resume", "-r", metavar="SESSION_ID",
                        help="Resume a previous conversation by session ID")
    parser.add_argument("--model", "-m", default=MODEL_SIZE,
                        choices=["tiny", "base", "small", "medium", "large", "turbo"],
                        help="Whisper model size (default: turbo)")
    parser.add_argument("--effort", "-e", default="low",
                        choices=["low", "medium", "high", "max"],
                        help="Claude effort level (default: low)")
    args = parser.parse_args()

    if args.resume:
        set_session_id(args.resume)
        print(f"📂 Resuming session: {args.resume}")

    atexit.register(_print_session_id)

    effort_levels = ["low", "medium", "high", "max"]
    effort_idx = effort_levels.index(args.effort)
    effort = args.effort

    print(f"Loading Whisper '{args.model}' model...")
    model = whisper.load_model(args.model)
    print("Ready!\n")

    while True:
        print(f"Press: ENTER=record  A=auto-approve  W=web search  E=effort [{effort}]  (Ctrl+C to quit)")
        key = _get_key()
        if key == "\x03":  # Ctrl+C
            raise KeyboardInterrupt
        if key == "e":
            effort_idx = (effort_idx + 1) % len(effort_levels)
            effort = effort_levels[effort_idx]
            print(f"⚡ Effort set to: {effort}")
            continue

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

        send_to_claude(text, allowed_tools=allowed_tools, effort=effort)
        print()


def run():
    """Entry point wrapper with KeyboardInterrupt handling."""
    try:
        main()
    except KeyboardInterrupt:
        print("\nBye!")
