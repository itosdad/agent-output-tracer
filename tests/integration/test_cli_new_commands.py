"""Integration tests for the Phase B-6/B-7/B-9 CLI subcommands
(causal-graph, export-trace, gc). Plus a hint-rendering check for
replay --show-hints."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _seed(data_dir, *, sid="n1", repeats=1, ts_base=None):
    sys.path.insert(0, str(REPO_ROOT))
    from core.recorder import append_event

    base_dt = ts_base or datetime(2026, 5, 1, 10, 0, 0, tzinfo=timezone.utc)

    def at(secs):
        return (base_dt + timedelta(seconds=secs)).isoformat(timespec="milliseconds")

    def ev(et, **over):
        e = {
            "v": 1,
            "engine": "claude-code",
            "event_type": et,
            "session_id": sid,
            "ts": at(0),
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
        e.update(over)
        return e

    append_event(ev("user_prompt", ts=at(0), user_prompt_text="explore"), data_dir=data_dir)
    append_event(
        ev(
            "post_tool",
            ts=at(1),
            tool_name="Glob",
            tool_input={"pattern": "*.md"},
            tool_response="/p/foo.md\n/p/bar.md",
        ),
        data_dir=data_dir,
    )
    # 'repeats' Read events of the same path → triggers repeated_read hint when >=3.
    # Each Read is a pre_tool + post_tool pair: causal_graph's dashed Glob→Read
    # edge fires on the pre_tool side.
    for i in range(repeats):
        append_event(
            ev(
                "pre_tool",
                ts=at(2 + i * 2),
                tool_name="Read",
                tool_input={"file_path": "/p/foo.md"},
                paths=["/p/foo.md"],
            ),
            data_dir=data_dir,
        )
        append_event(
            ev(
                "post_tool",
                ts=at(2 + i * 2 + 1),
                tool_name="Read",
                tool_input={"file_path": "/p/foo.md"},
                paths=["/p/foo.md"],
                tool_response="content",
                result_bytes=7,
            ),
            data_dir=data_dir,
        )
    append_event(
        ev("agent_response", ts=at(99), agent_response_text="done"),
        data_dir=data_dir,
    )


def _run(args, env=None):
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        capture_output=True,
        text=True,
        env=env or os.environ.copy(),
        cwd=str(REPO_ROOT),
        timeout=15,
    )


# ----- causal-graph -----


def test_cli_causal_graph_stdout(tmp_path):
    _seed(tmp_path)
    res = _run(["--data-dir", str(tmp_path), "causal-graph", "--session", "n1"])
    assert res.returncode == 0, res.stderr
    assert "```mermaid" in res.stdout
    assert "graph TD" in res.stdout
    # Read /p/foo.md after a Glob whose response contained /p/foo.md →
    # at least one dashed edge expected.
    assert "-.->" in res.stdout


def test_cli_causal_graph_to_file(tmp_path):
    _seed(tmp_path)
    out_file = tmp_path / "g.md"
    res = _run(
        [
            "--data-dir",
            str(tmp_path),
            "causal-graph",
            "--session",
            "n1",
            "--output",
            str(out_file),
        ]
    )
    assert res.returncode == 0, res.stderr
    assert out_file.exists()
    text = out_file.read_text()
    assert "```mermaid" in text


# ----- export-trace -----


def test_cli_export_trace_stdout(tmp_path):
    _seed(tmp_path)
    res = _run(["--data-dir", str(tmp_path), "export-trace", "--session", "n1"])
    assert res.returncode == 0, res.stderr
    # All sections present
    for header in ("## Timeline", "## User vs agent", "## Hallucination", "## Causal graph"):
        assert header in res.stdout, f"missing section: {header}"


def test_cli_export_trace_to_file(tmp_path):
    _seed(tmp_path)
    out_file = tmp_path / "report.md"
    res = _run(
        [
            "--data-dir",
            str(tmp_path),
            "export-trace",
            "--session",
            "n1",
            "--output",
            str(out_file),
        ]
    )
    assert res.returncode == 0
    text = out_file.read_text()
    assert "## Timeline" in text


# ----- replay --show-hints -----


def test_cli_replay_show_hints_surfaces_repeated_read(tmp_path):
    """3 Reads of the same path → repeated_read hint shows up."""
    _seed(tmp_path, repeats=3)
    res = _run(
        [
            "--data-dir",
            str(tmp_path),
            "replay",
            "--session",
            "n1",
            "--show-hints",
        ]
    )
    assert res.returncode == 0, res.stderr
    assert "Anomaly hints" in res.stdout
    assert "repeated_read" in res.stdout
    assert "/p/foo.md" in res.stdout


def test_cli_replay_show_hints_json_format(tmp_path):
    _seed(tmp_path, repeats=3)
    res = _run(
        [
            "--data-dir",
            str(tmp_path),
            "replay",
            "--session",
            "n1",
            "--show-hints",
            "--format",
            "json",
        ]
    )
    assert res.returncode == 0
    parsed = json.loads(res.stdout)
    assert "anomaly_hints" in parsed
    assert any(h["pattern"] == "repeated_read" for h in parsed["anomaly_hints"])


# ----- gc -----


def test_cli_gc_dry_run(tmp_path):
    """Old session → dry-run reports stripped/deleted without mutating."""
    old = datetime.now(timezone.utc) - timedelta(days=400)
    _seed(tmp_path, sid="old-one", ts_base=old)
    fresh = datetime.now(timezone.utc) - timedelta(hours=1)
    _seed(tmp_path, sid="recent", ts_base=fresh)

    res = _run(["--data-dir", str(tmp_path), "gc", "--dry-run"])
    assert res.returncode == 0
    assert "[dry-run]" in res.stdout
    assert "old-one" in res.stdout
    # Filesystem untouched
    assert (tmp_path / "sessions" / "old-one").exists()


def test_cli_gc_actually_mutates(tmp_path):
    """Without --dry-run, very old sessions get cleaned."""
    old = datetime.now(timezone.utc) - timedelta(days=400)
    _seed(tmp_path, sid="ancient", ts_base=old)
    res = _run(["--data-dir", str(tmp_path), "gc"])
    assert res.returncode == 0
    assert "deleted 1" in res.stdout
    assert not (tmp_path / "sessions" / "ancient").exists()
