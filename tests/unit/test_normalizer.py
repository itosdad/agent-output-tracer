"""Unit tests for the Claude Code event normalizer.

Contract under test (adapters.claude_code.normalize_event):

  normalize_event(raw: dict, event_type: str | None = None, *, now=None)
    → dict | None

  - Returns a dict with the engine-agnostic schema from DESIGN §3.3 / §5.1.
  - Returns None when the input is too malformed to be useful
    (no session_id and no hook_event_name).
  - When `event_type` is None, derives it from `hook_event_name`.
  - `now` lets tests inject a deterministic timestamp (callable returning
    a datetime).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from adapters.claude_code import (
    ENGINE_ID,
    EVENT_TYPE_MAP,
    normalize_event,
)

FIXED_NOW = datetime(2026, 5, 14, 10, 23, 45, 123000, tzinfo=UTC)


def _fixed_now():
    return FIXED_NOW


# --------- user_prompt ----------


def test_user_prompt_basic():
    raw = {
        "session_id": "abc123",
        "transcript_path": "/tmp/t.jsonl",
        "cwd": "/Users/dev/proj",
        "hook_event_name": "UserPromptSubmit",
        "user_prompt": "Implement FooBar component",
    }

    out = normalize_event(raw, now=_fixed_now)

    assert out is not None
    assert out["engine"] == ENGINE_ID
    assert out["event_type"] == "user_prompt"
    assert out["session_id"] == "abc123"
    assert out["cwd"] == "/Users/dev/proj"
    assert out["user_prompt_text"] == "Implement FooBar component"
    assert out["ts"] == FIXED_NOW.isoformat(timespec="milliseconds")
    assert out["raw_event"] == raw
    # tool fields should be None for user_prompt
    assert out["tool_name"] is None
    assert out["tool_input"] is None


def test_user_prompt_also_accepts_prompt_field():
    """Codex uses `prompt`; Claude Code (per design appendix A) uses
    `user_prompt`. Adapter accepts either to be forgiving."""
    raw = {
        "session_id": "s",
        "hook_event_name": "UserPromptSubmit",
        "prompt": "hello",
    }
    out = normalize_event(raw, now=_fixed_now)
    assert out is not None
    assert out["user_prompt_text"] == "hello"


# --------- pre_tool ----------


def test_pre_tool_read_extracts_file_path():
    raw = {
        "session_id": "s",
        "cwd": "/cwd",
        "hook_event_name": "PreToolUse",
        "tool_name": "Read",
        "tool_input": {"file_path": "/Users/dev/proj/foo.md"},
    }
    out = normalize_event(raw, now=_fixed_now)
    assert out is not None
    assert out["event_type"] == "pre_tool"
    assert out["tool_name"] == "Read"
    assert out["tool_input"] == {"file_path": "/Users/dev/proj/foo.md"}
    assert out["paths"] == ["/Users/dev/proj/foo.md"]
    assert out["command"] is None


def test_pre_tool_glob_extracts_path_field_when_present():
    raw = {
        "session_id": "s",
        "hook_event_name": "PreToolUse",
        "tool_name": "Glob",
        "tool_input": {"pattern": "src/**/*.tsx", "path": "/proj/src"},
    }
    out = normalize_event(raw, now=_fixed_now)
    assert out["paths"] == ["/proj/src"]


def test_pre_tool_glob_no_path_field():
    raw = {
        "session_id": "s",
        "hook_event_name": "PreToolUse",
        "tool_name": "Glob",
        "tool_input": {"pattern": "src/**/*.tsx"},
    }
    out = normalize_event(raw, now=_fixed_now)
    assert out["paths"] == []


def test_pre_tool_bash_extracts_command():
    raw = {
        "session_id": "s",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "ls -la /tmp", "description": "list /tmp"},
    }
    out = normalize_event(raw, now=_fixed_now)
    assert out["tool_name"] == "Bash"
    assert out["command"] == "ls -la /tmp"
    assert out["paths"] == []


def test_pre_tool_edit_extracts_file_path():
    raw = {
        "session_id": "s",
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "/proj/a.py",
            "old_string": "x",
            "new_string": "y",
        },
    }
    out = normalize_event(raw, now=_fixed_now)
    assert out["paths"] == ["/proj/a.py"]


def test_pre_tool_multiedit_extracts_file_path():
    raw = {
        "session_id": "s",
        "hook_event_name": "PreToolUse",
        "tool_name": "MultiEdit",
        "tool_input": {"file_path": "/proj/a.py", "edits": []},
    }
    out = normalize_event(raw, now=_fixed_now)
    assert out["paths"] == ["/proj/a.py"]


def test_pre_tool_missing_tool_input_is_tolerated():
    raw = {
        "session_id": "s",
        "hook_event_name": "PreToolUse",
        "tool_name": "Read",
        # no tool_input
    }
    out = normalize_event(raw, now=_fixed_now)
    assert out is not None
    assert out["tool_input"] == {}
    assert out["paths"] == []


# --------- post_tool ----------


def test_post_tool_string_response():
    raw = {
        "session_id": "s",
        "hook_event_name": "PostToolUse",
        "tool_name": "Read",
        "tool_input": {"file_path": "/a"},
        "tool_response": "file contents here",
    }
    out = normalize_event(raw, now=_fixed_now)
    assert out is not None
    assert out["event_type"] == "post_tool"
    assert out["tool_response"] == "file contents here"
    assert out["result_bytes"] == len(b"file contents here")
    assert out["paths"] == ["/a"]


def test_post_tool_dict_response_stringifies():
    raw = {
        "session_id": "s",
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "echo hi"},
        "tool_response": {"stdout": "hi\n", "exit_code": 0},
    }
    out = normalize_event(raw, now=_fixed_now)
    assert out is not None
    # JSON-serialized representation for downstream grep / index
    assert "hi" in out["tool_response"]
    assert out["result_bytes"] >= 4


def test_post_tool_response_missing():
    raw = {
        "session_id": "s",
        "hook_event_name": "PostToolUse",
        "tool_name": "Read",
        "tool_input": {"file_path": "/a"},
    }
    out = normalize_event(raw, now=_fixed_now)
    assert out is not None
    assert out["tool_response"] is None
    assert out["result_bytes"] == 0


# --------- agent_response (Stop) ----------


def test_stop_extracts_response_text_and_reason():
    raw = {
        "session_id": "s",
        "hook_event_name": "Stop",
        "stop_reason": "end_turn",
        "response_text": "Here is the plan...",
    }
    out = normalize_event(raw, now=_fixed_now)
    assert out is not None
    assert out["event_type"] == "agent_response"
    assert out["agent_response_text"] == "Here is the plan..."
    assert out["stop_reason"] == "end_turn"


def test_stop_alt_field_names_codex_style():
    """If the engine reports response under last_assistant_message (Codex),
    still extract it."""
    raw = {
        "session_id": "s",
        "hook_event_name": "Stop",
        "last_assistant_message": "hello",
    }
    out = normalize_event(raw, now=_fixed_now)
    assert out is not None
    assert out["agent_response_text"] == "hello"


# --------- session_end ----------


def test_session_end_minimum():
    raw = {
        "session_id": "s",
        "hook_event_name": "SessionEnd",
        "cwd": "/proj",
    }
    out = normalize_event(raw, now=_fixed_now)
    assert out is not None
    assert out["event_type"] == "session_end"
    assert out["session_id"] == "s"


# --------- malformed / robustness ----------


def test_missing_session_id_and_event_name_returns_none():
    raw = {"random": "junk"}
    assert normalize_event(raw, now=_fixed_now) is None


def test_unknown_hook_event_name_returns_none():
    raw = {"session_id": "s", "hook_event_name": "Unrelated"}
    assert normalize_event(raw, now=_fixed_now) is None


def test_explicit_event_type_overrides_hook_event_name():
    raw = {
        "session_id": "s",
        "hook_event_name": "UserPromptSubmit",
        "user_prompt": "hi",
    }
    out = normalize_event(raw, event_type="user_prompt", now=_fixed_now)
    assert out["event_type"] == "user_prompt"


def test_event_type_map_covers_5_hooks():
    assert set(EVENT_TYPE_MAP) == {
        "UserPromptSubmit",
        "PreToolUse",
        "PostToolUse",
        "Stop",
        "SessionEnd",
    }


def test_non_dict_input_returns_none():
    assert normalize_event(None, now=_fixed_now) is None
    assert normalize_event("not a dict", now=_fixed_now) is None
    assert normalize_event(42, now=_fixed_now) is None


def test_raw_event_preserved_for_debug():
    raw = {
        "session_id": "s",
        "hook_event_name": "PreToolUse",
        "tool_name": "Read",
        "tool_input": {"file_path": "/a"},
        "extra_field_for_debug": "preserve me",
    }
    out = normalize_event(raw, now=_fixed_now)
    assert out["raw_event"] == raw
    assert out["raw_event"]["extra_field_for_debug"] == "preserve me"


def test_ts_uses_real_clock_when_now_not_supplied():
    raw = {
        "session_id": "s",
        "hook_event_name": "UserPromptSubmit",
        "user_prompt": "x",
    }
    out = normalize_event(raw)
    # Must be a parseable ISO string
    parsed = datetime.fromisoformat(out["ts"])
    assert parsed.tzinfo is not None  # tz-aware


def test_cwd_optional():
    raw = {
        "session_id": "s",
        "hook_event_name": "UserPromptSubmit",
        "user_prompt": "x",
    }
    out = normalize_event(raw, now=_fixed_now)
    assert out["cwd"] is None


@pytest.mark.parametrize(
    "hook_event,expected_type",
    [
        ("UserPromptSubmit", "user_prompt"),
        ("PreToolUse", "pre_tool"),
        ("PostToolUse", "post_tool"),
        ("Stop", "agent_response"),
        ("SessionEnd", "session_end"),
    ],
)
def test_event_type_derivation(hook_event, expected_type):
    raw = {"session_id": "s", "hook_event_name": hook_event}
    out = normalize_event(raw, now=_fixed_now)
    assert out is not None
    assert out["event_type"] == expected_type
