"""Unit tests for query.trace — DESIGN §7.3.2.

Contract:

  trace(session_id, output_excerpt, *, data_dir=None, stream=...) -> dict

  Result dict:
    {
      "session_id": str,
      "output_excerpt": str,
      "first_mention_event": dict | None,
      "first_mention_ts": str | None,
      "user_prompt_source": {"event": dict, "matched": bool} | None,
      "read_sources": [
        {"event": dict, "path": str, "contains": bool},
        ...
      ],
      "hallucination_candidate": bool,
    }

  Also writes a human-readable causal trail to `stream`.

  - first_mention_event = the first agent_response containing the
    excerpt. None if no agent response mentions it.
  - user_prompt_source = the most-recent user_prompt before first_mention,
    with whether it mentioned the excerpt.
  - read_sources = every post_tool Read event before first_mention, with
    whether its tool_response contained the excerpt.
  - hallucination_candidate = True iff first_mention exists, no user
    prompt mentions it, and no read source contains it.
"""

from __future__ import annotations

import io

import pytest

from core.recorder import append_event
from query.trace import trace


def _event(**over):
    base = {
        "v": 1,
        "engine": "claude-code",
        "event_type": "user_prompt",
        "session_id": "T1",
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


def _seed_hallucination(plugin_data_dir):
    """User asked one thing, agent's response mentions something nobody
    introduced (no user prompt mention, no Read with that content)."""
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
            tool_input={"file_path": "/p/spec.md"},
            paths=["/p/spec.md"],
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="post_tool",
            ts="2026-01-01T00:00:02.000+00:00",
            tool_name="Read",
            tool_input={"file_path": "/p/spec.md"},
            paths=["/p/spec.md"],
            tool_response="FooBar should accept props for color and size",
            result_bytes=40,
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="agent_response",
            ts="2026-01-01T00:00:03.000+00:00",
            agent_response_text="I'll use a DI container approach for FooBar",
            stop_reason="end_turn",
        ),
        data_dir=plugin_data_dir,
    )


def _seed_grounded(plugin_data_dir):
    """The agent's response phrase is sourced — Read picked it up."""
    append_event(
        _event(
            event_type="user_prompt",
            ts="2026-01-01T00:00:00.000+00:00",
            user_prompt_text="Implement FooBar",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="post_tool",
            ts="2026-01-01T00:00:01.000+00:00",
            tool_name="Read",
            tool_input={"file_path": "/p/lib/di.ts"},
            paths=["/p/lib/di.ts"],
            tool_response="// Uses a DI container pattern for FooBar",
            result_bytes=42,
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="agent_response",
            ts="2026-01-01T00:00:02.000+00:00",
            agent_response_text="Found a DI container in lib/di.ts; FooBar will use it",
        ),
        data_dir=plugin_data_dir,
    )


def test_trace_finds_first_mention(plugin_data_dir):
    _seed_hallucination(plugin_data_dir)
    buf = io.StringIO()
    result = trace("T1", "DI container", data_dir=plugin_data_dir, stream=buf)
    assert result["first_mention_event"] is not None
    assert result["first_mention_event"]["event_type"] == "agent_response"
    assert result["first_mention_ts"] == "2026-01-01T00:00:03.000+00:00"


def test_trace_detects_hallucination_candidate(plugin_data_dir):
    """No user prompt or Read introduced "DI container", but agent said it."""
    _seed_hallucination(plugin_data_dir)
    buf = io.StringIO()
    result = trace("T1", "DI container", data_dir=plugin_data_dir, stream=buf)
    assert result["hallucination_candidate"] is True
    # Read /p/spec.md is recorded but its content does not contain target
    sources = result["read_sources"]
    assert len(sources) == 1
    assert sources[0]["path"] == "/p/spec.md"
    assert sources[0]["contains"] is False


def test_trace_grounded_phrase_is_not_hallucination(plugin_data_dir):
    _seed_grounded(plugin_data_dir)
    buf = io.StringIO()
    result = trace("T1", "DI container", data_dir=plugin_data_dir, stream=buf)
    assert result["hallucination_candidate"] is False
    sources = result["read_sources"]
    assert len(sources) == 1
    assert sources[0]["path"] == "/p/lib/di.ts"
    assert sources[0]["contains"] is True


def test_trace_user_prompt_source_captured(plugin_data_dir):
    """If the user themselves mentioned the phrase, surface that — it's
    not a hallucination either."""
    append_event(
        _event(
            event_type="user_prompt",
            ts="2026-01-01T00:00:00.000+00:00",
            user_prompt_text="Use a DI container please",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="agent_response",
            ts="2026-01-01T00:00:01.000+00:00",
            agent_response_text="OK, building with DI container",
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = trace("T1", "DI container", data_dir=plugin_data_dir, stream=buf)
    assert result["user_prompt_source"] is not None
    assert result["user_prompt_source"]["matched"] is True
    assert result["hallucination_candidate"] is False


def test_trace_excerpt_not_in_any_response(plugin_data_dir):
    _seed_hallucination(plugin_data_dir)
    buf = io.StringIO()
    result = trace("T1", "nothing-matches-this", data_dir=plugin_data_dir, stream=buf)
    assert result["first_mention_event"] is None
    assert result["hallucination_candidate"] is False
    out = buf.getvalue()
    assert "not found" in out.lower() or "no match" in out.lower()


def test_trace_writes_human_readable_output(plugin_data_dir):
    _seed_hallucination(plugin_data_dir)
    buf = io.StringIO()
    trace("T1", "DI container", data_dir=plugin_data_dir, stream=buf)
    out = buf.getvalue()
    assert "DI container" in out
    assert "first appeared" in out.lower() or "first mention" in out.lower()
    # Read file mentioned with ✓/✗-like indicator
    assert "/p/spec.md" in out


def test_trace_hallucination_warning_shown(plugin_data_dir):
    _seed_hallucination(plugin_data_dir)
    buf = io.StringIO()
    trace("T1", "DI container", data_dir=plugin_data_dir, stream=buf)
    out = buf.getvalue()
    # Warning marker should be visible in the rendered output
    assert "hallucination" in out.lower() or "⚠" in out


def test_trace_walks_only_events_before_first_mention(plugin_data_dir):
    """Events AFTER the first mention must not be classified as
    "sources" — the agent could not have read them yet."""
    _seed_hallucination(plugin_data_dir)
    # Add a Read AFTER the agent's response that does contain the phrase
    append_event(
        _event(
            event_type="post_tool",
            ts="2026-01-01T00:00:04.000+00:00",
            tool_name="Read",
            tool_input={"file_path": "/p/late.md"},
            paths=["/p/late.md"],
            tool_response="DI container reference",
            result_bytes=22,
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = trace("T1", "DI container", data_dir=plugin_data_dir, stream=buf)
    # Hallucination should still hold — the late Read happens after the
    # response and cannot be a source
    assert result["hallucination_candidate"] is True
    # And it should not appear in read_sources
    paths_listed = [s["path"] for s in result["read_sources"]]
    assert "/p/late.md" not in paths_listed


def test_trace_unknown_session(plugin_data_dir):
    from core.session_io import SessionNotFoundError

    with pytest.raises(SessionNotFoundError):
        trace("nope", "anything", data_dir=plugin_data_dir, stream=io.StringIO())


def test_trace_multiple_agent_responses_first_one_wins(plugin_data_dir):
    """If the phrase appears in multiple agent_response events, return
    the earliest."""
    append_event(
        _event(
            event_type="agent_response",
            ts="2026-01-01T00:00:01.000+00:00",
            agent_response_text="Initial DI container thought",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="agent_response",
            ts="2026-01-01T00:00:02.000+00:00",
            agent_response_text="Reaffirming DI container",
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = trace("T1", "DI container", data_dir=plugin_data_dir, stream=buf)
    assert result["first_mention_ts"] == "2026-01-01T00:00:01.000+00:00"


def test_trace_returns_session_id_and_excerpt_in_result(plugin_data_dir):
    _seed_hallucination(plugin_data_dir)
    buf = io.StringIO()
    result = trace("T1", "DI container", data_dir=plugin_data_dir, stream=buf)
    assert result["session_id"] == "T1"
    assert result["output_excerpt"] == "DI container"


def test_trace_paths_with_multiple_reads_of_same_file(plugin_data_dir):
    """Same file read multiple times → each Read event becomes its own
    entry in read_sources."""
    for i in range(3):
        append_event(
            _event(
                event_type="post_tool",
                ts=f"2026-01-01T00:00:0{i}.000+00:00",
                tool_name="Read",
                tool_input={"file_path": "/p/same.md"},
                paths=["/p/same.md"],
                tool_response="harmless content",
                result_bytes=16,
            ),
            data_dir=plugin_data_dir,
        )
    append_event(
        _event(
            event_type="agent_response",
            ts="2026-01-01T00:00:04.000+00:00",
            agent_response_text="DI container time",
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = trace("T1", "DI container", data_dir=plugin_data_dir, stream=buf)
    assert len(result["read_sources"]) == 3
    assert all(s["path"] == "/p/same.md" for s in result["read_sources"])
    assert all(s["contains"] is False for s in result["read_sources"])
    assert result["hallucination_candidate"] is True


def test_trace_user_prompt_source_is_most_recent_before_mention(plugin_data_dir):
    """If multiple user prompts exist before the mention, surface the
    most recent one (the immediate trigger)."""
    append_event(
        _event(
            event_type="user_prompt",
            ts="2026-01-01T00:00:00.000+00:00",
            user_prompt_text="early prompt with DI container in it",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="user_prompt",
            ts="2026-01-01T00:00:01.000+00:00",
            user_prompt_text="recent prompt without the phrase",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="agent_response",
            ts="2026-01-01T00:00:02.000+00:00",
            agent_response_text="Using DI container as discussed",
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = trace("T1", "DI container", data_dir=plugin_data_dir, stream=buf)
    # Most recent user_prompt before mention is the second one (no match)
    assert result["user_prompt_source"]["matched"] is False
    # But searching the whole session for any user mention should NOT
    # mark this as hallucination because the earlier prompt did
    # mention the phrase
    assert result["hallucination_candidate"] is False
