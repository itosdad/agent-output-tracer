"""Unit tests for query.why — DESIGN §7.3.3.

Contract:

  why(session_id, *, path=None, tool=None, ts=None, event_index=None,
      data_dir=None, stream=...) -> dict

  Identifies the target event by `--path` + optional `--tool` / `--ts`
  filters (or by `--event-index` for direct addressing). For the
  located event, returns / prints:

  - target event
  - immediately-preceding 3 events
  - the most-recent user_prompt before
  - "glob origin": a prior post_tool Glob whose tool_response contained
    the target's path (i.e. the agent picked this path from a Glob
    result without explicit user mention)

  Result dict:
    {
      "session_id": str,
      "target": dict | None,
      "preceding": [dict, ...],          # up to 3, oldest→newest
      "last_user_prompt": dict | None,
      "glob_origin": dict | None,
    }
"""

from __future__ import annotations

import io

import pytest

from core.recorder import append_event
from query.why import EventNotFound, why


def _event(**over):
    base = {
        "v": 1,
        "engine": "claude-code",
        "event_type": "pre_tool",
        "session_id": "W1",
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


def _seed_glob_then_read(plugin_data_dir):
    """Typical case: user asks → agent runs Glob → picks a result → Reads it."""
    append_event(
        _event(
            event_type="user_prompt",
            ts="2026-01-01T00:00:00.000+00:00",
            user_prompt_text="Implement the FooBar component",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="pre_tool",
            ts="2026-01-01T00:00:01.000+00:00",
            tool_name="Glob",
            tool_input={"pattern": "src/**/*.tsx"},
            paths=[],
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="post_tool",
            ts="2026-01-01T00:00:02.000+00:00",
            tool_name="Glob",
            tool_input={"pattern": "src/**/*.tsx"},
            paths=[],
            tool_response="/p/src/FooBar.tsx\n/p/src/lib/di.ts\n/p/src/utils.ts",
            result_bytes=50,
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="pre_tool",
            ts="2026-01-01T00:00:03.000+00:00",
            tool_name="Read",
            tool_input={"file_path": "/p/src/lib/di.ts"},
            paths=["/p/src/lib/di.ts"],
        ),
        data_dir=plugin_data_dir,
    )


def test_why_by_path_finds_event(plugin_data_dir):
    _seed_glob_then_read(plugin_data_dir)
    buf = io.StringIO()
    result = why("W1", path="/p/src/lib/di.ts", data_dir=plugin_data_dir, stream=buf)
    assert result["target"] is not None
    assert result["target"]["tool_name"] == "Read"
    assert result["target"]["paths"] == ["/p/src/lib/di.ts"]
    assert result["target"]["ts"] == "2026-01-01T00:00:03.000+00:00"


def test_why_detects_glob_origin(plugin_data_dir):
    _seed_glob_then_read(plugin_data_dir)
    buf = io.StringIO()
    result = why("W1", path="/p/src/lib/di.ts", data_dir=plugin_data_dir, stream=buf)
    assert result["glob_origin"] is not None
    assert result["glob_origin"]["tool_name"] == "Glob"
    assert result["glob_origin"]["tool_input"]["pattern"] == "src/**/*.tsx"


def test_why_returns_last_3_preceding(plugin_data_dir):
    _seed_glob_then_read(plugin_data_dir)
    buf = io.StringIO()
    result = why("W1", path="/p/src/lib/di.ts", data_dir=plugin_data_dir, stream=buf)
    # Preceding events (oldest→newest): user_prompt, Glob pre, Glob post
    assert len(result["preceding"]) == 3
    assert result["preceding"][0]["event_type"] == "user_prompt"
    assert result["preceding"][-1]["event_type"] == "post_tool"
    assert result["preceding"][-1]["tool_name"] == "Glob"


def test_why_finds_last_user_prompt(plugin_data_dir):
    _seed_glob_then_read(plugin_data_dir)
    buf = io.StringIO()
    result = why("W1", path="/p/src/lib/di.ts", data_dir=plugin_data_dir, stream=buf)
    assert result["last_user_prompt"] is not None
    assert "FooBar" in result["last_user_prompt"]["user_prompt_text"]


def test_why_no_glob_origin_when_user_supplied_path(plugin_data_dir):
    """User explicitly mentioned a path → Read it → no Glob involved."""
    append_event(
        _event(
            event_type="user_prompt",
            ts="2026-01-01T00:00:00.000+00:00",
            user_prompt_text="Read /p/explicit.md",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="pre_tool",
            ts="2026-01-01T00:00:01.000+00:00",
            tool_name="Read",
            tool_input={"file_path": "/p/explicit.md"},
            paths=["/p/explicit.md"],
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = why("W1", path="/p/explicit.md", data_dir=plugin_data_dir, stream=buf)
    assert result["target"] is not None
    assert result["glob_origin"] is None


def test_why_unknown_path_raises(plugin_data_dir):
    _seed_glob_then_read(plugin_data_dir)
    with pytest.raises(EventNotFound):
        why("W1", path="/p/never-touched.md", data_dir=plugin_data_dir, stream=io.StringIO())


def test_why_disambiguates_by_ts(plugin_data_dir):
    """Same path read twice → --ts picks one."""
    for i, ts in enumerate(["2026-01-01T00:00:01.000+00:00", "2026-01-01T00:00:05.000+00:00"]):
        append_event(
            _event(
                event_type="pre_tool",
                ts=ts,
                tool_name="Read",
                tool_input={"file_path": "/p/file.md"},
                paths=["/p/file.md"],
            ),
            data_dir=plugin_data_dir,
        )
    buf = io.StringIO()
    result = why(
        "W1",
        path="/p/file.md",
        ts="00:00:05",
        data_dir=plugin_data_dir,
        stream=buf,
    )
    assert result["target"]["ts"] == "2026-01-01T00:00:05.000+00:00"


def test_why_returns_first_match_when_ambiguous(plugin_data_dir):
    """Multiple Reads of same path without --ts → return first match."""
    for ts in ["2026-01-01T00:00:01.000+00:00", "2026-01-01T00:00:05.000+00:00"]:
        append_event(
            _event(
                event_type="pre_tool",
                ts=ts,
                tool_name="Read",
                tool_input={"file_path": "/p/file.md"},
                paths=["/p/file.md"],
            ),
            data_dir=plugin_data_dir,
        )
    buf = io.StringIO()
    result = why("W1", path="/p/file.md", data_dir=plugin_data_dir, stream=buf)
    assert result["target"]["ts"] == "2026-01-01T00:00:01.000+00:00"


def test_why_by_event_index(plugin_data_dir):
    _seed_glob_then_read(plugin_data_dir)
    buf = io.StringIO()
    # event_index=3 → the Read at 00:00:03 (0-based)
    result = why("W1", event_index=3, data_dir=plugin_data_dir, stream=buf)
    assert result["target"]["tool_name"] == "Read"


def test_why_event_index_out_of_range(plugin_data_dir):
    _seed_glob_then_read(plugin_data_dir)
    with pytest.raises(EventNotFound):
        why("W1", event_index=999, data_dir=plugin_data_dir, stream=io.StringIO())


def test_why_tool_filter(plugin_data_dir):
    """Same path appears in a Read and an Edit — --tool narrows down."""
    append_event(
        _event(
            event_type="pre_tool",
            ts="2026-01-01T00:00:01.000+00:00",
            tool_name="Read",
            tool_input={"file_path": "/p/x"},
            paths=["/p/x"],
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="pre_tool",
            ts="2026-01-01T00:00:02.000+00:00",
            tool_name="Edit",
            tool_input={"file_path": "/p/x"},
            paths=["/p/x"],
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = why("W1", path="/p/x", tool="Edit", data_dir=plugin_data_dir, stream=buf)
    assert result["target"]["tool_name"] == "Edit"


def test_why_writes_human_readable(plugin_data_dir):
    _seed_glob_then_read(plugin_data_dir)
    buf = io.StringIO()
    why("W1", path="/p/src/lib/di.ts", data_dir=plugin_data_dir, stream=buf)
    out = buf.getvalue()
    assert "/p/src/lib/di.ts" in out
    assert "FooBar" in out  # user prompt
    # Glob origin warning visible
    assert "Glob" in out and ("src/**/*.tsx" in out or "Glob result" in out.lower())


def test_why_requires_some_selector(plugin_data_dir):
    """Calling why without any selector (no path, no event_index, no tool)
    should be an error — there's nothing to look up."""
    _seed_glob_then_read(plugin_data_dir)
    with pytest.raises(EventNotFound):
        why("W1", data_dir=plugin_data_dir, stream=io.StringIO())


def test_why_unknown_session(plugin_data_dir):
    from core.session_io import SessionNotFoundError

    with pytest.raises(SessionNotFoundError):
        why("nope", path="/p/x", data_dir=plugin_data_dir, stream=io.StringIO())
