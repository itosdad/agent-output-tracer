"""Claude Code event → normalized event.

Converts the JSON that Claude Code delivers on a hook's stdin into the
engine-agnostic schema documented in `docs/DESIGN.md` §3.3 / §5.1.

The function is total over malformed input: any raw payload that is not
both a dict and recognizable as one of the 5 supported hook events
returns None. Callers (the hook scripts) treat None as "skip this event".
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

ENGINE_ID = "claude-code"

# Claude Code hook_event_name → plugin event_type
EVENT_TYPE_MAP: dict[str, str] = {
    "UserPromptSubmit": "user_prompt",
    "PreToolUse": "pre_tool",
    "PostToolUse": "post_tool",
    "Stop": "agent_response",
    "SessionEnd": "session_end",
}


def _now_iso_ms(now: Callable[[], datetime] | None) -> str:
    if now is not None:
        moment = now()
    else:
        moment = datetime.now(timezone.utc).astimezone()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.isoformat(timespec="milliseconds")


def _extract_paths(tool_name: str | None, tool_input: dict[str, Any]) -> list[str]:
    """Pull file-path-like values out of tool_input.

    Read / Write / Edit / MultiEdit → file_path
    Glob / Grep                    → path (when present)
    Bash                           → none (command is captured separately)
    """
    if not isinstance(tool_input, dict):
        return []
    paths: list[str] = []
    fp = tool_input.get("file_path")
    if isinstance(fp, str) and fp:
        paths.append(fp)
    if tool_name in ("Glob", "Grep"):
        p = tool_input.get("path")
        if isinstance(p, str) and p:
            paths.append(p)
    return paths


def _coerce_response(value: Any) -> tuple[str | None, int]:
    """Return (string-representation, byte-count) for a tool_response payload.

    String values pass through. Dict / list / other JSON values are
    json.dumps'ed so downstream grep can still find substrings."""
    if value is None:
        return None, 0
    if isinstance(value, str):
        return value, len(value.encode("utf-8"))
    try:
        serialized = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        serialized = repr(value)
    return serialized, len(serialized.encode("utf-8"))


def _build_base(
    raw: dict[str, Any],
    event_type: str,
    ts: str,
) -> dict[str, Any]:
    return {
        "v": 1,
        "engine": ENGINE_ID,
        "event_type": event_type,
        "session_id": raw.get("session_id"),
        "ts": ts,
        "cwd": raw.get("cwd"),
        "user_prompt_text": None,
        "tool_name": None,
        "tool_input": None,
        "tool_response": None,
        "agent_response_text": None,
        "stop_reason": None,
        "paths": [],
        "command": None,
        "result_bytes": 0,
        "raw_event": raw,
    }


def normalize_event(
    raw: Any,
    event_type: str | None = None,
    *,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any] | None:
    """Convert a Claude Code hook payload into a normalized event dict.

    Returns None when the input is not a dict or cannot be matched to any
    of the 5 supported hook events.
    """
    if not isinstance(raw, dict):
        return None

    if event_type is None:
        hook_event_name = raw.get("hook_event_name")
        if not isinstance(hook_event_name, str):
            return None
        event_type = EVENT_TYPE_MAP.get(hook_event_name)
        if event_type is None:
            return None

    if not raw.get("session_id"):
        return None

    ts = _now_iso_ms(now)
    out = _build_base(raw, event_type, ts)

    if event_type == "user_prompt":
        # Claude Code's actual UserPromptSubmit field is "prompt" (matches
        # Codex). Older public docs / our initial draft of the design used
        # "user_prompt"; we accept both so the adapter survives any future
        # surface change.
        text = raw.get("user_prompt")
        if not isinstance(text, str):
            text = raw.get("prompt")
        if isinstance(text, str):
            out["user_prompt_text"] = text

    elif event_type == "pre_tool":
        tool_name = raw.get("tool_name")
        tool_input = raw.get("tool_input") or {}
        out["tool_name"] = tool_name if isinstance(tool_name, str) else None
        out["tool_input"] = tool_input if isinstance(tool_input, dict) else {}
        out["paths"] = _extract_paths(out["tool_name"], out["tool_input"])
        if out["tool_name"] == "Bash":
            cmd = out["tool_input"].get("command")
            if isinstance(cmd, str):
                out["command"] = cmd

    elif event_type == "post_tool":
        tool_name = raw.get("tool_name")
        tool_input = raw.get("tool_input") or {}
        out["tool_name"] = tool_name if isinstance(tool_name, str) else None
        out["tool_input"] = tool_input if isinstance(tool_input, dict) else {}
        out["paths"] = _extract_paths(out["tool_name"], out["tool_input"])
        response_text, response_bytes = _coerce_response(raw.get("tool_response"))
        out["tool_response"] = response_text
        out["result_bytes"] = response_bytes
        if out["tool_name"] == "Bash":
            cmd = out["tool_input"].get("command")
            if isinstance(cmd, str):
                out["command"] = cmd

    elif event_type == "agent_response":
        # Claude Code's actual Stop event uses `last_assistant_message`
        # (matches Codex), not `response_text` as the design draft assumed.
        # Accept both. Claude Code does not emit `stop_reason`; it emits
        # `stop_hook_active: bool` instead, which is metadata about the
        # hook itself (not a useful event-level reason), so we ignore it.
        text = raw.get("response_text")
        if not isinstance(text, str):
            text = raw.get("last_assistant_message")
        if isinstance(text, str):
            out["agent_response_text"] = text
        stop_reason = raw.get("stop_reason")
        if isinstance(stop_reason, str):
            out["stop_reason"] = stop_reason

    # session_end: base fields are enough

    return out
