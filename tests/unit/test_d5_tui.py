"""D-5 TUI tests.

The TUI itself runs interactively, so testing focuses on:
  - `is_available()` returns the right boolean
  - When textual is missing, `aot tui` shows the 3-line error
  - When textual is present, the AOTApp class can be constructed
    against a real session (smoke test only — no actual rendering)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tui import is_available

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_is_available_matches_import():
    """is_available() should agree with a direct import attempt."""
    try:
        import textual  # noqa: F401
    except ImportError:
        assert is_available() is False
    else:
        assert is_available() is True


def test_cli_tui_without_optional_dep(tmp_path, monkeypatch):
    """When textual isn't on PYTHONPATH, `aot tui` returns 2 and emits
    the 3-line error pointing at the install command."""
    env = os.environ.copy()
    env["CLAUDE_PLUGIN_DATA"] = str(tmp_path)
    # Force-block textual import by pointing PYTHONPATH at an empty dir
    # — but only if textual is actually installed (otherwise the test
    # would falsely pass).
    if is_available():
        pytest.skip("textual is installed in this env; can't test the missing path")
    res = subprocess.run(
        [sys.executable, "-m", "cli.main", "tui", "--session", "latest"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
        timeout=10,
    )
    assert res.returncode == 2
    assert "[tui]" in res.stderr
    assert "pip install" in res.stderr


@pytest.mark.skipif(not is_available(), reason="textual not installed")
def test_app_can_be_constructed(plugin_data_dir):
    """If textual is installed, the AOTApp class instantiates without
    error against a real session id. Doesn't actually start the
    rendering loop."""
    from core.recorder import append_event

    append_event(
        {
            "v": 1,
            "engine": "claude-code",
            "event_type": "user_prompt",
            "session_id": "tui1",
            "ts": "2026-05-15T10:00:00.000+00:00",
            "cwd": "/p",
            "user_prompt_text": "hi",
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
        data_dir=plugin_data_dir,
    )
    from tui.app import AOTApp, _render_row

    app = AOTApp("tui1", data_dir=plugin_data_dir)
    assert app.session_id == "tui1"

    # Smoke-test the row formatter independently of the textual app
    # loop (this is the unit doing real work for D-5 timeline display).
    row = _render_row(
        {
            "ts": "2026-05-15T10:00:00.000+00:00",
            "event_type": "user_prompt",
            "user_prompt_text": "hello",
            "paths": [],
            "tool_name": None,
        }
    )
    assert row[1] == "user_prompt"
    assert "hello" in row[3]
