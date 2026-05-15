"""Unit tests for query.export — DESIGN §7.4 (forensic report bundle)."""

from __future__ import annotations

import io

import pytest

from core.recorder import append_event
from query.export import export_trace


def _event(**over):
    base = {
        "v": 1,
        "engine": "claude-code",
        "event_type": "user_prompt",
        "session_id": "X1",
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


def _seed_rich(plugin_data_dir):
    append_event(
        _event(
            event_type="user_prompt",
            ts="2026-01-01T00:00:00.000+00:00",
            user_prompt_text="Implement based on /p/spec.md",
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
            tool_response="some content",
            result_bytes=12,
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="agent_response",
            ts="2026-01-01T00:00:03.000+00:00",
            agent_response_text="referencing /p/ghost.md (no source!)",
        ),
        data_dir=plugin_data_dir,
    )


def test_export_bundle_contains_all_sections(plugin_data_dir):
    _seed_rich(plugin_data_dir)
    buf = io.StringIO()
    export_trace("X1", data_dir=plugin_data_dir, stream=buf)
    out = buf.getvalue()
    # Heading-based sections we promise to produce
    assert "# Forensic report:" in out or "# Session" in out
    assert "## Timeline" in out
    assert "## User vs agent" in out or "## Diff" in out
    assert "## Hallucination candidates" in out or "## mentioned-but-not-read" in out
    assert "## Causal graph" in out
    assert "```mermaid" in out


def test_export_to_file(plugin_data_dir, tmp_path):
    _seed_rich(plugin_data_dir)
    out_file = tmp_path / "report.md"
    export_trace("X1", data_dir=plugin_data_dir, output_path=out_file, stream=io.StringIO())
    assert out_file.exists()
    text = out_file.read_text()
    assert "## Timeline" in text
    assert "/p/spec.md" in text


def test_export_empty_session(plugin_data_dir):
    sdir = plugin_data_dir / "sessions" / "empty"
    sdir.mkdir(parents=True)
    (sdir / "events.jsonl").write_text("")
    buf = io.StringIO()
    export_trace("empty", data_dir=plugin_data_dir, stream=buf)
    out = buf.getvalue()
    # Doesn't crash; all sections present even if some are empty.
    assert "## Timeline" in out


def test_export_unknown_session(plugin_data_dir):
    from core.session_io import SessionNotFoundError

    with pytest.raises(SessionNotFoundError):
        export_trace("nope", data_dir=plugin_data_dir, stream=io.StringIO())


def test_export_mentions_hallucination_candidate(plugin_data_dir):
    _seed_rich(plugin_data_dir)
    buf = io.StringIO()
    export_trace("X1", data_dir=plugin_data_dir, stream=buf)
    out = buf.getvalue()
    # /p/ghost.md was mentioned by the agent with no source → should
    # appear in the hallucination section
    assert "/p/ghost.md" in out


def test_export_returns_summary(plugin_data_dir):
    _seed_rich(plugin_data_dir)
    buf = io.StringIO()
    result = export_trace("X1", data_dir=plugin_data_dir, stream=buf)
    assert result["session_id"] == "X1"
    assert result["sections"] == ["timeline", "diff", "mentioned", "causal"]
    assert isinstance(result["report"], str)
    assert "## Timeline" in result["report"]
