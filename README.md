# MicroClaw Streams

Voice calls with Claude – talk it out. Voice in, voice out. Push-to-talk voice conversations powered by [Whisper](https://github.com/openai/whisper) and [Claude Code](https://docs.anthropic.com/en/docs/claude-code).

Whisper runs **entirely on your machine** — no audio is sent to the cloud. Only the transcribed text is sent to Claude.

Just three dependencies: `numpy`, `sounddevice`, and `openai-whisper`.

## Setup

```bash
pip install microclaw-streams
```

Requires macOS (uses the built-in `say` command) and [Claude Code](https://docs.anthropic.com/en/docs/claude-code) to be installed and authenticated.

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
| `-r`, `--resume` | Resume a previous Claude Code session by its session ID | — |
| `--fp16` | Use half-precision inference (requires CUDA GPU) | off |

Any **additional flags** you pass are forwarded directly to the `claude` CLI. For example:

```bash
microclaw-streams --max-turns 5 --permission-mode plan --model turbo
```

Here `--model turbo` is consumed by MicroClaw (Whisper model), while `--max-turns 5` and `--permission-mode plan` are passed through to Claude Code. See `claude --help` for all available options.

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

## Example Conversation 

```
Loading Whisper 'turbo' model locally (no audio leaves your machine)...
Ready!

ENTER=record  A=auto-approve  T=manually type input  E=effort [low]  L=lang [auto]
Recording ... press ENTER to stop.
Transcribing...
You: Hey what's up how come we have a bunch of html files in this repo?

          Voice: Let me take a quick look at what HTML files are in the repo.
          [Glob **/*.html]
          [Glob result]
          index.html
          demo.html

          Voice: Actually, there are only two HTML files — an **index.html** and a **demo.html**. Not really a bunch. Want me to look into what they're for?
          [5.5s | 4 in | 123 out | 10254 cached | $0.0729]


ENTER=record  A=auto-approve  T=manually type input  E=effort [low]  L=lang [auto]
Recording ... press ENTER to stop.
Transcribing...
You: Yup, for sure.

          Voice: Sure, let me check them out.
          [Read /home/user/index.html]
          [Read result]
          Claude requested permissions to read from /home/user/index.html, but you haven't granted it yet.

          [Read /home/user/demo.html]
          [Read result]
          Claude requested permissions to read from /home/user/demo.html, but you haven't granted it yet.

          Voice: Hmm, looks like I need permission to read those files. Could you grant me access?
          [6.4s | 4 in | 147 out | 20759 cached | $0.0158]


ENTER=record  A=auto-approve  T=manually type input  E=effort [low]  L=lang [auto]
Recording (auto-approve ON) ... press ENTER to stop.
Transcribing...
You: Here you go.
```