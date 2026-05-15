"""Integration tests for Codex hook routing.

Codex shares the same hook scripts as Claude Code (single hooks.json,
runtime engine detection in `hooks/_runner.py`). These tests verify
each script accepts a Codex-format payload and records the right
normalized event.

Engine detection signal: Codex payloads carry `permission_mode`. The
runner uses that to pick the codex adapter.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# (script_name, codex hook_event_name, expected normalized event_type,
#  extra payload fields)
CODEX_SCRIPTS = [
    (
        "user_prompt_submit.py",
        "user_prompt_submit",
        "user_prompt",
        {"prompt": "hi from codex"},
    ),
    (
        "pre_tool_use.py",
        "pre_tool_use",
        "pre_tool",
        {"tool_name": "apply_patch", "tool_input": {"file_path": "/p/a.py"}},
    ),
    (
        "post_tool_use.py",
        "post_tool_use",
        "post_tool",
        {
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
            "tool_response": "a.py\nb.py",
        },
    ),
    (
        "stop.py",
        "stop",
        "agent_response",
        {"last_assistant_message": "done", "stop_reason": "end_turn"},
    ),
    (
        "session_start.py",
        "session_start",
        "session_start",
        {"source": "startup"},
    ),
    (
        "pre_compact.py",
        "pre_compact",
        "compact_pre",
        {},
    ),
    (
        "post_compact.py",
        "post_compact",
        "compact_post",
        {},
    ),
]


def _run_hook(script_name, stdin_payload, env_overrides=None):
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


def _codex_payload(hook_event_name, **extra):
    payload = {
        "hook_event_name": hook_event_name,
        "session_id": "cdx-itg",
        "cwd": "/proj",
        "model": "gpt-5",
        "permission_mode": "default",
        "transcript_path": "/tmp/c.jsonl",
    }
    # turn_id only for turn-scoped events
    if hook_event_name in (
        "user_prompt_submit",
        "pre_tool_use",
        "post_tool_use",
        "stop",
    ):
        payload["turn_id"] = "t-1"
    payload.update(extra)
    return payload


@pytest.mark.parametrize(
    "script,hook_name,expected_type,extra",
    CODEX_SCRIPTS,
)
def test_codex_event_routed_to_codex_adapter(
    tmp_path, script, hook_name, expected_type, extra
):
    raw = _codex_payload(hook_name, **extra)
    res = _run_hook(
        script,
        json.dumps(raw),
        env_overrides={"CLAUDE_PLUGIN_DATA": str(tmp_path)},
    )
    assert res.returncode == 0, res.stderr
    assert res.stderr == "", f"hook should be silent: {res.stderr!r}"

    events_file = tmp_path / "sessions" / "cdx-itg" / "events.jsonl"
    assert events_file.is_file(), f"events.jsonl missing for {script}"
    parsed = json.loads(events_file.read_text().splitlines()[-1])
    assert parsed["engine"] == "codex"
    assert parsed["event_type"] == expected_type
    assert parsed["session_id"] == "cdx-itg"


def test_codex_turn_id_preserved_through_runner(tmp_path):
    """End-to-end: turn_id from raw event survives normalization and
    appears in the recorded events.jsonl line."""
    raw = _codex_payload(
        "user_prompt_submit",
        prompt="please",
    )
    res = _run_hook(
        "user_prompt_submit.py",
        json.dumps(raw),
        env_overrides={"CLAUDE_PLUGIN_DATA": str(tmp_path)},
    )
    assert res.returncode == 0
    parsed = json.loads(
        (tmp_path / "sessions" / "cdx-itg" / "events.jsonl")
        .read_text()
        .splitlines()[-1]
    )
    assert parsed.get("turn_id") == "t-1"


def test_engine_detection_falls_back_to_claude_for_legacy_payload(tmp_path):
    """A Claude-Code-shaped payload (no permission_mode) must still
    route to the claude_code adapter even though the same script also
    handles Codex events."""
    raw = {
        "session_id": "cc-itg",
        "cwd": "/proj",
        "hook_event_name": "UserPromptSubmit",
        "user_prompt": "hi from claude",
    }
    res = _run_hook(
        "user_prompt_submit.py",
        json.dumps(raw),
        env_overrides={"CLAUDE_PLUGIN_DATA": str(tmp_path)},
    )
    assert res.returncode == 0
    parsed = json.loads(
        (tmp_path / "sessions" / "cc-itg" / "events.jsonl")
        .read_text()
        .splitlines()[-1]
    )
    assert parsed["engine"] == "claude-code"
    assert parsed["event_type"] == "user_prompt"


def test_codex_session_start_drops_on_claude_adapter(tmp_path):
    """If a session_start payload arrives shaped like Claude Code (no
    permission_mode), the claude adapter doesn't subscribe to
    SessionStart, so nothing is recorded — but exit is still 0."""
    raw = {
        "session_id": "ss-1",
        "cwd": "/proj",
        "hook_event_name": "SessionStart",  # CamelCase — Claude style
        "source": "startup",
    }
    res = _run_hook(
        "session_start.py",
        json.dumps(raw),
        env_overrides={"CLAUDE_PLUGIN_DATA": str(tmp_path)},
    )
    assert res.returncode == 0
    assert not (tmp_path / "sessions" / "ss-1").exists()
