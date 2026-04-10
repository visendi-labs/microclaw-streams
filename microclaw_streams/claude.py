"""Claude Code integration via the claude-agent-sdk (bidirectional client)."""

import re

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    UserMessage,
    SystemMessage,
    ResultMessage,
    TextBlock,
)

from .speaker import say, reset_interrupted, is_interrupted

VOICE_RE = re.compile(r'<v(?:\s+lang="([a-z]{2})")?>(.*?)</v>', re.DOTALL)

ALWAYS_ALLOWED_TOOLS = ["AskUserQuestion", "WebSearch", "WebFetch"]

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
    "This way the user stays informed even when the spoken response is kept brief.\n\n"
    "You can use the AskUserQuestion tool when you need a structured choice from the user. "
    "The question and option labels will be spoken aloud automatically — you do NOT need to "
    "wrap them in <v> tags. Keep option labels short and natural-sounding since they'll be "
    "read out loud. The user will answer with their voice on the next turn."
)

# Module-level persistent client
_client: ClaudeSDKClient | None = None


def _block_type(block):
    return getattr(block, "type", None) or type(block).__name__


def _speak_unseen(full_response, spoken_so_far):
    accumulated = "".join(full_response)
    unseen = accumulated[spoken_so_far:]
    for match in VOICE_RE.finditer(unseen):
        if is_interrupted():
            break
        say(match.group(2), lang=match.group(1))
    last_close = unseen.rfind("</v>")
    if last_close != -1:
        return spoken_so_far + last_close + len("</v>")
    return spoken_so_far


async def start_session(allowed_tools=None, permission_mode="default", resume=None):
    """Start a persistent Claude session."""
    global _client

    if _client is not None:
        await stop_session()

    tools_list = list(ALWAYS_ALLOWED_TOOLS)
    if allowed_tools:
        for t in allowed_tools:
            if t not in tools_list:
                tools_list.append(t)

    options_kwargs = {
        "system_prompt": SYSTEM_PROMPT,
        "allowed_tools": tools_list,
        "permission_mode": permission_mode,
    }
    if resume:
        options_kwargs["resume"] = resume
    options = ClaudeAgentOptions(**options_kwargs)

    _client = ClaudeSDKClient(options)
    await _client.__aenter__()


async def stop_session():
    """Stop the persistent Claude session."""
    global _client
    if _client is not None:
        await _client.__aexit__(None, None, None)
        _client = None


async def interrupt_claude():
    """Interrupt Claude's current processing."""
    if _client is not None:
        await _client.interrupt()


async def set_permission_mode(mode):
    """Change permission mode on the live session."""
    if _client is not None:
        await _client.set_permission_mode(mode)


async def send_to_claude(text):
    """Send a message to Claude via the persistent client and stream the response."""
    if _client is None:
        raise RuntimeError("Session not started. Call start_session() first.")

    reset_interrupted()
    B = "\033[1m"
    R = "\033[0m"
    D = "\033[2m"
    print(f"{B}You:{R} {text}\n")

    await _client.query(text)

    full_response = []
    spoken_so_far = 0
    pending_tools = {}
    result_message = None

    async for message in _client.receive_response():
        if isinstance(message, AssistantMessage):
            for block in message.content:
                btype = _block_type(block)
                if isinstance(block, TextBlock) or btype == "text":
                    chunk_text = block.text
                    full_response.append(chunk_text)
                    text_only = VOICE_RE.sub('', chunk_text).strip()
                    voice_only = " ".join(m[1] for m in VOICE_RE.findall(chunk_text)).strip()
                    if voice_only:
                        print(f"          {B}Voice:{R} {voice_only}")
                    if text_only:
                        print(f"          {B}Text:{R} {text_only}")
                elif "ToolUse" in btype or btype == "tool_use":
                    tool_name = getattr(block, "name", "unknown")
                    tool_input = getattr(block, "input", {}) or {}
                    tool_id = getattr(block, "id", "")
                    pending_tools[tool_id] = tool_name
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
                    elif tool_name == "AskUserQuestion":
                        detail = " (asking)"
                    print(f"          {D}[{tool_name}{detail}]{R}")
                    if tool_name == "AskUserQuestion":
                        for q in tool_input.get("questions", []):
                            qtext = q.get("question", "")
                            opts = q.get("options", [])
                            spoken = qtext
                            labels = [o.get("label", "") for o in opts if o.get("label")]
                            if labels:
                                spoken += ". Options are: " + ", or ".join(labels)
                            print(f"          {B}Voice:{R} {spoken}")
                            say(spoken)
            spoken_so_far = _speak_unseen(full_response, spoken_so_far)

        elif isinstance(message, UserMessage):
            content = getattr(message, "content", None) or []
            if isinstance(content, list):
                for block in content:
                    btype = _block_type(block)
                    if "ToolResult" in btype or btype == "tool_result":
                        tid = getattr(block, "tool_use_id", "")
                        name = pending_tools.pop(tid, "tool")
                        bcontent = getattr(block, "content", "")
                        snippet = ""
                        if isinstance(bcontent, str):
                            snippet = bcontent
                        elif isinstance(bcontent, list):
                            parts = []
                            for c in bcontent:
                                if hasattr(c, "text"):
                                    parts.append(c.text)
                                elif isinstance(c, dict):
                                    parts.append(c.get("text", ""))
                            snippet = "\n".join(parts)
                        if snippet:
                            lines = snippet.splitlines()
                            preview = "\n".join("          " + l for l in lines[:6])
                            if len(lines) > 6:
                                preview += f"\n          ... ({len(lines) - 6} more lines)"
                            print(f"          {D}[{name} result]{R}\n{preview}\n")
                        else:
                            print(f"          {D}[{name} done]{R}")

        elif isinstance(message, ResultMessage):
            result_message = message
            result_text = getattr(message, "result", None)
            if result_text and not full_response:
                full_response.append(result_text)
                text_only = VOICE_RE.sub('', result_text).strip()
                voice_only = " ".join(m[1] for m in VOICE_RE.findall(result_text)).strip()
                if voice_only:
                    print(f"          {B}Voice:{R} {voice_only}")
                if text_only:
                    print(f"          {B}Text:{R} {text_only}")

    response = "".join(full_response)

    stats_parts = []
    if result_message is not None:
        dur_ms = getattr(result_message, "duration_ms", None)
        if dur_ms:
            stats_parts.append(f"{dur_ms / 1000:.1f}s")
        usage = getattr(result_message, "usage", None) or {}
        if isinstance(usage, dict):
            if usage.get("input_tokens"):
                stats_parts.append(f"{usage['input_tokens']} in")
            if usage.get("output_tokens"):
                stats_parts.append(f"{usage['output_tokens']} out")
            cached = usage.get("cache_read_input_tokens", 0)
            if cached:
                stats_parts.append(f"{cached} cached")
        cost = getattr(result_message, "total_cost_usd", None)
        if cost is not None:
            stats_parts.append(f"${cost:.4f}")
    if stats_parts:
        print(f"          {D}[{' | '.join(stats_parts)}]{R}\n")

    remaining = response[spoken_so_far:]
    for match in VOICE_RE.finditer(remaining):
        if is_interrupted():
            break
        say(match.group(2), lang=match.group(1))

    return response
