"""Unit tests for query.mentioned_but_not_read — DESIGN §7.3.8.

Session-level hallucination candidate extractor:
- pull path-like tokens from every agent_response
- for each token, check whether it appears in any user_prompt_text
  or any tool_response
- return tokens with no such grounding

Result:
  {
    "session_id": str,
    "candidates": [
      {"token": str, "first_seen_ts": str, "first_seen_event": dict},
      ...
    ],
  }
"""

from __future__ import annotations

import io

from core.recorder import append_event
from query.mentioned_but_not_read import mentioned_but_not_read


def _event(**over):
    base = {
        "v": 1,
        "engine": "claude-code",
        "event_type": "user_prompt",
        "session_id": "M1",
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


def test_token_with_no_source_is_candidate(plugin_data_dir):
    """Agent says '/proj/ghost.md' that nobody ever introduced → candidate."""
    append_event(
        _event(
            event_type="user_prompt",
            ts="2026-01-01T00:00:00.000+00:00",
            user_prompt_text="implement something",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="agent_response",
            ts="2026-01-01T00:00:01.000+00:00",
            agent_response_text="I'll start by reading /proj/ghost.md",
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = mentioned_but_not_read("M1", data_dir=plugin_data_dir, stream=buf)
    tokens = [c["token"] for c in result["candidates"]]
    assert "/proj/ghost.md" in tokens


def test_token_grounded_in_user_prompt_excluded(plugin_data_dir):
    append_event(
        _event(
            event_type="user_prompt",
            ts="2026-01-01T00:00:00.000+00:00",
            user_prompt_text="Read /proj/spec.md",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="agent_response",
            ts="2026-01-01T00:00:01.000+00:00",
            agent_response_text="Reading /proj/spec.md now",
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = mentioned_but_not_read("M1", data_dir=plugin_data_dir, stream=buf)
    tokens = [c["token"] for c in result["candidates"]]
    assert "/proj/spec.md" not in tokens


def test_token_grounded_in_tool_response_excluded(plugin_data_dir):
    append_event(
        _event(
            event_type="user_prompt",
            ts="2026-01-01T00:00:00.000+00:00",
            user_prompt_text="explore",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="post_tool",
            ts="2026-01-01T00:00:01.000+00:00",
            tool_name="Glob",
            tool_input={"pattern": "**/*.md"},
            tool_response="/proj/found.md\n/proj/other.md",
            result_bytes=30,
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="agent_response",
            ts="2026-01-01T00:00:02.000+00:00",
            agent_response_text="I see /proj/found.md and /proj/other.md",
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = mentioned_but_not_read("M1", data_dir=plugin_data_dir, stream=buf)
    tokens = [c["token"] for c in result["candidates"]]
    assert "/proj/found.md" not in tokens
    assert "/proj/other.md" not in tokens


def test_multiple_candidates_returned(plugin_data_dir):
    append_event(
        _event(
            event_type="user_prompt",
            ts="2026-01-01T00:00:00.000+00:00",
            user_prompt_text="do stuff",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="agent_response",
            ts="2026-01-01T00:00:01.000+00:00",
            agent_response_text="Need /proj/a.md and /proj/b.ts and /proj/c.py",
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = mentioned_but_not_read("M1", data_dir=plugin_data_dir, stream=buf)
    tokens = [c["token"] for c in result["candidates"]]
    assert "/proj/a.md" in tokens
    assert "/proj/b.ts" in tokens
    assert "/proj/c.py" in tokens


def test_candidate_has_first_seen_event(plugin_data_dir):
    """The result records which agent_response event first mentioned the token."""
    append_event(
        _event(
            event_type="agent_response",
            ts="2026-01-01T00:00:01.000+00:00",
            agent_response_text="early mention: /proj/x.md",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="agent_response",
            ts="2026-01-01T00:00:02.000+00:00",
            agent_response_text="repeated /proj/x.md mention",
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = mentioned_but_not_read("M1", data_dir=plugin_data_dir, stream=buf)
    cands = [c for c in result["candidates"] if c["token"] == "/proj/x.md"]
    assert len(cands) == 1
    assert cands[0]["first_seen_ts"] == "2026-01-01T00:00:01.000+00:00"


def test_no_agent_responses_returns_empty(plugin_data_dir):
    append_event(
        _event(
            event_type="user_prompt",
            ts="2026-01-01T00:00:00.000+00:00",
            user_prompt_text="just a prompt",
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = mentioned_but_not_read("M1", data_dir=plugin_data_dir, stream=buf)
    assert result["candidates"] == []


def test_no_candidates_clean_output(plugin_data_dir):
    """All paths agent mentions are grounded → clean output, no candidates."""
    append_event(
        _event(
            event_type="user_prompt",
            ts="2026-01-01T00:00:00.000+00:00",
            user_prompt_text="Read /proj/a.md",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="agent_response",
            ts="2026-01-01T00:00:01.000+00:00",
            agent_response_text="OK reading /proj/a.md",
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = mentioned_but_not_read("M1", data_dir=plugin_data_dir, stream=buf)
    assert result["candidates"] == []
    out = buf.getvalue()
    assert "(none" in out.lower() or "no hallucination" in out.lower()


def test_writes_human_readable(plugin_data_dir):
    append_event(
        _event(
            event_type="agent_response",
            ts="2026-01-01T00:00:01.000+00:00",
            agent_response_text="Talking about /proj/ghost.md",
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    mentioned_but_not_read("M1", data_dir=plugin_data_dir, stream=buf)
    out = buf.getvalue()
    assert "/proj/ghost.md" in out
    assert "hallucination" in out.lower() or "candidate" in out.lower()


def test_trailing_slash_token_grounded_by_user_mention(plugin_data_dir):
    """Regression: agent says `~/proj/hooks/` (trailing slash), user
    said `~/proj/hooks` (no slash) — grounding must succeed despite
    os.path.basename returning empty for trailing-slash paths."""
    append_event(
        _event(
            event_type="user_prompt",
            ts="2026-01-01T00:00:00.000+00:00",
            user_prompt_text="explore ~/proj/hooks for python files",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="agent_response",
            ts="2026-01-01T00:00:01.000+00:00",
            agent_response_text="Found 6 files under ~/proj/hooks/",
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = mentioned_but_not_read("M1", data_dir=plugin_data_dir, stream=buf)
    tokens = [c["token"] for c in result["candidates"]]
    assert "~/proj/hooks/" not in tokens
    assert "~/proj/hooks" not in tokens


def test_basename_in_user_prompt_grounds_token(plugin_data_dir):
    """User said 'foo.md', agent said '/proj/foo.md' — grounded by basename."""
    append_event(
        _event(
            event_type="user_prompt",
            ts="2026-01-01T00:00:00.000+00:00",
            user_prompt_text="Open foo.md",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="agent_response",
            ts="2026-01-01T00:00:01.000+00:00",
            agent_response_text="Opened /proj/foo.md",
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = mentioned_but_not_read("M1", data_dir=plugin_data_dir, stream=buf)
    tokens = [c["token"] for c in result["candidates"]]
    assert "/proj/foo.md" not in tokens


def test_unknown_session(plugin_data_dir):
    import pytest

    from core.session_io import SessionNotFoundError

    with pytest.raises(SessionNotFoundError):
        mentioned_but_not_read("nope", data_dir=plugin_data_dir, stream=io.StringIO())


def test_returns_list_sorted_by_first_seen_ts(plugin_data_dir):
    """Candidates should come back ordered by when the agent first
    mentioned each one (earliest first), so the user sees them in the
    same order as the timeline."""
    append_event(
        _event(
            event_type="agent_response",
            ts="2026-01-01T00:00:01.000+00:00",
            agent_response_text="mentioning /proj/late.md",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="agent_response",
            ts="2026-01-01T00:00:02.000+00:00",
            agent_response_text="and /proj/aaa.md",
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = mentioned_but_not_read("M1", data_dir=plugin_data_dir, stream=buf)
    tokens = [c["token"] for c in result["candidates"]]
    # Chronological order (timestamp order), not alphabetical
    assert tokens.index("/proj/late.md") < tokens.index("/proj/aaa.md")
