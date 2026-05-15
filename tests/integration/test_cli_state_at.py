"""Integration tests for `agent-output-tracer state-at`."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _seed(data_dir, sid="sa1"):
    sys.path.insert(0, str(REPO_ROOT))
    from core.recorder import append_event

    for i in range(5):
        append_event(
            {
                "v": 1,
                "engine": "claude-code",
                "event_type": "post_tool",
                "session_id": sid,
                "ts": f"2026-05-14T10:00:0{i}.000+00:00",
                "cwd": "/p",
                "user_prompt_text": None,
                "tool_name": "Read",
                "tool_input": {"file_path": f"/proj/{i}.md"},
                "tool_response": None,
                "agent_response_text": None,
                "stop_reason": None,
                "paths": [f"/proj/{i}.md"],
                "command": None,
                "result_bytes": 100,
                "raw_event": {},
            },
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


def test_cli_state_at_latest(tmp_path):
    _seed(tmp_path)
    res = _run(["--data-dir", str(tmp_path), "state-at", "--session", "sa1", "--time", "latest"])
    assert res.returncode == 0, res.stderr
    assert "5 unique" in res.stdout


def test_cli_state_at_iso(tmp_path):
    _seed(tmp_path)
    res = _run(
        [
            "--data-dir",
            str(tmp_path),
            "state-at",
            "--session",
            "sa1",
            "--time",
            "2026-05-14T10:00:02+00:00",
        ]
    )
    assert res.returncode == 0
    assert "3 unique" in res.stdout  # /proj/0.md, /proj/1.md, /proj/2.md


def test_cli_state_at_time_of_day(tmp_path):
    _seed(tmp_path)
    res = _run(
        [
            "--data-dir",
            str(tmp_path),
            "state-at",
            "--session",
            "sa1",
            "--time",
            "10:00:01",
        ]
    )
    assert res.returncode == 0
    assert "2 unique" in res.stdout


def test_cli_state_at_invalid_time(tmp_path):
    _seed(tmp_path)
    res = _run(
        [
            "--data-dir",
            str(tmp_path),
            "state-at",
            "--session",
            "sa1",
            "--time",
            "not-a-time",
        ]
    )
    assert res.returncode == 2
    assert "invalid" in res.stderr.lower() or "time" in res.stderr.lower()
