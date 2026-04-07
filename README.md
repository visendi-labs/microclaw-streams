# MicroClaw Streams

Voice calls with Claude – talk it out. Voice in, voice out. Push-to-talk voice conversations powered by [Whisper](https://github.com/openai/whisper) and [Claude Code](https://docs.anthropic.com/en/docs/claude-code).

Whisper runs **entirely on your machine** — no audio is sent to the cloud. Only the transcribed text is sent to Claude.

## Setup

```bash
pip install -e .
```

Requires [Claude Code](https://docs.anthropic.com/en/docs/claude-code) to be installed and authenticated.

## Usage

```bash
microclaw-streams
microclaw-streams --model turbo
microclaw-streams --resume <session-id>
microclaw-streams -l sv -e high
```

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `-m`, `--model` | Whisper model size (`tiny`, `base`, `small`, `medium`, `large`, `turbo`) | `base` |
| `-l`, `--language` | Transcription language (e.g. `en`, `sv`, `de`) | `auto` |
| `-e`, `--effort` | Claude effort level (`low`, `medium`, `high`, `max`) | `low` |
| `-r`, `--resume` | Resume a previous session by ID | — |
| `--fp16` | Use half-precision inference (requires CUDA GPU) | off |

### Controls

| Key | Action |
|-----|--------|
| `Enter` | Start/stop recording |
| `A` | Record with auto-approve (allows edits, writes, bash) |
| `W` | Record with web search enabled |
| `T` | Type a message instead of speaking |
| `E` | Cycle effort level |
| `L` | Cycle transcription language |
| `Space` | Interrupt speech output |

## How it works

1. **Record** — Press Enter to start recording, press Enter again to stop
2. **Transcribe** — Whisper transcribes your speech locally
3. **Respond** — Claude Code processes your message and streams a response
4. **Speak** — Voice output is spoken via macOS `say` command

## Requirements

- macOS (uses `say` for text-to-speech)
- Python 3.10+
- Claude Code CLI
