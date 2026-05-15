"""Integration tests for `agent-output-tracer mentioned-but-not-read`."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _seed(data_dir, *, hallucinate=True):
    sys.path.insert(0, str(REPO_ROOT))
    from core.recorder import append_event

    def ev(et, **over):
        e = {
            "v": 1,
            "engine": "claude-code",
            "event_type": et,
            "session_id": "m1",
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
            user_prompt_text="explore /proj",
        ),
        data_dir=data_dir,
    )
    if hallucinate:
        append_event(
            ev(
                "agent_response",
                ts="2026-01-01T00:00:01.000+00:00",
                agent_response_text="Looked at /proj/ghost.md and /proj/imaginary.ts",
            ),
            data_dir=data_dir,
        )
    else:
        append_event(
            ev(
                "post_tool",
                ts="2026-01-01T00:00:01.000+00:00",
                tool_name="Glob",
                tool_input={"pattern": "*"},
                tool_response="/proj/real.md",
                result_bytes=14,
            ),
            data_dir=data_dir,
        )
        append_event(
            ev(
                "agent_response",
                ts="2026-01-01T00:00:02.000+00:00",
                agent_response_text="Found /proj/real.md",
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


def test_cli_mbnr_with_candidates_exit_3(tmp_path):
    _seed(tmp_path, hallucinate=True)
    res = _run(
        [
            "--data-dir",
            str(tmp_path),
            "mentioned-but-not-read",
            "--session",
            "m1",
        ]
    )
    assert res.returncode == 3, res.stderr
    assert "/proj/ghost.md" in res.stdout
    assert "/proj/imaginary.ts" in res.stdout


def test_cli_mbnr_clean_session_exit_0(tmp_path):
    _seed(tmp_path, hallucinate=False)
    res = _run(
        [
            "--data-dir",
            str(tmp_path),
            "mentioned-but-not-read",
            "--session",
            "m1",
        ]
    )
    assert res.returncode == 0, res.stderr
    out = res.stdout.lower()
    assert "(none" in out or "no hallucination" in out
    # /proj/real.md is grounded (in Glob tool_response), should NOT be listed
    assert "/proj/real.md\n" not in res.stdout or "(none" in out


def test_cli_mbnr_uses_resolver(tmp_path):
    _seed(tmp_path, hallucinate=True)
    res = _run(
        [
            "--data-dir",
            str(tmp_path),
            "mentioned-but-not-read",
            "--session",
            "latest",
        ]
    )
    assert res.returncode == 3
    assert "Session: m1" in res.stdout
