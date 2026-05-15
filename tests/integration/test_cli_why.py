"""Integration tests for `agent-output-tracer why`."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _seed(data_dir, *, sid="w1"):
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
        ev(
            "user_prompt",
            ts="2026-01-01T00:00:00.000+00:00",
            user_prompt_text="Implement FooBar",
        ),
        data_dir=data_dir,
    )
    append_event(
        ev(
            "post_tool",
            ts="2026-01-01T00:00:01.000+00:00",
            tool_name="Glob",
            tool_input={"pattern": "src/**/*.tsx"},
            tool_response="/p/src/FooBar.tsx\n/p/src/lib/di.ts",
            result_bytes=30,
        ),
        data_dir=data_dir,
    )
    append_event(
        ev(
            "pre_tool",
            ts="2026-01-01T00:00:02.000+00:00",
            tool_name="Read",
            tool_input={"file_path": "/p/src/lib/di.ts"},
            paths=["/p/src/lib/di.ts"],
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


def test_cli_why_by_path(tmp_path):
    _seed(tmp_path)
    res = _run(
        [
            "--data-dir",
            str(tmp_path),
            "why",
            "--session",
            "w1",
            "--path",
            "/p/src/lib/di.ts",
        ]
    )
    assert res.returncode == 0, res.stderr
    assert "/p/src/lib/di.ts" in res.stdout
    assert "FooBar" in res.stdout  # user prompt surfaced
    assert "Glob" in res.stdout  # glob origin surfaced


def test_cli_why_unknown_path_exits_1(tmp_path):
    _seed(tmp_path)
    res = _run(
        [
            "--data-dir",
            str(tmp_path),
            "why",
            "--session",
            "w1",
            "--path",
            "/p/never",
        ]
    )
    assert res.returncode == 1
    assert "no event" in res.stderr.lower()


def test_cli_why_no_selector_exits_1(tmp_path):
    _seed(tmp_path)
    res = _run(
        [
            "--data-dir",
            str(tmp_path),
            "why",
            "--session",
            "w1",
        ]
    )
    assert res.returncode == 1
    assert "--path" in res.stderr or "--event-index" in res.stderr or "supply" in res.stderr.lower()


def test_cli_why_by_event_index(tmp_path):
    _seed(tmp_path)
    res = _run(
        [
            "--data-dir",
            str(tmp_path),
            "why",
            "--session",
            "w1",
            "--event-index",
            "2",
        ]
    )
    assert res.returncode == 0
    assert "Read" in res.stdout
