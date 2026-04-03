"""CLI entry point for MicroClaw Streams."""

import argparse
import atexit
import sys
import tty
import termios

import whisper
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from .recorder import record_push_to_talk, transcribe, SAMPLE_RATE, _restore_terminal
from .claude import send_to_claude, get_session_id, set_session_id
from .speaker import is_interrupted

console = Console()

MODEL_SIZE = "base"  # tiny, base, small, medium, large, turbo

MODE_MAP = {
    "a": ("auto-approve", "Edit,Write,Bash,Read"),
    "w": ("web search", "WebSearch,WebFetch"),
}


def _print_session_id():
    """Print the session ID on exit so the user can resume later."""
    sid = get_session_id()
    if sid:
        console.print(f"\n[bold cyan]🔑 Session ID:[/] {sid}")
        console.print(f"   [dim]Resume with:[/] [bold]microclaw-streams --resume {sid}[/]")


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
        console.print(f"[bold cyan]📂 Resuming session:[/] {args.resume}")

    atexit.register(_print_session_id)

    effort_levels = ["low", "medium", "high", "max"]
    effort_idx = effort_levels.index(args.effort)
    effort = args.effort

    console.print(f"[dim]Loading Whisper[/] [bold yellow]'{args.model}'[/] [dim]model...[/]")
    model = whisper.load_model(args.model)
    console.print(Panel("[bold green]Ready![/]", border_style="green", expand=False))
    print()

    while True:
        menu = Text()
        menu.append("ENTER", style="bold white")
        menu.append("=record  ", style="dim")
        menu.append("A", style="bold white")
        menu.append("=auto-approve  ", style="dim")
        menu.append("W", style="bold white")
        menu.append("=web search  ", style="dim")
        menu.append("T", style="bold white")
        menu.append("=type  ", style="dim")
        menu.append("E", style="bold white")
        menu.append(f"=effort ", style="dim")
        menu.append(f"[{effort}]", style="bold magenta")
        console.print(menu)

        key = _get_key()
        if key == "\x03":  # Ctrl+C
            raise KeyboardInterrupt
        if key == "e":
            effort_idx = (effort_idx + 1) % len(effort_levels)
            effort = effort_levels[effort_idx]
            console.print(f"[bold yellow]⚡ Effort set to:[/] [bold magenta]{effort}[/]")
            continue
        if key == "t":
            _restore_terminal()
            console.print("[bold cyan]💬 Type your message:[/] ", end="")
            text = input().strip()
            if text:
                send_to_claude(text, effort=effort)
                print()
            continue

        mode = MODE_MAP.get(key)
        if mode:
            label, allowed_tools = mode
            console.print(f"[bold red]🎙  Recording[/] [bold yellow]({label} ON)[/] [dim]... press ENTER to stop.[/]")
        else:
            allowed_tools = None
            console.print("[bold red]🎙  Recording[/] [dim]... press ENTER to stop.[/]")

        audio = record_push_to_talk()

        if audio is None or len(audio) < SAMPLE_RATE * 0.3:
            console.print("[dim]Too short, skipping.[/]\n")
            continue

        console.print("[bold cyan]Transcribing...[/]")
        text = transcribe(model, audio, fp16=args.fp16, language=args.language)

        if not text:
            console.print("[dim]No speech detected.[/]\n")
            continue

        send_to_claude(text, allowed_tools=allowed_tools, effort=effort)
        print()

        # If speech was interrupted by Enter, go straight into recording
        if is_interrupted():
            console.print("[bold red]🎙  Recording[/] [dim]... press ENTER to stop.[/]")
            audio = record_push_to_talk()
            if audio is not None and len(audio) >= SAMPLE_RATE * 0.3:
                console.print("[bold cyan]Transcribing...[/]")
                text = transcribe(model, audio, fp16=args.fp16, language=args.language)
                if text:
                    send_to_claude(text, effort=effort)
                    print()


def run():
    """Entry point wrapper with KeyboardInterrupt handling."""
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[bold]Bye![/]")
