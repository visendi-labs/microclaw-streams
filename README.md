# MicroClaw Streams

Voice calls with Claude – talk it out. Voice in, voice out. Push-to-talk voice conversations powered by [Whisper](https://github.com/openai/whisper) and [Claude Code](https://docs.anthropic.com/en/docs/claude-code).

Whisper runs **entirely on your machine** — no audio is sent to the cloud. Only the transcribed text is sent to Claude.

## Setup

```bash
pip install microclaw-streams
```

Requires macOS (uses the built-in `say` command) and [Claude Code](https://docs.anthropic.com/en/docs/claude-code) to be installed and authenticated.

## Usage

```bash
microclaw-streams
microclaw-streams --model turbo
microclaw-streams --open-mic
microclaw-streams --resume <session-id>
microclaw-streams -l sv
```

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `-m`, `--model` | Whisper model size (`tiny`, `base`, `small`, `medium`, `large`, `turbo`) | `base` |
| `-l`, `--language` | Transcription language (e.g. `en`, `sv`, `de`) | `auto` |
| `-r`, `--resume` | Resume a previous Claude Code session by its session ID | — |
| `-o`, `--open-mic` | Start in open mic mode (auto-detect speech via VAD) | off |
| `--fp16` | Use half-precision inference (requires CUDA GPU) | off |

### Controls

| Key | Action |
|-----|--------|
| `Enter` | Start/stop recording |
| `A` | Toggle auto-approve (allows edits, writes, bash) |
| `T` | Type a message instead of speaking |
| `O` | Switch to open mic mode |
| `L` | Cycle transcription language |
| `Space` | Interrupt speech output |

## How it works

1. **Record** — Press Enter to start recording (push-to-talk), or use open mic mode for hands-free
2. **Transcribe** — Whisper transcribes your speech locally
3. **Respond** — Claude Code processes your message and streams a response
4. **Speak** — Voice output is spoken via macOS `say` command

The session is persistent — Claude remembers the full conversation context across all turns. No need to resume sessions manually.

### Open Mic Mode

Open mic mode uses energy-based voice activity detection (VAD) to automatically detect when you start and stop speaking. When a pause is detected (~1.5s of silence), the audio is transcribed and sent to Claude automatically. Start with `--open-mic` or press `O` during a session.

## Requirements

- macOS (uses `say` for text-to-speech)
- Python 3.10+
- Claude Code CLI

## Example Conversation 

```
Loading Whisper 'turbo' model locally (no audio leaves your machine)...
Connecting to Claude...
Ready!

ENTER=record  A=auto-approve [default]  T=type  O=open-mic  L=lang [auto]
Recording ... press ENTER to stop.
Transcribing...
You: Hey what's up how come we have a bunch of html files in this repo?

          Voice: Let me take a quick look at what HTML files are in the repo.
          [Glob **/*.html]
          [Glob result]
          index.html
          demo.html

          Voice: Actually, there are only two HTML files — an index.html and a demo.html. Not really a bunch. Want me to look into what they're for?
          [5.5s | 4 in | 123 out | 10254 cached | $0.0729]
```
