"""Unit tests for query.state_at — snapshot of session state at time T."""

from __future__ import annotations

import io

import pytest

from core.recorder import append_event
from query.state_at import state_at


def _push(plugin_data_dir, sid="SA"):
    """Push: user @00s, read /a @01s (10b), read /b @02s (20b), read /a @03s (10b),
    user @04s, read /a @05s (10b)."""

    def base(**over):
        e = {
            "v": 1,
            "engine": "claude-code",
            "event_type": "post_tool",
            "session_id": sid,
            "ts": "2026-05-14T10:00:00.000+00:00",
            "cwd": "/p",
            "user_prompt_text": None,
            "tool_name": "Read",
            "tool_input": {"file_path": "/a"},
            "tool_response": None,
            "agent_response_text": None,
            "stop_reason": None,
            "paths": ["/a"],
            "command": None,
            "result_bytes": 10,
            "raw_event": {},
        }
        e.update(over)
        return e

    append_event(
        base(
            event_type="user_prompt",
            ts="2026-05-14T10:00:00.000+00:00",
            tool_name=None,
            tool_input=None,
            paths=[],
            user_prompt_text="first",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        base(ts="2026-05-14T10:00:01.000+00:00", paths=["/a"], result_bytes=10),
        data_dir=plugin_data_dir,
    )
    append_event(
        base(
            ts="2026-05-14T10:00:02.000+00:00",
            paths=["/b"],
            tool_input={"file_path": "/b"},
            result_bytes=20,
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        base(ts="2026-05-14T10:00:03.000+00:00", paths=["/a"], result_bytes=10),
        data_dir=plugin_data_dir,
    )
    append_event(
        base(
            event_type="user_prompt",
            ts="2026-05-14T10:00:04.000+00:00",
            tool_name=None,
            tool_input=None,
            paths=[],
            user_prompt_text="second",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        base(ts="2026-05-14T10:00:05.000+00:00", paths=["/a"], result_bytes=10),
        data_dir=plugin_data_dir,
    )


def test_state_at_iso_truncates(plugin_data_dir):
    _push(plugin_data_dir)
    buf = io.StringIO()
    # As of 10:00:03 we've seen: user@00, read/a@01 (10b), read/b@02 (20b),
    # read/a@03 (10b). So 3 reads total, 2 unique files, 40 bytes.
    state_at("SA", "2026-05-14T10:00:03+00:00", data_dir=plugin_data_dir, stream=buf)
    out = buf.getvalue()
    assert "2 unique" in out
    assert "3 total" in out
    assert "40" in out  # bytes
    assert "/a" in out and "/b" in out


def test_state_at_after_all_events(plugin_data_dir):
    _push(plugin_data_dir)
    buf = io.StringIO()
    state_at("SA", "2026-05-14T11:00:00+00:00", data_dir=plugin_data_dir, stream=buf)
    out = buf.getvalue()
    # All 4 reads counted: 3x /a + 1x /b
    assert "2 unique" in out
    assert "4 total" in out


def test_state_at_before_any_event(plugin_data_dir):
    _push(plugin_data_dir)
    buf = io.StringIO()
    state_at("SA", "2026-01-01T00:00:00+00:00", data_dir=plugin_data_dir, stream=buf)
    out = buf.getvalue()
    assert "0 unique" in out
    assert "0 total" in out or "0 reads" in out.lower()


def test_state_at_time_of_day_form(plugin_data_dir):
    _push(plugin_data_dir)
    buf = io.StringIO()
    # HH:MM:SS — interpreted against session date (2026-05-14)
    state_at("SA", "10:00:02", data_dir=plugin_data_dir, stream=buf)
    out = buf.getvalue()
    # As of 10:00:02 we've seen: 2 reads (/a + /b) = 30 bytes
    assert "30" in out


def test_state_at_latest_keyword(plugin_data_dir):
    _push(plugin_data_dir)
    buf = io.StringIO()
    state_at("SA", "latest", data_dir=plugin_data_dir, stream=buf)
    out = buf.getvalue()
    assert "2 unique" in out
    assert "4 total" in out


def test_state_at_repeated_read_flag(plugin_data_dir):
    _push(plugin_data_dir)
    buf = io.StringIO()
    state_at("SA", "latest", data_dir=plugin_data_dir, stream=buf)
    out = buf.getvalue()
    # /a is read 3 times — flagged
    assert "/a" in out
    # Look for repeat marker (the design uses ⚠️ repeated)
    assert "repeated" in out.lower() or "⚠" in out


def test_state_at_invalid_time_raises(plugin_data_dir):
    _push(plugin_data_dir)
    buf = io.StringIO()
    with pytest.raises(ValueError):
        state_at("SA", "not-a-time", data_dir=plugin_data_dir, stream=buf)


def test_state_at_user_prompt_count(plugin_data_dir):
    _push(plugin_data_dir)
    buf = io.StringIO()
    state_at("SA", "latest", data_dir=plugin_data_dir, stream=buf)
    out = buf.getvalue()
    assert "2" in out  # two user prompts


def test_state_at_unknown_session(plugin_data_dir):
    from core.session_io import SessionNotFoundError

    with pytest.raises(SessionNotFoundError):
        state_at("nope", "latest", data_dir=plugin_data_dir, stream=io.StringIO())
