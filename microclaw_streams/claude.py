"""Claude Code integration — send messages and stream responses."""

import json
import re
import subprocess

from .speaker import say, reset_interrupted, is_interrupted

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


def get_session_id():
    """Return the current session ID."""
    return _session_id


def set_session_id(sid):
    """Set the session ID (e.g. when resuming)."""
    global _session_id
    _session_id = sid


def send_to_claude(text, allowed_tools=None):
    """Send a message to Claude via print mode, streaming the response."""
    global _session_id
    reset_interrupted()
    print(f"\n> {text}\n")

    cmd = ["claude", "-p", text, "--output-format", "stream-json", "--verbose",
           "--system-prompt", SYSTEM_PROMPT]
    if allowed_tools:
        cmd += ["--allowedTools", allowed_tools]
    if _session_id:
        cmd += ["--resume", _session_id]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    full_response = []
    spoken_so_far = 0
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
            if is_interrupted():
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
        if is_interrupted():
            break
        say(match.group(2), lang=match.group(1))

    return response
