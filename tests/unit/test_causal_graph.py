"""Unit tests for query.causal_graph — DESIGN §7.3.7.

Contract:
  causal_graph(session_id, *, data_dir=None, output_path=None, stream=...)
    → dict {"session_id": str, "node_count": int, "edge_count": int,
            "dashed_edge_count": int, "mermaid": str}

  - One node per event, labeled with a short description.
  - Linear edge E{i-1} --> E{i} between consecutive events.
  - Dashed edge E{glob_idx} -.->|returned this path| E{read_idx}
    when a Read's path appears in a prior Glob's tool_response.
  - Output: markdown ```mermaid``` fenced block.
  - If output_path is given, write to that file. Otherwise write to stream.
"""

from __future__ import annotations

import io

from core.recorder import append_event
from query.causal_graph import causal_graph


def _event(**over):
    base = {
        "v": 1,
        "engine": "claude-code",
        "event_type": "user_prompt",
        "session_id": "C1",
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


def _seed_glob_read(plugin_data_dir):
    append_event(
        _event(
            event_type="user_prompt", ts="2026-01-01T00:00:00.000+00:00", user_prompt_text="hello"
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="pre_tool",
            ts="2026-01-01T00:00:01.000+00:00",
            tool_name="Glob",
            tool_input={"pattern": "src/**/*.tsx"},
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="post_tool",
            ts="2026-01-01T00:00:02.000+00:00",
            tool_name="Glob",
            tool_input={"pattern": "src/**/*.tsx"},
            tool_response="/p/foo.tsx\n/p/bar.tsx",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="pre_tool",
            ts="2026-01-01T00:00:03.000+00:00",
            tool_name="Read",
            tool_input={"file_path": "/p/foo.tsx"},
            paths=["/p/foo.tsx"],
        ),
        data_dir=plugin_data_dir,
    )


def test_causal_graph_has_one_node_per_event(plugin_data_dir):
    _seed_glob_read(plugin_data_dir)
    buf = io.StringIO()
    result = causal_graph("C1", data_dir=plugin_data_dir, stream=buf)
    assert result["node_count"] == 4


def test_causal_graph_linear_edges(plugin_data_dir):
    _seed_glob_read(plugin_data_dir)
    buf = io.StringIO()
    result = causal_graph("C1", data_dir=plugin_data_dir, stream=buf)
    # 4 events → 3 linear edges
    assert result["edge_count"] == 3


def test_causal_graph_dashed_edge_for_glob_read(plugin_data_dir):
    _seed_glob_read(plugin_data_dir)
    buf = io.StringIO()
    result = causal_graph("C1", data_dir=plugin_data_dir, stream=buf)
    assert result["dashed_edge_count"] == 1
    assert "-.->|returned this path|" in result["mermaid"]


def test_causal_graph_no_dashed_when_no_glob(plugin_data_dir):
    append_event(
        _event(
            event_type="pre_tool",
            ts="2026-01-01T00:00:00.000+00:00",
            tool_name="Read",
            tool_input={"file_path": "/p/foo"},
            paths=["/p/foo"],
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = causal_graph("C1", data_dir=plugin_data_dir, stream=buf)
    assert result["dashed_edge_count"] == 0


def test_causal_graph_mermaid_fence(plugin_data_dir):
    _seed_glob_read(plugin_data_dir)
    buf = io.StringIO()
    causal_graph("C1", data_dir=plugin_data_dir, stream=buf)
    out = buf.getvalue()
    assert "```mermaid" in out
    assert "```" in out.split("```mermaid", 1)[1]
    assert "graph TD" in out


def test_causal_graph_writes_to_output_path(plugin_data_dir, tmp_path):
    _seed_glob_read(plugin_data_dir)
    out_file = tmp_path / "graph.md"
    causal_graph("C1", data_dir=plugin_data_dir, output_path=out_file, stream=io.StringIO())
    assert out_file.exists()
    text = out_file.read_text()
    assert "```mermaid" in text


def test_causal_graph_escapes_quotes_in_labels(plugin_data_dir):
    """Quotes in event text must not break mermaid label syntax."""
    append_event(
        _event(
            event_type="user_prompt",
            ts="2026-01-01T00:00:00.000+00:00",
            user_prompt_text='read "quoted" file',
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = causal_graph("C1", data_dir=plugin_data_dir, stream=buf)
    # Double-quote in label is escaped or replaced
    assert '""' not in result["mermaid"] or '\\"' in result["mermaid"]


def test_causal_graph_truncates_long_labels(plugin_data_dir):
    append_event(
        _event(
            event_type="user_prompt", ts="2026-01-01T00:00:00.000+00:00", user_prompt_text="x" * 500
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = causal_graph("C1", data_dir=plugin_data_dir, stream=buf)
    # No single label line should exceed a sane limit (e.g. 200 chars)
    for line in result["mermaid"].splitlines():
        assert len(line) < 200


def test_causal_graph_unknown_session(plugin_data_dir):
    import pytest

    from core.session_io import SessionNotFoundError

    with pytest.raises(SessionNotFoundError):
        causal_graph("nope", data_dir=plugin_data_dir, stream=io.StringIO())


def test_causal_graph_empty_session(plugin_data_dir):
    sdir = plugin_data_dir / "sessions" / "empty"
    sdir.mkdir(parents=True)
    (sdir / "events.jsonl").write_text("")
    buf = io.StringIO()
    result = causal_graph("empty", data_dir=plugin_data_dir, stream=buf)
    assert result["node_count"] == 0
    assert result["edge_count"] == 0
