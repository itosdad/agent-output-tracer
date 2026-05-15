"""Unit tests for query.grep — session-wide regex search."""

from __future__ import annotations

import io
import re

from core.recorder import append_event
from query.grep import grep


def _seed(plugin_data_dir, sid="G1"):
    events = [
        {
            "v": 1,
            "engine": "claude-code",
            "event_type": "user_prompt",
            "session_id": sid,
            "ts": "2026-01-01T00:00:00.000+00:00",
            "cwd": "/p",
            "user_prompt_text": "Please implement the FooBar widget",
            "tool_name": None,
            "tool_input": None,
            "tool_response": None,
            "agent_response_text": None,
            "stop_reason": None,
            "paths": [],
            "command": None,
            "result_bytes": 0,
            "raw_event": {},
        },
        {
            "v": 1,
            "engine": "claude-code",
            "event_type": "pre_tool",
            "session_id": sid,
            "ts": "2026-01-01T00:00:01.000+00:00",
            "cwd": "/p",
            "user_prompt_text": None,
            "tool_name": "Read",
            "tool_input": {"file_path": "/proj/FooBar.tsx"},
            "tool_response": None,
            "agent_response_text": None,
            "stop_reason": None,
            "paths": ["/proj/FooBar.tsx"],
            "command": None,
            "result_bytes": 0,
            "raw_event": {},
        },
        {
            "v": 1,
            "engine": "claude-code",
            "event_type": "post_tool",
            "session_id": sid,
            "ts": "2026-01-01T00:00:02.000+00:00",
            "cwd": "/p",
            "user_prompt_text": None,
            "tool_name": "Read",
            "tool_input": {"file_path": "/proj/FooBar.tsx"},
            "tool_response": "export const FooBar = () => <div>hi</div>",
            "agent_response_text": None,
            "stop_reason": None,
            "paths": ["/proj/FooBar.tsx"],
            "command": None,
            "result_bytes": 40,
            "raw_event": {},
        },
        {
            "v": 1,
            "engine": "claude-code",
            "event_type": "agent_response",
            "session_id": sid,
            "ts": "2026-01-01T00:00:03.000+00:00",
            "cwd": "/p",
            "user_prompt_text": None,
            "tool_name": None,
            "tool_input": None,
            "tool_response": None,
            "agent_response_text": "Found FooBar.tsx — looks good",
            "stop_reason": "end_turn",
            "paths": [],
            "command": None,
            "result_bytes": 0,
            "raw_event": {},
        },
    ]
    for e in events:
        append_event(e, data_dir=plugin_data_dir)


def test_grep_finds_user_prompt_match(plugin_data_dir):
    _seed(plugin_data_dir)
    buf = io.StringIO()
    n = grep("G1", "FooBar", data_dir=plugin_data_dir, stream=buf)
    out = buf.getvalue()
    assert "FooBar" in out
    assert n >= 1


def test_grep_finds_tool_response_match(plugin_data_dir):
    _seed(plugin_data_dir)
    buf = io.StringIO()
    grep("G1", "export const", data_dir=plugin_data_dir, stream=buf)
    out = buf.getvalue()
    assert "export const" in out
    assert "tool_response" in out


def test_grep_finds_paths_match(plugin_data_dir):
    _seed(plugin_data_dir)
    buf = io.StringIO()
    grep("G1", r"\.tsx$", data_dir=plugin_data_dir, stream=buf)
    out = buf.getvalue()
    assert ".tsx" in out


def test_grep_case_sensitive_default(plugin_data_dir):
    _seed(plugin_data_dir)
    buf = io.StringIO()
    n = grep("G1", "foobar", data_dir=plugin_data_dir, stream=buf)
    assert n == 0  # case-sensitive doesn't match "FooBar"


def test_grep_ignore_case(plugin_data_dir):
    _seed(plugin_data_dir)
    buf = io.StringIO()
    n = grep(
        "G1",
        "foobar",
        data_dir=plugin_data_dir,
        ignore_case=True,
        stream=buf,
    )
    assert n >= 1


def test_grep_no_match_returns_zero_and_empty(plugin_data_dir):
    _seed(plugin_data_dir)
    buf = io.StringIO()
    n = grep("G1", "nothing-matches-this", data_dir=plugin_data_dir, stream=buf)
    assert n == 0
    assert buf.getvalue() == ""


def test_grep_invalid_regex_raises_re_error(plugin_data_dir):
    _seed(plugin_data_dir)
    import pytest

    buf = io.StringIO()
    with pytest.raises(re.error):
        grep("G1", "(((", data_dir=plugin_data_dir, stream=buf)


def test_grep_emits_one_line_per_match(plugin_data_dir):
    _seed(plugin_data_dir)
    buf = io.StringIO()
    grep("G1", "FooBar", data_dir=plugin_data_dir, stream=buf)
    # Multiple events mention FooBar; we expect multiple match lines
    lines = [line for line in buf.getvalue().splitlines() if line.strip()]
    assert len(lines) >= 2


def test_grep_output_includes_event_type(plugin_data_dir):
    _seed(plugin_data_dir)
    buf = io.StringIO()
    grep("G1", "FooBar", data_dir=plugin_data_dir, stream=buf)
    out = buf.getvalue()
    # User prompt matches reference event_type=user_prompt
    assert "user_prompt" in out


def test_grep_returns_match_count(plugin_data_dir):
    _seed(plugin_data_dir)
    buf = io.StringIO()
    n = grep("G1", "FooBar", data_dir=plugin_data_dir, stream=buf)
    matched = [line for line in buf.getvalue().splitlines() if line.strip()]
    assert n == len(matched)
