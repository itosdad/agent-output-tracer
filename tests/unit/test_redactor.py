"""Unit tests for core.redactor.

Contract:
  - `redact_text(text, patterns=None)` replaces matches with `[REDACTED]`.
  - `redact_event(event, patterns=None)` produces a deep-copied event with
    every string field (and nested string in tool_input / raw_event /
    paths) redacted. The structure is otherwise unchanged.
  - `compile_patterns(patterns)` returns a list of compiled regexes,
    silently dropping invalid patterns.
"""

from __future__ import annotations

import copy

from core.redactor import (
    DEFAULT_PATTERNS,
    compile_patterns,
    redact_event,
    redact_text,
)

# --------- redact_text ----------


def test_redact_api_key():
    text = "my key is sk-1234567890abcdef1234567890abcdef1234567890ab and more"
    out = redact_text(text)
    assert "sk-1234567890" not in out
    assert "[REDACTED]" in out


def test_redact_github_pat():
    text = "ghp_abcdefghijklmnopqrstuvwxyz0123456789AA"
    out = redact_text(text)
    assert "ghp_" not in out or "[REDACTED]" in out


def test_redact_password_kv():
    cases = [
        'password="supersecret12345678"',
        "password=supersecret12345678",
        "API_KEY: secretkey1234567890abcdef",
        "token = 'mytoken1234567890abcdef'",
    ]
    for case in cases:
        out = redact_text(case)
        assert "[REDACTED]" in out, f"Failed to redact: {case}"


def test_clean_text_unchanged():
    """Plain text without secrets should pass through untouched."""
    text = "Implement the FooBar component and add unit tests."
    assert redact_text(text) == text


def test_empty_or_none():
    assert redact_text("") == ""
    assert redact_text(None) is None


def test_redact_text_returns_string_when_input_is_string():
    out = redact_text("plain")
    assert isinstance(out, str)


def test_custom_patterns_extend_defaults():
    extra = [r"INTERNAL-[A-Z0-9]+"]
    text = "ref INTERNAL-ABC123 was leaked"
    out = redact_text(text, patterns=extra)
    assert "INTERNAL-ABC123" not in out
    assert "[REDACTED]" in out
    # Default patterns still apply
    sk_text = "sk-1234567890abcdef1234567890abcdef1234567890ab"
    assert "[REDACTED]" in redact_text(sk_text, patterns=extra)


def test_compile_patterns_drops_invalid():
    patterns = [r"valid-\d+", "(((invalid_unclosed", r"another-valid-[a-z]+"]
    compiled = compile_patterns(patterns)
    assert len(compiled) == 2  # the broken one is silently dropped


def test_redact_text_with_no_default_uses_only_custom():
    text = "sk-1234567890abcdef1234567890abcdef1234567890ab and FOO-9999"
    out = redact_text(text, patterns=[r"FOO-\d+"], include_defaults=False)
    assert "FOO-" not in out
    # default pattern NOT applied because include_defaults=False
    assert "sk-1234567890abcdef" in out


# --------- redact_event ----------


def _base_event():
    return {
        "v": 1,
        "engine": "claude-code",
        "event_type": "post_tool",
        "session_id": "S1",
        "ts": "2026-01-01T00:00:00.000+00:00",
        "cwd": "/proj",
        "user_prompt_text": None,
        "tool_name": "Bash",
        "tool_input": {
            "command": (
                "curl -H 'Authorization: Bearer ghp_abcdefghijklmnopqrstuvwxyz0123456789AA'"
            ),
            "description": "fetch some thing",
        },
        "tool_response": "ok: token=sk-1234567890abcdef1234567890abcdef1234567890ab",
        "agent_response_text": None,
        "stop_reason": None,
        "paths": [],
        "command": "echo sk-1234567890abcdef1234567890abcdef1234567890ab",
        "result_bytes": 100,
        "raw_event": {
            "session_id": "S1",
            "tool_input": {
                "command": "ghp_abcdefghijklmnopqrstuvwxyz0123456789AA",
            },
        },
    }


def test_redact_event_redacts_tool_response():
    e = _base_event()
    out = redact_event(e)
    assert "sk-" not in out["tool_response"]
    assert "[REDACTED]" in out["tool_response"]


def test_redact_event_redacts_command_field():
    e = _base_event()
    out = redact_event(e)
    assert "[REDACTED]" in out["command"]


def test_redact_event_redacts_nested_tool_input():
    e = _base_event()
    out = redact_event(e)
    assert "ghp_" not in out["tool_input"]["command"]
    assert "[REDACTED]" in out["tool_input"]["command"]
    # description is clean — should pass through
    assert out["tool_input"]["description"] == "fetch some thing"


def test_redact_event_redacts_raw_event_recursively():
    e = _base_event()
    out = redact_event(e)
    assert "ghp_" not in out["raw_event"]["tool_input"]["command"]


def test_redact_event_does_not_mutate_input():
    e = _base_event()
    snapshot = copy.deepcopy(e)
    _ = redact_event(e)
    assert e == snapshot


def test_redact_event_preserves_structure():
    e = _base_event()
    out = redact_event(e)
    assert set(out.keys()) == set(e.keys())
    assert out["event_type"] == "post_tool"
    assert out["v"] == 1
    assert out["session_id"] == "S1"
    assert out["result_bytes"] == 100


def test_redact_event_user_prompt():
    e = _base_event()
    e["event_type"] = "user_prompt"
    e["user_prompt_text"] = "my pw is password=supersecret12345678 fyi"
    out = redact_event(e)
    assert "supersecret12345678" not in out["user_prompt_text"]


def test_redact_event_agent_response():
    e = _base_event()
    e["event_type"] = "agent_response"
    e["agent_response_text"] = "leaked sk-1234567890abcdef1234567890abcdef1234567890ab"
    out = redact_event(e)
    assert "sk-" not in out["agent_response_text"] or "[REDACTED]" in out["agent_response_text"]


def test_redact_event_paths_list():
    e = _base_event()
    e["paths"] = [
        "/proj/configs/ghp_abcdefghijklmnopqrstuvwxyz0123456789AA.txt",
        "/proj/normal.md",
    ]
    out = redact_event(e)
    # Filenames containing leaked tokens get redacted; normal paths
    # pass through.
    assert "ghp_" not in out["paths"][0]
    assert out["paths"][1] == "/proj/normal.md"


def test_default_patterns_present():
    """Smoke test that the DEFAULT_PATTERNS list is non-empty and matches
    the headline secret formats we promise to mask."""
    assert len(DEFAULT_PATTERNS) >= 3
    sample = "sk-1234567890abcdef1234567890abcdef1234567890ab"
    assert "[REDACTED]" in redact_text(sample)


def test_redact_event_handles_none_event():
    assert redact_event(None) is None


def test_redact_event_handles_non_dict():
    assert redact_event("not a dict") == "not a dict"


def test_redact_event_replacement_token_configurable():
    e = _base_event()
    out = redact_event(e, replacement="<REMOVED>")
    assert "<REMOVED>" in out["tool_response"]
    assert "[REDACTED]" not in out["tool_response"]
