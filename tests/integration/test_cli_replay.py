"""Integration tests for the `agent-output-tracer` CLI subprocess.

Invokes the console-script via `python -m cli.main` (equivalent to the
installed entry point) and asserts user-visible behavior.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _seed_session(data_dir, sid="cli1"):
    """Use the recorder directly (faster than subprocess for fixture setup)."""
    sys.path.insert(0, str(REPO_ROOT))
    from core.recorder import append_event

    base = {
        "v": 1,
        "engine": "claude-code",
        "session_id": sid,
        "cwd": "/proj",
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
    append_event(
        {
            **base,
            "event_type": "user_prompt",
            "ts": "2026-01-01T00:00:00.000+00:00",
            "user_prompt_text": "hello",
        },
        data_dir=data_dir,
    )
    append_event(
        {
            **base,
            "event_type": "pre_tool",
            "ts": "2026-01-01T00:00:01.000+00:00",
            "tool_name": "Read",
            "tool_input": {"file_path": "/proj/x"},
            "paths": ["/proj/x"],
        },
        data_dir=data_dir,
    )


def _run_cli(args, env_overrides=None):
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
        timeout=10,
    )


def test_cli_replay_text(tmp_path):
    _seed_session(tmp_path)
    res = _run_cli(["--data-dir", str(tmp_path), "replay", "--session", "cli1"])
    assert res.returncode == 0, res.stderr
    assert "Session: cli1" in res.stdout
    assert "[user]" in res.stdout
    assert "[tool]" in res.stdout


def test_cli_replay_json(tmp_path):
    _seed_session(tmp_path)
    res = _run_cli(
        [
            "--data-dir",
            str(tmp_path),
            "replay",
            "--session",
            "cli1",
            "--format",
            "json",
        ]
    )
    assert res.returncode == 0, res.stderr
    parsed = json.loads(res.stdout)
    assert parsed["session_id"] == "cli1"
    assert len(parsed["events"]) == 2


def test_cli_replay_markdown(tmp_path):
    _seed_session(tmp_path)
    res = _run_cli(
        [
            "--data-dir",
            str(tmp_path),
            "replay",
            "--session",
            "cli1",
            "--format",
            "markdown",
        ]
    )
    assert res.returncode == 0
    assert res.stdout.startswith("# Session cli1")


def test_cli_unknown_session_exits_2(tmp_path):
    res = _run_cli(
        [
            "--data-dir",
            str(tmp_path),
            "replay",
            "--session",
            "nope",
        ]
    )
    assert res.returncode == 2
    assert "no session" in res.stderr.lower() or "not" in res.stderr.lower()


def test_cli_help():
    res = _run_cli(["--help"])
    assert res.returncode == 0
    assert "replay" in res.stdout


def test_cli_version():
    res = _run_cli(["--version"])
    assert res.returncode == 0
    assert "agent-output-tracer" in res.stdout


def test_cli_replay_via_env_data_dir(tmp_path):
    """When --data-dir is omitted, CLAUDE_PLUGIN_DATA wins."""
    _seed_session(tmp_path)
    res = _run_cli(
        ["replay", "--session", "cli1"],
        env_overrides={"CLAUDE_PLUGIN_DATA": str(tmp_path)},
    )
    assert res.returncode == 0
    assert "Session: cli1" in res.stdout


def test_cli_replay_traversal_session_id_safe(tmp_path):
    """The CLI must not let session_id escape the sessions root."""
    _seed_session(tmp_path)
    res = _run_cli(
        [
            "--data-dir",
            str(tmp_path),
            "replay",
            "--session",
            "../escape",
        ]
    )
    assert res.returncode == 2


@pytest.mark.parametrize("script_path", ["cli/main.py"])
def test_main_is_runnable_directly(tmp_path, script_path):
    """`python cli/main.py replay ...` should also work (no -m)."""
    _seed_session(tmp_path)
    res = subprocess.run(
        [sys.executable, script_path, "--data-dir", str(tmp_path), "replay", "--session", "cli1"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=10,
    )
    assert res.returncode == 0, res.stderr
    assert "Session: cli1" in res.stdout
