"""Integration tests for `agent-output-tracer trace`."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _seed(data_dir, *, sid="trc1", hallucination=True):
    sys.path.insert(0, str(REPO_ROOT))
    from core.recorder import append_event

    def ev(et, **over):
        e = {
            "v": 1,
            "engine": "claude-code",
            "event_type": et,
            "session_id": sid,
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
        e.update(over)
        return e

    append_event(
        ev("user_prompt", ts="2026-01-01T00:00:00.000+00:00", user_prompt_text="Implement Foo"),
        data_dir=data_dir,
    )
    response = "// unrelated content" if hallucination else "// Uses DI container"
    append_event(
        ev(
            "post_tool",
            ts="2026-01-01T00:00:01.000+00:00",
            tool_name="Read",
            tool_input={"file_path": "/p/spec.md"},
            paths=["/p/spec.md"],
            tool_response=response,
            result_bytes=len(response),
        ),
        data_dir=data_dir,
    )
    append_event(
        ev(
            "agent_response",
            ts="2026-01-01T00:00:02.000+00:00",
            agent_response_text="Using DI container approach",
        ),
        data_dir=data_dir,
    )


def _run(args, env=None):
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        capture_output=True,
        text=True,
        env=env or os.environ.copy(),
        cwd=str(REPO_ROOT),
        timeout=10,
    )


def test_cli_trace_hallucination_exits_3(tmp_path):
    _seed(tmp_path, hallucination=True)
    res = _run(
        [
            "--data-dir",
            str(tmp_path),
            "trace",
            "--session",
            "trc1",
            "--output",
            "DI container",
        ]
    )
    assert res.returncode == 3, res.stderr
    assert "hallucination" in res.stdout.lower() or "⚠" in res.stdout
    assert "DI container" in res.stdout


def test_cli_trace_grounded_exits_0(tmp_path):
    _seed(tmp_path, hallucination=False)
    res = _run(
        [
            "--data-dir",
            str(tmp_path),
            "trace",
            "--session",
            "trc1",
            "--output",
            "DI container",
        ]
    )
    assert res.returncode == 0, res.stderr
    out_lower = res.stdout.lower()
    # Grounded → no hallucination warning
    assert "hallucination" not in out_lower
    # Read should show as containing the phrase
    assert "✓ contains" in res.stdout


def test_cli_trace_phrase_absent_exits_0(tmp_path):
    _seed(tmp_path, hallucination=True)
    res = _run(
        [
            "--data-dir",
            str(tmp_path),
            "trace",
            "--session",
            "trc1",
            "--output",
            "nothing-matches-this-phrase",
        ]
    )
    assert res.returncode == 0
    assert "not found" in res.stdout.lower()


def test_cli_trace_uses_resolver(tmp_path):
    _seed(tmp_path, sid="abcdef123", hallucination=True)
    res = _run(
        [
            "--data-dir",
            str(tmp_path),
            "trace",
            "--session",
            "abcd",  # short prefix
            "--output",
            "DI container",
        ]
    )
    # Hallucination → exit 3
    assert res.returncode == 3
    assert "DI container" in res.stdout


def test_cli_trace_uses_latest_spec(tmp_path):
    _seed(tmp_path, sid="latest-target", hallucination=True)
    res = _run(
        [
            "--data-dir",
            str(tmp_path),
            "trace",
            "--session",
            "latest",
            "--output",
            "DI container",
        ]
    )
    assert res.returncode == 3
    assert "DI container" in res.stdout
