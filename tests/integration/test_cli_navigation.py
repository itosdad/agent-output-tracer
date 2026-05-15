"""Integration tests for the `list` / `latest` CLI subcommands plus the
session-spec resolver wired into `replay`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _seed(data_dir, sid, ts):
    sys.path.insert(0, str(REPO_ROOT))
    from core.recorder import append_event

    append_event(
        {
            "v": 1,
            "engine": "claude-code",
            "event_type": "user_prompt",
            "session_id": sid,
            "ts": ts,
            "cwd": "/p",
            "user_prompt_text": "x",
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


def test_list_empty(tmp_path):
    res = _run_cli(["--data-dir", str(tmp_path), "list"])
    assert res.returncode == 0
    assert "no sessions" in res.stdout.lower()


def test_list_after_seeding(tmp_path):
    _seed(tmp_path, "s1", "2026-01-01T00:00:00.000+00:00")
    _seed(tmp_path, "s2", "2026-02-01T00:00:00.000+00:00")
    res = _run_cli(["--data-dir", str(tmp_path), "list"])
    assert res.returncode == 0
    assert "s1" in res.stdout and "s2" in res.stdout
    # Newest first
    assert res.stdout.index("s2") < res.stdout.index("s1")


def test_list_json(tmp_path):
    _seed(tmp_path, "alpha", "2026-01-01T00:00:00.000+00:00")
    res = _run_cli(["--data-dir", str(tmp_path), "list", "--format", "json"])
    assert res.returncode == 0
    parsed = json.loads(res.stdout)
    assert any(s["session_id"] == "alpha" for s in parsed["sessions"])


def test_list_last_n(tmp_path):
    _seed(tmp_path, "a", "2026-01-01T00:00:00.000+00:00")
    _seed(tmp_path, "b", "2026-02-01T00:00:00.000+00:00")
    _seed(tmp_path, "c", "2026-03-01T00:00:00.000+00:00")
    res = _run_cli(["--data-dir", str(tmp_path), "list", "--last", "2"])
    assert res.returncode == 0
    # Top 2 most recent: c, b
    assert "c" in res.stdout and "b" in res.stdout
    assert "a" not in res.stdout.split("---")[-1]


def test_latest(tmp_path):
    _seed(tmp_path, "old", "2026-01-01T00:00:00.000+00:00")
    _seed(tmp_path, "newest-one", "2026-05-01T00:00:00.000+00:00")
    res = _run_cli(["--data-dir", str(tmp_path), "latest"])
    assert res.returncode == 0
    assert res.stdout.strip() == "newest-one"


def test_latest_empty(tmp_path):
    res = _run_cli(["--data-dir", str(tmp_path), "latest"])
    assert res.returncode == 2


def test_replay_with_latest_spec(tmp_path):
    _seed(tmp_path, "old", "2026-01-01T00:00:00.000+00:00")
    _seed(tmp_path, "newest", "2026-05-01T00:00:00.000+00:00")
    res = _run_cli(["--data-dir", str(tmp_path), "replay", "--session", "latest"])
    assert res.returncode == 0
    assert "Session: newest" in res.stdout


def test_replay_with_short_prefix(tmp_path):
    _seed(tmp_path, "abcdef123", "2026-01-01T00:00:00.000+00:00")
    res = _run_cli(["--data-dir", str(tmp_path), "replay", "--session", "abcd"])
    assert res.returncode == 0
    assert "Session: abcdef123" in res.stdout


def test_replay_with_iso_date(tmp_path):
    _seed(tmp_path, "morning", "2026-05-14T09:00:00.000+00:00")
    _seed(tmp_path, "afternoon", "2026-05-14T15:00:00.000+00:00")
    res = _run_cli(["--data-dir", str(tmp_path), "replay", "--session", "2026-05-14"])
    assert res.returncode == 0
    # Afternoon is later in the day → wins
    assert "Session: afternoon" in res.stdout
