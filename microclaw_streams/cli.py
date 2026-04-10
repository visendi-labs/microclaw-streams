"""CLI entry point for MicroClaw Streams."""

import argparse
import asyncio
import sys
import tty
import termios
import threading

import whisper

from .recorder import record_push_to_talk, transcribe, OpenMicRecorder, SAMPLE_RATE
from .claude import (
    start_session, stop_session, send_to_claude,
    queue_message, drain_responses,
    set_permission_mode, interrupt_claude,
)
from .speaker import is_interrupted

MODEL_SIZE = "base"  # tiny, base, small, medium, large, turbo

AUTO_APPROVE_TOOLS = ["Edit", "Write", "Bash", "Read", "Glob", "Grep"]


def _get_key():
    """Read a single keypress without waiting for Enter."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


async def _run_open_mic(whisper_model, fp16, language):
    """Open mic mode: continuously listen, auto-transcribe on pauses, send to Claude."""
    B = "\033[1m"
    R = "\033[0m"
    D = "\033[2m"

    print(f"\n{B}Open mic active{R} — speak freely, pauses trigger transcription.")
    print(f"Press {B}Ctrl+C{R} to return to push-to-talk.\n")

    recorder = OpenMicRecorder()
    loop = asyncio.get_event_loop()
    text_ready = asyncio.Event()
    text_queue = []
    drain_task = None

    def vad_and_transcribe_thread():
        """VAD + transcription in one thread — async loop stays free for Claude I/O."""
        for audio in recorder.record():
            if len(audio) < SAMPLE_RATE * 0.3:
                continue
            text = transcribe(whisper_model, audio, fp16=fp16, language=language)
            if text:
                text_queue.append(text)
                loop.call_soon_threadsafe(text_ready.set)

    thread = threading.Thread(target=vad_and_transcribe_thread, daemon=True)
    thread.start()

    async def _drain_loop():
        """Continuously drain responses from Claude in the background."""
        while True:
            try:
                await drain_responses()
            except Exception:
                break

    try:
        while True:
            await text_ready.wait()
            text_ready.clear()

            while text_queue:
                text = text_queue.pop(0)
                # Fire off the message immediately — don't wait for response
                await queue_message(text)
                # Ensure a drain task is running to process responses
                if drain_task is None or drain_task.done():
                    drain_task = asyncio.create_task(_drain_loop())
                print()
    except KeyboardInterrupt:
        pass
    finally:
        recorder.stop()
        print(f"\n{D}Open mic stopped.{R}\n")


async def _run_push_to_talk(whisper_model, fp16, language, language_options, lang_idx):
    """Push-to-talk mode: press keys to record, type, or change settings."""
    B = "\033[1m"
    R = "\033[0m"
    D = "\033[2m"

    auto_approve = False

    while True:
        mode_str = "auto-approve ON" if auto_approve else "default"
        print(f"{B}ENTER{R}=record  {B}A{R}=auto-approve [{mode_str}]  {B}T{R}=type  {B}O{R}=open-mic  {B}L{R}=lang [{B}{language}{R}]  ")

        key = await asyncio.to_thread(_get_key)
        if key == "\x03":  # Ctrl+C
            raise KeyboardInterrupt
        if key == "l":
            lang_idx = (lang_idx + 1) % len(language_options)
            language = language_options[lang_idx]
            print(f"Language set to: {B}{language}{R}")
            continue
        if key == "t":
            print("Type your message: ", end="", flush=True)
            text = await asyncio.to_thread(input)
            text = text.strip()
            if text:
                await send_to_claude(text)
                print()
            continue
        if key == "a":
            auto_approve = not auto_approve
            mode = "bypassPermissions" if auto_approve else "default"
            await set_permission_mode(mode)
            print(f"Auto-approve: {B}{'ON' if auto_approve else 'OFF'}{R}")
            continue
        if key == "o":
            await _run_open_mic(whisper_model, fp16, language)
            continue

        if key in ("\r", "\n"):
            print(f"{B}Recording{R} ... press ENTER to stop.")
        else:
            continue

        audio = await asyncio.to_thread(record_push_to_talk)

        if audio is None or len(audio) < SAMPLE_RATE * 0.3:
            print("Too short, skipping.\n")
            continue

        print(f"{D}Transcribing...{R}")
        text = transcribe(whisper_model, audio, fp16=fp16, language=language)

        if not text:
            print(f"{D}No speech detected.{R}\n")
            continue

        await send_to_claude(text)
        print()

        # If speech was interrupted by Enter, go straight into recording
        if is_interrupted():
            await interrupt_claude()
            print(f"{B}Recording{R} ... press ENTER to stop.")
            audio = await asyncio.to_thread(record_push_to_talk)
            if audio is not None and len(audio) >= SAMPLE_RATE * 0.3:
                print(f"{D}Transcribing...{R}")
                text = transcribe(whisper_model, audio, fp16=fp16, language=language)
                if text:
                    await send_to_claude(text)
                    print()


async def main():
    parser = argparse.ArgumentParser(
        prog="microclaw-streams",
        description="MicroClaw Streams — Push-to-talk voice conversations powered by Whisper (local) and Claude Code. "
                    "Whisper runs entirely on your machine — no audio is sent to the cloud.",
    )
    parser.add_argument("--model", "-m", default=MODEL_SIZE,
                        choices=["tiny", "base", "small", "medium", "large", "turbo"],
                        help="Whisper model size (default: base)")
    parser.add_argument("--language", "-l", default="auto",
                        help="Language for Whisper transcription (default: auto). E.g. 'en', 'sv', 'de'")
    parser.add_argument("--fp16", action="store_true",
                        help="Use half-precision (fp16) for Whisper inference (requires CUDA GPU)")
    parser.add_argument("--resume", "-r", metavar="SESSION_ID",
                        help="Resume a previous conversation by session ID")
    parser.add_argument("--open-mic", "-o", action="store_true",
                        help="Start in open mic mode (auto-detect speech via VAD)")
    args = parser.parse_args()

    language_options = ["auto", "en", "sv", "de", "fr", "es", "ja", "zh"]
    if args.language not in language_options:
        language_options.insert(1, args.language)
    lang_idx = language_options.index(args.language)
    language = args.language

    print(f"Loading Whisper '{args.model}' model locally (no audio leaves your machine)...")
    whisper_model = whisper.load_model(args.model)
    B = "\033[1m"
    R = "\033[0m"

    if args.resume:
        print(f"Resuming session: {args.resume}")

    print("Connecting to Claude...")
    await start_session(allowed_tools=AUTO_APPROVE_TOOLS, resume=args.resume)
    print(f"{B}Ready!{R}\n")

    try:
        if args.open_mic:
            await _run_open_mic(whisper_model, args.fp16, language)
        else:
            await _run_push_to_talk(whisper_model, args.fp16, language, language_options, lang_idx)
    finally:
        await stop_session()


def run():
    """Entry point wrapper with KeyboardInterrupt handling."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBye!")
