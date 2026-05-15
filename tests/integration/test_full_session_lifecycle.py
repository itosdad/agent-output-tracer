"""End-to-end Phase A milestone test.

Drives a realistic multi-turn session through every hook script as
subprocesses (i.e. exactly how Claude Code invokes them), then verifies
every Phase A query surface (replay / list / latest / grep / state-at)
produces useful answers.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _hook(script, payload, data_dir):
    env = os.environ.copy()
    env["CLAUDE_PLUGIN_DATA"] = str(data_dir)
    res = subprocess.run(
        [sys.executable, str(REPO_ROOT / "hooks" / script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=5,
    )
    assert res.returncode == 0, res.stderr


def _cli(args, data_dir):
    env = os.environ.copy()
    env["CLAUDE_PLUGIN_DATA"] = str(data_dir)
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
        timeout=10,
    )


def test_full_lifecycle(tmp_path):
    sid = "lifecycle-1"
    cwd = "/proj"

    # ---------- Turn 1: read foo.md ----------
    _hook(
        "user_prompt_submit.py",
        {
            "session_id": sid,
            "cwd": cwd,
            "hook_event_name": "UserPromptSubmit",
            "user_prompt": "Read foo.md and tell me what's in it.",
        },
        tmp_path,
    )
    _hook(
        "pre_tool_use.py",
        {
            "session_id": sid,
            "cwd": cwd,
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "tool_input": {"file_path": "/proj/foo.md"},
        },
        tmp_path,
    )
    _hook(
        "post_tool_use.py",
        {
            "session_id": sid,
            "cwd": cwd,
            "hook_event_name": "PostToolUse",
            "tool_name": "Read",
            "tool_input": {"file_path": "/proj/foo.md"},
            "tool_response": "# foo\n\nhello world",
        },
        tmp_path,
    )
    _hook(
        "stop.py",
        {
            "session_id": sid,
            "cwd": cwd,
            "hook_event_name": "Stop",
            "stop_reason": "end_turn",
            "response_text": "foo.md says hello world.",
        },
        tmp_path,
    )

    # ---------- Turn 2: read foo.md again + di.ts (unsolicited) ----------
    _hook(
        "user_prompt_submit.py",
        {
            "session_id": sid,
            "cwd": cwd,
            "hook_event_name": "UserPromptSubmit",
            "user_prompt": "Now implement FooBar.tsx based on foo.md.",
        },
        tmp_path,
    )
    _hook(
        "pre_tool_use.py",
        {
            "session_id": sid,
            "cwd": cwd,
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "tool_input": {"file_path": "/proj/foo.md"},  # repeat read
        },
        tmp_path,
    )
    _hook(
        "post_tool_use.py",
        {
            "session_id": sid,
            "cwd": cwd,
            "hook_event_name": "PostToolUse",
            "tool_name": "Read",
            "tool_input": {"file_path": "/proj/foo.md"},
            "tool_response": "# foo\n\nhello world",
        },
        tmp_path,
    )
    _hook(
        "pre_tool_use.py",
        {
            "session_id": sid,
            "cwd": cwd,
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "tool_input": {"file_path": "/proj/src/di.ts"},  # unsolicited
        },
        tmp_path,
    )
    _hook(
        "post_tool_use.py",
        {
            "session_id": sid,
            "cwd": cwd,
            "hook_event_name": "PostToolUse",
            "tool_name": "Read",
            "tool_input": {"file_path": "/proj/src/di.ts"},
            "tool_response": "export const container = ...",
        },
        tmp_path,
    )
    _hook(
        "stop.py",
        {
            "session_id": sid,
            "cwd": cwd,
            "hook_event_name": "Stop",
            "stop_reason": "end_turn",
            "response_text": "Designed FooBar with a DI container approach.",
        },
        tmp_path,
    )

    _hook(
        "session_end.py",
        {"session_id": sid, "cwd": cwd, "hook_event_name": "SessionEnd"},
        tmp_path,
    )

    # ---------- Verify events.jsonl + metadata.json ----------
    sdir = tmp_path / "sessions" / sid
    events = (sdir / "events.jsonl").read_text().splitlines()
    # 2 user_prompt + 3 pre_tool + 3 post_tool + 2 agent_response + 1
    # session_end = 11
    assert len(events) == 11

    meta = json.loads((sdir / "metadata.json").read_text())
    assert meta["session_id"] == sid
    assert meta["user_prompts_count"] == 2
    assert meta["agent_responses_count"] == 2
    assert meta["tool_calls_total"] == 3  # 3 pre_tool events
    assert meta["unique_files_read"] == 2  # foo.md + di.ts

    # ---------- replay ----------
    r = _cli(["replay", "--session", sid], tmp_path)
    assert r.returncode == 0, r.stderr
    assert "Session: " + sid in r.stdout
    assert "/proj/foo.md" in r.stdout
    assert "/proj/src/di.ts" in r.stdout
    assert "[user]" in r.stdout
    assert "[agent]" in r.stdout

    # ---------- replay with 'latest' ----------
    r = _cli(["replay", "--session", "latest"], tmp_path)
    assert r.returncode == 0
    assert "Session: " + sid in r.stdout

    # ---------- list ----------
    r = _cli(["list"], tmp_path)
    assert r.returncode == 0
    assert sid in r.stdout

    # ---------- latest ----------
    r = _cli(["latest"], tmp_path)
    assert r.returncode == 0
    assert r.stdout.strip() == sid

    # ---------- grep ----------
    r = _cli(["grep", "--session", sid, "--pattern", "FooBar"], tmp_path)
    assert r.returncode == 0
    assert "FooBar" in r.stdout
    # User prompt mentioned FooBar.tsx; agent response said FooBar.
    # Should be at least 2 matches.

    # grep for an unsolicited read target
    r = _cli(["grep", "--session", sid, "--pattern", "di.ts"], tmp_path)
    assert r.returncode == 0
    assert "di.ts" in r.stdout

    # grep with no match returns exit 1
    r = _cli(["grep", "--session", sid, "--pattern", "nothing-here-xyz"], tmp_path)
    assert r.returncode == 1

    # ---------- state-at latest ----------
    r = _cli(["state-at", "--session", sid, "--time", "latest"], tmp_path)
    assert r.returncode == 0
    assert "2 unique" in r.stdout
    assert "/proj/foo.md" in r.stdout
    # foo.md was read 2x, di.ts 1x → foo.md should have the ⚠ when threshold=3,
    # but we set threshold at 3 in state_at, so neither is flagged here.
    # We just check the table renders.


def test_replay_text_output_shape(tmp_path):
    """Lock the replay text format so we notice regressions."""
    sid = "shape"
    _hook(
        "user_prompt_submit.py",
        {
            "session_id": sid,
            "cwd": "/p",
            "hook_event_name": "UserPromptSubmit",
            "user_prompt": "hi",
        },
        tmp_path,
    )
    _hook(
        "pre_tool_use.py",
        {
            "session_id": sid,
            "cwd": "/p",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la"},
        },
        tmp_path,
    )

    r = _cli(["replay", "--session", sid], tmp_path)
    assert r.returncode == 0
    lines = [line for line in r.stdout.splitlines() if line.strip()]
    # Header (Session/Started/Events/Counts ≤ 5 lines) + 2 event lines
    assert any("Session: shape" in line for line in lines)
    assert any("[user]" in line and "hi" in line for line in lines)
    assert any("[tool]" in line and "Bash" in line and "ls -la" in line for line in lines)


def test_json_replay_round_trip_via_recorder_and_cli(tmp_path):
    """JSON replay output should be valid JSON parseable back into a
    dict with a known shape."""
    sid = "jrt"
    _hook(
        "user_prompt_submit.py",
        {
            "session_id": sid,
            "cwd": "/p",
            "hook_event_name": "UserPromptSubmit",
            "user_prompt": "hi",
        },
        tmp_path,
    )
    r = _cli(["replay", "--session", sid, "--format", "json"], tmp_path)
    assert r.returncode == 0
    parsed = json.loads(r.stdout)
    assert parsed["session_id"] == sid
    assert parsed["metadata"]["session_id"] == sid
    assert len(parsed["events"]) == 1
    assert parsed["events"][0]["event_type"] == "user_prompt"
