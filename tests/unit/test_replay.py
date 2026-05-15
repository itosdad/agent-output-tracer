"""Unit tests for query.replay — the timeline renderer."""

from __future__ import annotations

import io
import json

import pytest

from core.recorder import append_event
from query.replay import replay


def _seed_basic_session(plugin_data_dir, sid="S1"):
    def ev(et, **extra):
        e = {
            "v": 1,
            "engine": "claude-code",
            "event_type": et,
            "session_id": sid,
            "ts": extra.pop("ts", "2026-01-01T00:00:00.000+00:00"),
            "cwd": "/proj",
            "user_prompt_text": None,
            "tool_name": None,
            "tool_input": None,
            "tool_response": None,
            "agent_response_text": None,
            "stop_reason": None,
            "paths": [],
            "command": None,
            "result_bytes": 0,
            "raw_event": {},
        }
        e.update(extra)
        return e

    append_event(
        ev("user_prompt", user_prompt_text="Read foo.md", ts="2026-01-01T00:00:00.000+00:00"),
        data_dir=plugin_data_dir,
    )
    append_event(
        ev(
            "pre_tool",
            tool_name="Read",
            tool_input={"file_path": "/proj/foo.md"},
            paths=["/proj/foo.md"],
            ts="2026-01-01T00:00:01.000+00:00",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        ev(
            "post_tool",
            tool_name="Read",
            tool_input={"file_path": "/proj/foo.md"},
            paths=["/proj/foo.md"],
            tool_response="hello",
            result_bytes=5,
            ts="2026-01-01T00:00:02.000+00:00",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        ev(
            "agent_response",
            agent_response_text="Done. foo says hello",
            stop_reason="end_turn",
            ts="2026-01-01T00:00:03.000+00:00",
        ),
        data_dir=plugin_data_dir,
    )


def test_replay_text_format_shows_all_events_in_order(plugin_data_dir):
    _seed_basic_session(plugin_data_dir)
    buf = io.StringIO()
    replay("S1", data_dir=plugin_data_dir, stream=buf)
    out = buf.getvalue()
    # All event-line markers appear
    assert "[user]" in out
    assert "[tool]" in out
    assert "[agent]" in out
    # In timeline order (the markers, not arbitrary substrings)
    assert out.index("[user]") < out.index("[tool]") < out.index("[agent]")


def test_replay_includes_session_header(plugin_data_dir):
    _seed_basic_session(plugin_data_dir)
    buf = io.StringIO()
    replay("S1", data_dir=plugin_data_dir, stream=buf)
    out = buf.getvalue()
    assert "S1" in out
    assert "events" in out.lower()


def test_replay_text_shows_truncated_user_prompt(plugin_data_dir):
    """Long user prompts are truncated for the timeline view."""
    long_prompt = "a" * 500
    append_event(
        {
            "v": 1,
            "engine": "claude-code",
            "event_type": "user_prompt",
            "session_id": "long",
            "ts": "2026-01-01T00:00:00.000+00:00",
            "cwd": "/p",
            "user_prompt_text": long_prompt,
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
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    replay("long", data_dir=plugin_data_dir, stream=buf)
    out = buf.getvalue()
    # Default truncation cap — the full 500-char prompt should NOT be
    # in the output verbatim.
    assert long_prompt not in out
    # But some of the prompt should be there.
    assert "a" * 50 in out


def test_replay_json_format(plugin_data_dir):
    _seed_basic_session(plugin_data_dir)
    buf = io.StringIO()
    replay("S1", data_dir=plugin_data_dir, fmt="json", stream=buf)
    parsed = json.loads(buf.getvalue())
    assert parsed["session_id"] == "S1"
    assert len(parsed["events"]) == 4
    assert parsed["events"][0]["event_type"] == "user_prompt"


def test_replay_markdown_format(plugin_data_dir):
    _seed_basic_session(plugin_data_dir)
    buf = io.StringIO()
    replay("S1", data_dir=plugin_data_dir, fmt="markdown", stream=buf)
    out = buf.getvalue()
    assert "# Session" in out
    assert "S1" in out
    # Markdown style: each event becomes a row / list item
    assert "user_prompt" in out or "user prompt" in out.lower()


def test_replay_unknown_session(plugin_data_dir):
    from core.session_io import SessionNotFoundError

    with pytest.raises(SessionNotFoundError):
        replay("does-not-exist", data_dir=plugin_data_dir)


def test_replay_shows_bash_command(plugin_data_dir):
    append_event(
        {
            "v": 1,
            "engine": "claude-code",
            "event_type": "pre_tool",
            "session_id": "bash",
            "ts": "2026-01-01T00:00:00.000+00:00",
            "cwd": "/p",
            "user_prompt_text": None,
            "tool_name": "Bash",
            "tool_input": {"command": "ls /tmp"},
            "tool_response": None,
            "agent_response_text": None,
            "stop_reason": None,
            "paths": [],
            "command": "ls /tmp",
            "result_bytes": 0,
            "raw_event": {},
        },
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    replay("bash", data_dir=plugin_data_dir, stream=buf)
    out = buf.getvalue()
    assert "ls /tmp" in out


def test_replay_shows_result_bytes(plugin_data_dir):
    _seed_basic_session(plugin_data_dir)
    buf = io.StringIO()
    replay("S1", data_dir=plugin_data_dir, stream=buf)
    out = buf.getvalue()
    # 5 bytes ("hello") shown human-readably as "5 B" or similar
    assert "5" in out


def test_replay_returns_zero_for_empty_session(plugin_data_dir):
    """A session dir that exists but has no events should not crash."""
    sdir = plugin_data_dir / "sessions" / "empty"
    sdir.mkdir(parents=True)
    (sdir / "events.jsonl").write_text("")
    (sdir / "metadata.json").write_text(
        json.dumps({"v": 1, "session_id": "empty", "engine": "claude-code", "tags": []})
    )
    buf = io.StringIO()
    replay("empty", data_dir=plugin_data_dir, stream=buf)
    out = buf.getvalue()
    assert "empty" in out
