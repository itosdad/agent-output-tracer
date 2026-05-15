"""Integration tests for `agent-output-tracer diff`."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _seed(data_dir):
    sys.path.insert(0, str(REPO_ROOT))
    from core.recorder import append_event

    def ev(et, **over):
        e = {
            "v": 1,
            "engine": "claude-code",
            "event_type": et,
            "session_id": "d1",
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
            user_prompt_text="Implement FooBar based on /proj/spec.md",
        ),
        data_dir=data_dir,
    )
    append_event(
        ev(
            "pre_tool",
            ts="2026-01-01T00:00:01.000+00:00",
            tool_name="Read",
            tool_input={"file_path": "/proj/spec.md"},
            paths=["/proj/spec.md"],
        ),
        data_dir=data_dir,
    )
    append_event(
        ev(
            "pre_tool",
            ts="2026-01-01T00:00:02.000+00:00",
            tool_name="Read",
            tool_input={"file_path": "/proj/unrelated.ts"},
            paths=["/proj/unrelated.ts"],
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


def test_cli_diff_basic(tmp_path):
    _seed(tmp_path)
    res = _run(["--data-dir", str(tmp_path), "diff", "--session", "d1"])
    assert res.returncode == 0, res.stderr
    assert "/proj/unrelated.ts" in res.stdout  # agent touched, no mention
    # /proj/spec.md was mentioned and touched → neither flagged side


def test_cli_diff_clean_session(tmp_path):
    """Empty session: both sides report (none)."""
    sdir = tmp_path / "sessions" / "empty"
    sdir.mkdir(parents=True)
    (sdir / "events.jsonl").write_text("")
    res = _run(["--data-dir", str(tmp_path), "diff", "--session", "empty"])
    assert res.returncode == 0
    # Both sections show (none)
    assert res.stdout.count("(none)") >= 2


def test_cli_diff_uses_resolver(tmp_path):
    _seed(tmp_path)
    res = _run(["--data-dir", str(tmp_path), "diff", "--session", "latest"])
    assert res.returncode == 0
    assert "Session: d1" in res.stdout
