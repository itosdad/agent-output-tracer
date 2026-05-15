"""Integration tests for `agent-output-tracer grep`."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _seed(data_dir, sid="g1"):
    sys.path.insert(0, str(REPO_ROOT))
    from core.recorder import append_event

    append_event(
        {
            "v": 1,
            "engine": "claude-code",
            "event_type": "user_prompt",
            "session_id": sid,
            "ts": "2026-01-01T00:00:00.000+00:00",
            "cwd": "/p",
            "user_prompt_text": "Read FooBar.tsx and tell me the export",
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
        data_dir=data_dir,
    )


def _run_cli(args, env=None):
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        capture_output=True,
        text=True,
        env=env or os.environ.copy(),
        cwd=str(REPO_ROOT),
        timeout=10,
    )


def test_cli_grep_match(tmp_path):
    _seed(tmp_path)
    res = _run_cli(
        [
            "--data-dir",
            str(tmp_path),
            "grep",
            "--session",
            "g1",
            "--pattern",
            "FooBar",
        ]
    )
    assert res.returncode == 0
    assert "FooBar" in res.stdout


def test_cli_grep_no_match_exits_1(tmp_path):
    _seed(tmp_path)
    res = _run_cli(
        [
            "--data-dir",
            str(tmp_path),
            "grep",
            "--session",
            "g1",
            "--pattern",
            "nothing-here",
        ]
    )
    assert res.returncode == 1
    assert res.stdout == ""


def test_cli_grep_ignore_case(tmp_path):
    _seed(tmp_path)
    res = _run_cli(
        [
            "--data-dir",
            str(tmp_path),
            "grep",
            "--session",
            "g1",
            "--pattern",
            "foobar",
            "-i",
        ]
    )
    assert res.returncode == 0
    assert "FooBar" in res.stdout


def test_cli_grep_invalid_regex_exits_2(tmp_path):
    _seed(tmp_path)
    res = _run_cli(
        [
            "--data-dir",
            str(tmp_path),
            "grep",
            "--session",
            "g1",
            "--pattern",
            "(((",
        ]
    )
    assert res.returncode == 2
    assert "invalid regex" in res.stderr.lower()


def test_cli_grep_uses_resolver(tmp_path):
    _seed(tmp_path, sid="abcdef1234")
    res = _run_cli(
        [
            "--data-dir",
            str(tmp_path),
            "grep",
            "--session",
            "abcd",  # short prefix
            "--pattern",
            "FooBar",
        ]
    )
    assert res.returncode == 0
    assert "FooBar" in res.stdout
