"""Unit tests for query.diff — DESIGN §7.3.4.

Contract:

  diff(session_id, *, data_dir=None, stream=...) -> dict

  Two-way asymmetric report on a session:

  Result dict:
    {
      "session_id": str,
      "user_mentioned_not_touched": [str, ...],
      "agent_touched_no_mention":   [str, ...],
    }

  - `user_mentioned_not_touched`: path-like tokens that appear in any
    user_prompt but are not (by full-path or basename) among the
    agent's touched paths.
  - `agent_touched_no_mention`: paths the agent touched (pre_tool) where
    neither the full path nor the basename appears anywhere in user
    prompt text.

  Matching is intentionally loose on basenames to avoid false positives
  on "user said 'foo.md' → agent read '/proj/foo.md'" (clearly served).
"""

from __future__ import annotations

import io

from core.recorder import append_event
from query.diff import diff


def _event(**over):
    base = {
        "v": 1,
        "engine": "claude-code",
        "event_type": "user_prompt",
        "session_id": "D1",
        "ts": "2026-01-01T00:00:00.000+00:00",
        "cwd": "/p",
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
    base.update(over)
    return base


def test_diff_user_mentioned_but_not_touched(plugin_data_dir):
    """User asks the agent to read foo.md, but the agent never does."""
    append_event(
        _event(
            event_type="user_prompt",
            ts="2026-01-01T00:00:00.000+00:00",
            user_prompt_text="Please read /proj/foo.md and summarize",
        ),
        data_dir=plugin_data_dir,
    )
    # No pre_tool events at all — agent didn't touch anything

    buf = io.StringIO()
    result = diff("D1", data_dir=plugin_data_dir, stream=buf)
    assert "/proj/foo.md" in result["user_mentioned_not_touched"]
    assert result["agent_touched_no_mention"] == []


def test_diff_agent_touched_without_user_mention(plugin_data_dir):
    """Agent reads a file the user never mentioned."""
    append_event(
        _event(
            event_type="user_prompt",
            ts="2026-01-01T00:00:00.000+00:00",
            user_prompt_text="Implement FooBar component",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="pre_tool",
            ts="2026-01-01T00:00:01.000+00:00",
            tool_name="Read",
            tool_input={"file_path": "/proj/secrets.env"},
            paths=["/proj/secrets.env"],
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = diff("D1", data_dir=plugin_data_dir, stream=buf)
    assert "/proj/secrets.env" in result["agent_touched_no_mention"]
    # User_mentioned_not_touched may or may not contain "FooBar" if it
    # parses as a reference, but the test target is the touch side.


def test_diff_basename_match_counts_as_served(plugin_data_dir):
    """User says 'foo.md', agent touches '/proj/foo.md' — served by
    basename match. Neither side flagged."""
    append_event(
        _event(
            event_type="user_prompt",
            ts="2026-01-01T00:00:00.000+00:00",
            user_prompt_text="Read foo.md please",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="pre_tool",
            ts="2026-01-01T00:00:01.000+00:00",
            tool_name="Read",
            tool_input={"file_path": "/proj/foo.md"},
            paths=["/proj/foo.md"],
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = diff("D1", data_dir=plugin_data_dir, stream=buf)
    assert result["user_mentioned_not_touched"] == []
    assert result["agent_touched_no_mention"] == []


def test_diff_substring_not_mistaken_for_basename(plugin_data_dir):
    """User says 'log.py', agent touches '/proj/dialog.py' — basenames
    differ, the touch is unprompted."""
    append_event(
        _event(
            event_type="user_prompt",
            ts="2026-01-01T00:00:00.000+00:00",
            user_prompt_text="Update log.py to add tracing",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="pre_tool",
            ts="2026-01-01T00:00:01.000+00:00",
            tool_name="Read",
            tool_input={"file_path": "/proj/dialog.py"},
            paths=["/proj/dialog.py"],
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = diff("D1", data_dir=plugin_data_dir, stream=buf)
    assert "/proj/dialog.py" in result["agent_touched_no_mention"]
    assert "log.py" in result["user_mentioned_not_touched"]


def test_diff_both_sides_clean(plugin_data_dir):
    """User mentions a path, agent reads it — clean diff."""
    append_event(
        _event(
            event_type="user_prompt",
            ts="2026-01-01T00:00:00.000+00:00",
            user_prompt_text="Read /proj/foo.md",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="pre_tool",
            ts="2026-01-01T00:00:01.000+00:00",
            tool_name="Read",
            tool_input={"file_path": "/proj/foo.md"},
            paths=["/proj/foo.md"],
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = diff("D1", data_dir=plugin_data_dir, stream=buf)
    assert result["user_mentioned_not_touched"] == []
    assert result["agent_touched_no_mention"] == []


def test_diff_writes_human_readable(plugin_data_dir):
    append_event(
        _event(
            event_type="user_prompt",
            ts="2026-01-01T00:00:00.000+00:00",
            user_prompt_text="Read /a.md but not /b.md",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="pre_tool",
            ts="2026-01-01T00:00:01.000+00:00",
            tool_name="Read",
            tool_input={"file_path": "/a.md"},
            paths=["/a.md"],
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="pre_tool",
            ts="2026-01-01T00:00:02.000+00:00",
            tool_name="Read",
            tool_input={"file_path": "/secret"},
            paths=["/secret"],
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    diff("D1", data_dir=plugin_data_dir, stream=buf)
    out = buf.getvalue()
    # Both sections present, with the right contents.
    assert "User mentioned but agent did NOT" in out or "user mentioned" in out.lower()
    assert "Agent accessed without" in out or "no mention" in out.lower()
    assert "/secret" in out


def test_diff_empty_session_returns_empty_diff(plugin_data_dir):
    """A session with no events should produce empty result lists,
    not crash."""
    sdir = plugin_data_dir / "sessions" / "empty"
    sdir.mkdir(parents=True)
    (sdir / "events.jsonl").write_text("")
    buf = io.StringIO()
    result = diff("empty", data_dir=plugin_data_dir, stream=buf)
    assert result["user_mentioned_not_touched"] == []
    assert result["agent_touched_no_mention"] == []


def test_diff_includes_bash_paths_too(plugin_data_dir):
    """Bash commands may not surface a 'path', so paths=[] for Bash.
    That's fine — diff only considers explicit paths."""
    append_event(
        _event(
            event_type="user_prompt",
            ts="2026-01-01T00:00:00.000+00:00",
            user_prompt_text="Run ls",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="pre_tool",
            ts="2026-01-01T00:00:01.000+00:00",
            tool_name="Bash",
            tool_input={"command": "ls /tmp"},
            paths=[],
            command="ls /tmp",
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = diff("D1", data_dir=plugin_data_dir, stream=buf)
    # No explicit paths in Bash → nothing on touched side
    assert result["agent_touched_no_mention"] == []


def test_diff_deduplicates(plugin_data_dir):
    """Same path read multiple times → appears once in the touched set."""
    append_event(
        _event(
            event_type="user_prompt",
            ts="2026-01-01T00:00:00.000+00:00",
            user_prompt_text="Implement",
        ),
        data_dir=plugin_data_dir,
    )
    for ts in ("2026-01-01T00:00:01.000+00:00", "2026-01-01T00:00:02.000+00:00"):
        append_event(
            _event(
                event_type="pre_tool",
                ts=ts,
                tool_name="Read",
                tool_input={"file_path": "/p/x"},
                paths=["/p/x"],
            ),
            data_dir=plugin_data_dir,
        )
    buf = io.StringIO()
    result = diff("D1", data_dir=plugin_data_dir, stream=buf)
    assert result["agent_touched_no_mention"].count("/p/x") == 1


def test_diff_unknown_session(plugin_data_dir):
    import pytest

    from core.session_io import SessionNotFoundError

    with pytest.raises(SessionNotFoundError):
        diff("nope", data_dir=plugin_data_dir, stream=io.StringIO())


def test_diff_quoted_paths_in_user_prompt(plugin_data_dir):
    """Path mentioned in single/double quotes — still extracted."""
    append_event(
        _event(
            event_type="user_prompt",
            ts="2026-01-01T00:00:00.000+00:00",
            user_prompt_text="Read \"/proj/quoted.md\" and '~/other.md'",
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = diff("D1", data_dir=plugin_data_dir, stream=buf)
    # both mentioned paths surface as unserved
    serialized = " ".join(result["user_mentioned_not_touched"])
    assert "quoted.md" in serialized
    assert "other.md" in serialized
