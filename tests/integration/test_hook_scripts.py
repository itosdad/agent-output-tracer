"""Integration tests for the 5 hook entry-point scripts.

Each script is invoked as a real subprocess (matching how Claude Code
calls them) with a fake event on stdin and an isolated CLAUDE_PLUGIN_DATA.

We verify:
  - Exit code is always 0 (failure-tolerance is non-negotiable per §9.1).
  - When the event is well-formed, events.jsonl + metadata.json appear.
  - When the event is malformed, no files are created but exit is still 0.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK_SCRIPTS = {
    "user_prompt": "user_prompt_submit.py",
    "pre_tool": "pre_tool_use.py",
    "post_tool": "post_tool_use.py",
    "agent_response": "stop.py",
    "session_end": "session_end.py",
}

CLAUDE_HOOK_NAMES = {
    "user_prompt": "UserPromptSubmit",
    "pre_tool": "PreToolUse",
    "post_tool": "PostToolUse",
    "agent_response": "Stop",
    "session_end": "SessionEnd",
}

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _run_hook(script_name, stdin_payload, env_overrides=None):
    """Invoke a hook script as a subprocess, return CompletedProcess."""
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "hooks" / script_name)],
        input=stdin_payload,
        capture_output=True,
        text=True,
        env=env,
        timeout=5,
    )


@pytest.mark.parametrize("event_type,script", list(HOOK_SCRIPTS.items()))
def test_hook_exits_zero_with_well_formed_event(tmp_path, event_type, script):
    raw = {
        "session_id": "intg1",
        "cwd": "/proj",
        "hook_event_name": CLAUDE_HOOK_NAMES[event_type],
    }
    if event_type == "user_prompt":
        raw["user_prompt"] = "hello"
    elif event_type in ("pre_tool", "post_tool"):
        raw["tool_name"] = "Read"
        raw["tool_input"] = {"file_path": "/proj/foo.md"}
        if event_type == "post_tool":
            raw["tool_response"] = "foo contents"
    elif event_type == "agent_response":
        raw["response_text"] = "ok"
        raw["stop_reason"] = "end_turn"

    res = _run_hook(
        script,
        json.dumps(raw),
        env_overrides={"CLAUDE_PLUGIN_DATA": str(tmp_path)},
    )
    assert res.returncode == 0, res.stderr

    events_file = tmp_path / "sessions" / "intg1" / "events.jsonl"
    metadata_file = tmp_path / "sessions" / "intg1" / "metadata.json"
    assert events_file.is_file(), f"events.jsonl missing for {script}"
    assert metadata_file.is_file(), f"metadata.json missing for {script}"

    parsed = json.loads(events_file.read_text().splitlines()[-1])
    assert parsed["event_type"] == event_type
    assert parsed["session_id"] == "intg1"


@pytest.mark.parametrize("script", list(HOOK_SCRIPTS.values()))
def test_hook_exits_zero_with_bad_json(tmp_path, script):
    res = _run_hook(
        script,
        "this is not json at all }}}",
        env_overrides={"CLAUDE_PLUGIN_DATA": str(tmp_path)},
    )
    assert res.returncode == 0, res.stderr
    assert res.stderr == "", f"hook should not write to stderr: {res.stderr!r}"
    # No session dir should be created
    assert not (tmp_path / "sessions").exists()


@pytest.mark.parametrize("script", list(HOOK_SCRIPTS.values()))
def test_hook_exits_zero_with_empty_stdin(tmp_path, script):
    res = _run_hook(
        script,
        "",
        env_overrides={"CLAUDE_PLUGIN_DATA": str(tmp_path)},
    )
    assert res.returncode == 0
    assert res.stderr == ""


@pytest.mark.parametrize("script", list(HOOK_SCRIPTS.values()))
def test_hook_exits_zero_without_plugin_data_env(tmp_path, script):
    """Even when CLAUDE_PLUGIN_DATA is unset, the hook must not crash."""
    env = os.environ.copy()
    env.pop("CLAUDE_PLUGIN_DATA", None)
    res = subprocess.run(
        [sys.executable, str(REPO_ROOT / "hooks" / script)],
        input='{"session_id":"x","hook_event_name":"PreToolUse","tool_name":"Read","tool_input":{}}',
        capture_output=True,
        text=True,
        env=env,
        timeout=5,
    )
    assert res.returncode == 0
    assert res.stderr == ""


def test_pre_post_pair_round_trip(tmp_path):
    """A typical Read call fires PreToolUse then PostToolUse; both should
    land in the same session log in order."""
    base = {
        "session_id": "pair1",
        "cwd": "/proj",
        "tool_name": "Read",
        "tool_input": {"file_path": "/proj/foo.md"},
    }
    _run_hook(
        "pre_tool_use.py",
        json.dumps({**base, "hook_event_name": "PreToolUse"}),
        env_overrides={"CLAUDE_PLUGIN_DATA": str(tmp_path)},
    )
    _run_hook(
        "post_tool_use.py",
        json.dumps({**base, "hook_event_name": "PostToolUse", "tool_response": "abc"}),
        env_overrides={"CLAUDE_PLUGIN_DATA": str(tmp_path)},
    )

    events = (tmp_path / "sessions" / "pair1" / "events.jsonl").read_text().splitlines()
    assert len(events) == 2
    assert json.loads(events[0])["event_type"] == "pre_tool"
    assert json.loads(events[1])["event_type"] == "post_tool"

    meta = json.loads((tmp_path / "sessions" / "pair1" / "metadata.json").read_text())
    assert meta["tool_calls_total"] == 1  # only pre_tool counts
    assert meta["unique_files_read"] == 1
    assert meta["total_bytes_read"] == 3  # "abc"


def test_full_5_hook_session(tmp_path):
    """End-to-end: simulate a complete tiny session through all 5 hooks."""
    sid = "fullsession"
    env = {"CLAUDE_PLUGIN_DATA": str(tmp_path)}

    _run_hook(
        "user_prompt_submit.py",
        json.dumps(
            {
                "session_id": sid,
                "cwd": "/proj",
                "hook_event_name": "UserPromptSubmit",
                "user_prompt": "Read foo.md",
            }
        ),
        env_overrides=env,
    )
    _run_hook(
        "pre_tool_use.py",
        json.dumps(
            {
                "session_id": sid,
                "cwd": "/proj",
                "hook_event_name": "PreToolUse",
                "tool_name": "Read",
                "tool_input": {"file_path": "/proj/foo.md"},
            }
        ),
        env_overrides=env,
    )
    _run_hook(
        "post_tool_use.py",
        json.dumps(
            {
                "session_id": sid,
                "cwd": "/proj",
                "hook_event_name": "PostToolUse",
                "tool_name": "Read",
                "tool_input": {"file_path": "/proj/foo.md"},
                "tool_response": "foo contents",
            }
        ),
        env_overrides=env,
    )
    _run_hook(
        "stop.py",
        json.dumps(
            {
                "session_id": sid,
                "cwd": "/proj",
                "hook_event_name": "Stop",
                "stop_reason": "end_turn",
                "response_text": "Done. foo contains: foo contents",
            }
        ),
        env_overrides=env,
    )
    _run_hook(
        "session_end.py",
        json.dumps(
            {
                "session_id": sid,
                "cwd": "/proj",
                "hook_event_name": "SessionEnd",
            }
        ),
        env_overrides=env,
    )

    events = [
        json.loads(line)
        for line in (tmp_path / "sessions" / sid / "events.jsonl").read_text().splitlines()
    ]
    assert [e["event_type"] for e in events] == [
        "user_prompt",
        "pre_tool",
        "post_tool",
        "agent_response",
        "session_end",
    ]

    meta = json.loads((tmp_path / "sessions" / sid / "metadata.json").read_text())
    assert meta["tool_calls_total"] == 1
    assert meta["user_prompts_count"] == 1
    assert meta["agent_responses_count"] == 1
    assert meta["unique_files_read"] == 1
    assert meta["total_bytes_read"] == len(b"foo contents")


def test_hooks_run_under_system_python_if_available(tmp_path):
    """The hooks are invoked by Claude Code via `python3 ...`. They must
    work under whatever `python3` the user has — including macOS system
    3.9. Skip if the system python is the same as the test runner."""
    candidates = ["/usr/bin/python3", "/usr/local/bin/python3"]
    sys_python = next((p for p in candidates if Path(p).exists()), None)
    if not sys_python or sys_python == sys.executable:
        pytest.skip("no distinct system python found to verify cross-version")

    res = subprocess.run(
        [sys_python, str(REPO_ROOT / "hooks" / "pre_tool_use.py")],
        input=json.dumps(
            {
                "session_id": "syspy",
                "cwd": "/proj",
                "hook_event_name": "PreToolUse",
                "tool_name": "Read",
                "tool_input": {"file_path": "/proj/a"},
            }
        ),
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_PLUGIN_DATA": str(tmp_path)},
        timeout=5,
    )
    assert res.returncode == 0
    assert (tmp_path / "sessions" / "syspy" / "events.jsonl").is_file()
