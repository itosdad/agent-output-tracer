"""Codex CLI event → normalized event.

Converts the JSON that Codex delivers on a hook's stdin into the same
engine-agnostic schema documented in `docs/DESIGN.md` §3.3 / §5.1.

Codex wire format (per §3.2): `hook_event_name` is snake_case, every
event carries `session_id` / `cwd` / `model` / `permission_mode`, and
turn-scoped events (UserPromptSubmit / PreToolUse / PostToolUse / Stop /
PermissionRequest) additionally carry `turn_id`. Codex does NOT emit a
SessionEnd event — metadata.json stays current because the recorder
updates it on every append.

PermissionRequest is observed but not normalized (design §3.2.2 — not
useful for forensic replay). All other 7 events map cleanly.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

ENGINE_ID = "codex"

# Codex hook_event_name (snake_case) → plugin event_type.
# PermissionRequest is intentionally absent (design §3.2.2).
EVENT_TYPE_MAP: dict[str, str] = {
    "session_start": "session_start",
    "user_prompt_submit": "user_prompt",
    "pre_tool_use": "pre_tool",
    "post_tool_use": "post_tool",
    "stop": "agent_response",
    "pre_compact": "compact_pre",
    "post_compact": "compact_post",
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
    """Pull file-path-like values out of a Codex tool_input.

    Codex tool surface differs from Claude Code:
      - apply_patch: a unified-diff blob; we don't try to parse out
        individual touched paths (design §3.2.4 — Read-equivalents don't
        even fire PostToolUse here, so per-path forensic is best-effort)
      - Bash:        command is captured separately
      - MCP tools:   tool-specific input; we look for the common
                     `file_path` / `path` keys best-effort
    """
    if not isinstance(tool_input, dict):
        return []
    paths: list[str] = []
    fp = tool_input.get("file_path")
    if isinstance(fp, str) and fp:
        paths.append(fp)
    p = tool_input.get("path")
    if isinstance(p, str) and p and p not in paths:
        paths.append(p)
    return paths


def _coerce_response(value: Any) -> tuple[str | None, int]:
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
    base: dict[str, Any] = {
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
    # Codex-specific optional fields: only attach when present so callers
    # built against the Claude-Code schema continue to work.
    turn_id = raw.get("turn_id")
    if isinstance(turn_id, str) and turn_id:
        base["turn_id"] = turn_id
    # Schema v2 (DESIGN_FORENSIC_UX §6.2) pass-through.
    for key in ("tool_use_id", "engine_version"):
        v = raw.get(key)
        if isinstance(v, str) and v:
            base[key] = v
    pm = raw.get("permission_mode")
    if isinstance(pm, str) and pm:
        base["permission_mode"] = pm
    parent = raw.get("parent_session_id")
    if isinstance(parent, str) and parent:
        base["parent_session_id"] = parent
    duration = raw.get("duration_ms")
    if isinstance(duration, int):
        base["duration_ms"] = duration
    tokens = raw.get("tokens") or (raw.get("usage") if isinstance(raw.get("usage"), dict) else None)
    if isinstance(tokens, dict):
        base["tokens"] = {
            "input": tokens.get("input_tokens") or tokens.get("input"),
            "output": tokens.get("output_tokens") or tokens.get("output"),
            "cache_read": tokens.get("cache_read_input_tokens") or tokens.get("cache_read"),
            "cache_creation": tokens.get("cache_creation_input_tokens") or tokens.get("cache_creation"),
        }
    return base


def normalize_event(
    raw: Any,
    event_type: str | None = None,
    *,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any] | None:
    """Convert a Codex hook payload into a normalized event dict.

    Returns None when the input is not a dict, lacks `session_id`, or
    cannot be matched to any of the 7 supported hook events.
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
        text = raw.get("prompt")
        if not isinstance(text, str):
            # Defensive: some sample events show `user_prompt` key
            text = raw.get("user_prompt")
        if isinstance(text, str):
            out["user_prompt_text"] = text

    elif event_type == "pre_tool":
        tool_name = raw.get("tool_name")
        tool_input = raw.get("tool_input") or {}
        out["tool_name"] = tool_name if isinstance(tool_name, str) else None
        out["tool_input"] = tool_input if isinstance(tool_input, dict) else {}
        out["paths"] = _extract_paths(out["tool_name"], out["tool_input"])
        # Codex canonical key is `command`; design §3.2.10 confirms `cmd`
        # was never spec.
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
        # Codex Stop event uses `last_assistant_message` — same convention
        # as Claude Code's post-spec-alignment field.
        text = raw.get("last_assistant_message")
        if not isinstance(text, str):
            text = raw.get("response_text")
        if isinstance(text, str):
            out["agent_response_text"] = text
        stop_reason = raw.get("stop_reason")
        if isinstance(stop_reason, str):
            out["stop_reason"] = stop_reason

    elif event_type == "session_start":
        # Codex SessionStart carries a `source` enum (startup / resume /
        # clear). Capture it under stop_reason since the field is unused
        # for session_start and a structured "why this fired" is what an
        # operator wants to see at replay time.
        source = raw.get("source")
        if isinstance(source, str):
            out["stop_reason"] = source

    # compact_pre / compact_post: base fields are enough; raw_event keeps
    # the per-engine payload for anyone who wants to dig in.

    return out
