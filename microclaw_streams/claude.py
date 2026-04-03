"""Claude Code integration — send messages and stream responses."""

import json
import re
import subprocess

from .speaker import say, reset_interrupted, is_interrupted

VOICE_RE = re.compile(r'<v(?:\s+lang="([a-z]{2})")?>(.*?)</v>', re.DOTALL)

SYSTEM_PROMPT = (
    "You are in a live voice conversation. The user is speaking to you via speech-to-text. "
    "Keep responses concise and conversational. "
    "Wrap spoken text in <v></v> tags. Use a lang attribute for non-English, e.g. <v lang=\"sv\">. "
    "Match the user's language. Default is English.\n\n"
    "CRITICAL: Your response MUST start with a <v> tag IMMEDIATELY — before any thinking, "
    "code, tool calls, or text output. The user is waiting to hear you speak. "
    "Give a quick spoken acknowledgment first (e.g. 'Sure, let me look into that' or "
    "'Good question, here's what I think'), then continue with any additional work. "
    "You can add more <v> tags later in your response if needed.\n\n"
    "Content outside <v> tags is shown in the terminal but not spoken. "
    "Always include at least one <v> section. Be responsive — never leave the user in silence.\n"
    "For plans, documents, or code: keep the first <v> short (e.g. 'Here, take a look'), "
    "put details outside <v> tags, then optionally add another <v> to summarize.\n"
    "It is recommended to output information outside <v> tags so the user can see what's "
    "happening in the terminal (e.g. summaries of changes, file paths, key decisions). "
    "This way the user stays informed even when the spoken response is kept brief."
)

_session_id = None


def get_session_id():
    """Return the current session ID."""
    return _session_id


def set_session_id(sid):
    """Set the session ID (e.g. when resuming)."""
    global _session_id
    _session_id = sid


def send_to_claude(text, allowed_tools=None, effort="low"):
    """Send a message to Claude via print mode, streaming the response."""
    global _session_id
    reset_interrupted()
    B = "\033[1m"
    R = "\033[0m"
    D = "\033[2m"
    print(f"{B}You:{R} {text}\n")

    cmd = ["claude", "-p", text, "--output-format", "stream-json", "--verbose",
           "--effort", effort, "--system-prompt", SYSTEM_PROMPT]
    if allowed_tools:
        cmd += ["--allowedTools", allowed_tools]
    if _session_id:
        cmd += ["--resume", _session_id]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    full_response = []
    result_stats = {}
    _pending_tools = {}
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
        elif event.get("type") == "user" and "message" in event:
                for block in event["message"].get("content", []):
                    if block.get("type") == "tool_result":
                        tid = block.get("tool_use_id", "")
                        name = _pending_tools.pop(tid, "tool")
                        snippet = ""
                        content = block.get("content", "")
                        if isinstance(content, str):
                            snippet = content
                        elif isinstance(content, list):
                            parts = [c.get("text", "") for c in content if isinstance(c, dict)]
                            snippet = "\n".join(parts)
                        if snippet:
                            lines = snippet.splitlines()
                            preview = "\n".join("          " + l for l in lines[:6])
                            if len(lines) > 6:
                                preview += f"\n          ... ({len(lines) - 6} more lines)"
                            print(f"          {D}[{name} result]{R}\n{preview}\n")
                        else:
                            print(f"          {D}[{name} done]{R}")
        elif event.get("type") == "assistant" and "message" in event:
            for block in event["message"].get("content", []):
                if block.get("type") == "tool_use":
                    tool_name = block.get("name", "unknown")
                    tool_input = block.get("input", {})
                    _pending_tools[block.get("id", "")] = tool_name
                    detail = ""
                    if tool_name in ("Read", "Edit", "Write"):
                        detail = f" {tool_input.get('file_path', '?')}"
                    elif tool_name == "Bash":
                        cmd_str = tool_input.get("command", "")
                        detail = f" {cmd_str[:80]}{'...' if len(cmd_str) > 80 else ''}"
                    elif tool_name == "Glob":
                        detail = f" {tool_input.get('pattern', '?')}"
                    elif tool_name == "Grep":
                        detail = f" /{tool_input.get('pattern', '?')}/"
                    elif tool_name == "Agent":
                        detail = f" {tool_input.get('description', '?')}"
                    print(f"          {D}[{tool_name}{detail}]{R}")
                elif block.get("type") == "text":
                    chunk_text = block["text"]
                    full_response.append(chunk_text)
                    text_only = VOICE_RE.sub('', chunk_text).strip()
                    voice_only = " ".join(m[1] for m in VOICE_RE.findall(chunk_text)).strip()
                    if voice_only:
                        print(f"          {B}Voice:{R} {voice_only}")
                    if text_only:
                        print(f"          {B}Text:{R} {text_only}")
        elif event.get("type") == "result":
            result_stats = event
            if "result" in event and not full_response:
                full_response.append(event["result"])
                text_only = VOICE_RE.sub('', event["result"]).strip()
                voice_only = " ".join(m[1] for m in VOICE_RE.findall(event["result"])).strip()
                if voice_only:
                    print(f"          {B}Voice:{R} {voice_only}")
                if text_only:
                    print(f"          {B}Text:{R} {text_only}")

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

    stats_parts = []
    if result_stats:
        if "duration_ms" in result_stats:
            stats_parts.append(f"{result_stats['duration_ms'] / 1000:.1f}s")
        usage = result_stats.get("usage", {})
        if usage.get("input_tokens"):
            stats_parts.append(f"{usage['input_tokens']} in")
        if usage.get("output_tokens"):
            stats_parts.append(f"{usage['output_tokens']} out")
        cached = usage.get("cache_read_input_tokens", 0)
        if cached:
            stats_parts.append(f"{cached} cached")
        if "total_cost_usd" in result_stats:
            stats_parts.append(f"${result_stats['total_cost_usd']:.4f}")
    print(f"          {D}[{' | '.join(stats_parts)}]{R}\n")

    # Speak any remaining v tags that arrived after the last check
    remaining = response[spoken_so_far:]
    for match in VOICE_RE.finditer(remaining):
        if is_interrupted():
            break
        say(match.group(2), lang=match.group(1))

    return response
