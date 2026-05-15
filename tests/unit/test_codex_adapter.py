"""Unit tests for the Codex event normalizer (DESIGN §3.2 + §3.3).

Contract under test (adapters.codex.normalize_event):

  normalize_event(raw: dict, event_type: str | None = None, *, now=None)
    → dict | None

Codex wire format differences vs Claude Code:
  - `hook_event_name` is snake_case (`pre_tool_use`, not `PreToolUse`)
  - every event carries `permission_mode` + `model`
  - turn-scoped events carry `turn_id`
  - no `SessionEnd`; SessionStart / PreCompact / PostCompact exist
"""

from __future__ import annotations

from datetime import UTC, datetime

from adapters.codex import (
    ENGINE_ID,
    EVENT_TYPE_MAP,
    normalize_event,
)

FIXED_NOW = datetime(2026, 5, 15, 12, 0, 0, 500000, tzinfo=UTC)


def _fixed_now():
    return FIXED_NOW


def _codex_base(**over):
    """Codex event template — every field that the official generated
    schema marks `required`."""
    base = {
        "hook_event_name": "user_prompt_submit",
        "session_id": "cdx-001",
        "cwd": "/Users/work/proj",
        "model": "gpt-5",
        "permission_mode": "default",
        "transcript_path": "/tmp/codex.jsonl",
        "turn_id": "t1",
    }
    base.update(over)
    return base


# --------- engine + event type mapping ----------


def test_engine_id_is_codex():
    out = normalize_event(_codex_base(prompt="hi"), now=_fixed_now)
    assert out is not None
    assert out["engine"] == ENGINE_ID == "codex"


def test_event_type_map_covers_seven_events():
    """All 7 subscribed events map; PermissionRequest is intentionally
    not in the map (design §3.2.2)."""
    assert set(EVENT_TYPE_MAP) == {
        "session_start",
        "user_prompt_submit",
        "pre_tool_use",
        "post_tool_use",
        "stop",
        "pre_compact",
        "post_compact",
    }


def test_permission_request_is_dropped():
    raw = _codex_base(hook_event_name="permission_request")
    assert normalize_event(raw, now=_fixed_now) is None


def test_unknown_event_name_dropped():
    raw = _codex_base(hook_event_name="some_made_up_event")
    assert normalize_event(raw, now=_fixed_now) is None


# --------- input shape guards ----------


def test_non_dict_input_returns_none():
    assert normalize_event(None, now=_fixed_now) is None
    assert normalize_event("oops", now=_fixed_now) is None
    assert normalize_event([1, 2], now=_fixed_now) is None


def test_missing_session_id_returns_none():
    raw = _codex_base(prompt="hi")
    raw.pop("session_id")
    assert normalize_event(raw, now=_fixed_now) is None


# --------- user_prompt ----------


def test_user_prompt_uses_prompt_field():
    raw = _codex_base(hook_event_name="user_prompt_submit", prompt="implement Foo")
    out = normalize_event(raw, now=_fixed_now)
    assert out is not None
    assert out["event_type"] == "user_prompt"
    assert out["user_prompt_text"] == "implement Foo"
    assert out["turn_id"] == "t1"


def test_user_prompt_also_accepts_user_prompt_field():
    raw = _codex_base(
        hook_event_name="user_prompt_submit",
        user_prompt="legacy field name",
    )
    raw.pop("turn_id", None)
    out = normalize_event(raw, now=_fixed_now)
    assert out is not None
    assert out["user_prompt_text"] == "legacy field name"
    # turn_id absent → key omitted (not None)
    assert "turn_id" not in out


# --------- pre_tool ----------


def test_pre_tool_apply_patch_path_extraction():
    raw = _codex_base(
        hook_event_name="pre_tool_use",
        tool_name="apply_patch",
        tool_input={"file_path": "/proj/foo.py"},
    )
    out = normalize_event(raw, now=_fixed_now)
    assert out is not None
    assert out["event_type"] == "pre_tool"
    assert out["tool_name"] == "apply_patch"
    assert out["paths"] == ["/proj/foo.py"]


def test_pre_tool_bash_captures_command_canonical_field():
    """Design §3.2.10: `command` is canonical, `cmd` was never spec."""
    raw = _codex_base(
        hook_event_name="pre_tool_use",
        tool_name="Bash",
        tool_input={"command": "ls -la"},
    )
    out = normalize_event(raw, now=_fixed_now)
    assert out is not None
    assert out["command"] == "ls -la"


def test_pre_tool_mcp_dual_path_keys():
    """MCP tools can use either `file_path` or `path` — adapter
    extracts both when distinct."""
    raw = _codex_base(
        hook_event_name="pre_tool_use",
        tool_name="mcp_some_search",
        tool_input={"file_path": "/a.py", "path": "/b.py"},
    )
    out = normalize_event(raw, now=_fixed_now)
    assert out is not None
    assert out["paths"] == ["/a.py", "/b.py"]


# --------- post_tool ----------


def test_post_tool_bash_with_string_response():
    raw = _codex_base(
        hook_event_name="post_tool_use",
        tool_name="Bash",
        tool_input={"command": "echo hi"},
        tool_response="hi\n",
    )
    out = normalize_event(raw, now=_fixed_now)
    assert out is not None
    assert out["event_type"] == "post_tool"
    assert out["tool_response"] == "hi\n"
    assert out["result_bytes"] == 3
    assert out["command"] == "echo hi"


def test_post_tool_serializes_dict_response():
    raw = _codex_base(
        hook_event_name="post_tool_use",
        tool_name="apply_patch",
        tool_input={"patch": "..."},
        tool_response={"applied": True, "files": ["/a.py"]},
    )
    out = normalize_event(raw, now=_fixed_now)
    assert out is not None
    assert out["tool_response"] is not None
    assert "applied" in out["tool_response"]
    assert out["result_bytes"] > 0


# --------- stop / agent_response ----------


def test_stop_event_extracts_last_assistant_message():
    raw = _codex_base(
        hook_event_name="stop",
        last_assistant_message="done",
        stop_reason="end_turn",
    )
    out = normalize_event(raw, now=_fixed_now)
    assert out is not None
    assert out["event_type"] == "agent_response"
    assert out["agent_response_text"] == "done"
    assert out["stop_reason"] == "end_turn"
    assert out["turn_id"] == "t1"


# --------- session_start (Codex-only) ----------


def test_session_start_captures_source():
    raw = _codex_base(hook_event_name="session_start", source="resume")
    raw.pop("turn_id", None)  # SessionStart isn't turn-scoped
    out = normalize_event(raw, now=_fixed_now)
    assert out is not None
    assert out["event_type"] == "session_start"
    assert out["stop_reason"] == "resume"


def test_session_start_no_turn_id():
    raw = _codex_base(hook_event_name="session_start", source="startup")
    raw.pop("turn_id", None)
    out = normalize_event(raw, now=_fixed_now)
    assert out is not None
    assert "turn_id" not in out


# --------- compaction ----------


def test_pre_compact_normalized():
    raw = _codex_base(hook_event_name="pre_compact")
    out = normalize_event(raw, now=_fixed_now)
    assert out is not None
    assert out["event_type"] == "compact_pre"


def test_post_compact_normalized():
    raw = _codex_base(hook_event_name="post_compact")
    out = normalize_event(raw, now=_fixed_now)
    assert out is not None
    assert out["event_type"] == "compact_post"


# --------- explicit event_type kwarg ----------


def test_explicit_event_type_overrides_hook_event_name():
    """For hook scripts that know their own type, we honor the kwarg
    without re-deriving from raw."""
    raw = _codex_base(prompt="x")
    raw.pop("hook_event_name", None)
    out = normalize_event(raw, event_type="user_prompt", now=_fixed_now)
    assert out is not None
    assert out["event_type"] == "user_prompt"
    assert out["user_prompt_text"] == "x"


# --------- raw_event preserved ----------


def test_raw_event_preserved():
    raw = _codex_base(prompt="hello")
    out = normalize_event(raw, now=_fixed_now)
    assert out is not None
    assert out["raw_event"] == raw
