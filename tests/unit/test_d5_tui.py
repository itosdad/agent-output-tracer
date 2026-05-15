"""D-5 TUI tests (Phase 1 — screen-based navigation).

The TUI runs interactively, so testing focuses on what's worth
unit-coverage:
  - `is_available()` agrees with a real import attempt
  - When textual is missing, `aot tui` exits 2 with the 3-line hint
  - When textual is present, the App + each screen can be constructed
    against real session data without crashing
  - `_render_row` produces the expected (prefix, ts, type, locus, body)
    tuple per event type
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
    if is_available():
        pytest.skip("textual is installed in this env; can't test the missing path")
    res = subprocess.run(
        [sys.executable, "-m", "cli.main", "tui"],
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
def test_render_row_semantic_prefix():
    """Each event type maps to the right semantic prefix."""
    from tui.app import _render_row

    user_row = _render_row(
        {
            "ts": "2026-05-15T10:00:00.000+00:00",
            "event_type": "user_prompt",
            "user_prompt_text": "hello",
            "paths": [],
            "tool_name": None,
        }
    )
    assert user_row[0] == "›"
    assert user_row[2] == "user_prompt"
    assert "hello" in user_row[4]

    pre = _render_row(
        {
            "ts": "2026-05-15T10:00:01.000+00:00",
            "event_type": "pre_tool",
            "tool_name": "Read",
            "paths": ["/p/x.md"],
            "tool_response": None,
        }
    )
    assert pre[0] == "⏵"
    assert pre[2] == "pre_tool"
    assert "Read /p/x.md" in pre[3]

    post = _render_row(
        {
            "ts": "2026-05-15T10:00:02.000+00:00",
            "event_type": "post_tool",
            "tool_name": "Read",
            "paths": ["/p/x.md"],
            "tool_response": "content",
        }
    )
    assert post[0] == "✓"

    agent = _render_row(
        {
            "ts": "2026-05-15T10:00:03.000+00:00",
            "event_type": "agent_response",
            "agent_response_text": "OK",
            "paths": [],
            "tool_name": None,
        }
    )
    assert agent[0] == "•"


@pytest.mark.skipif(not is_available(), reason="textual not installed")
def test_app_can_be_constructed_home(plugin_data_dir):
    """Bare `AOTApp()` (no session) constructs cleanly — the Home screen
    is the canonical entry point."""
    from tui.app import AOTApp

    app = AOTApp(None, data_dir=plugin_data_dir)
    assert app._initial_session is None


@pytest.mark.skipif(not is_available(), reason="textual not installed")
def test_app_can_be_constructed_with_session(plugin_data_dir):
    """Providing a session id arms the deep-link path. Construction
    alone does not start the loop, so a non-existent session is fine."""
    from tui.app import AOTApp

    app = AOTApp("abcd-1234", data_dir=plugin_data_dir)
    assert app.session_id == "abcd-1234"
    assert app._initial_session == "abcd-1234"


@pytest.mark.skipif(not is_available(), reason="textual not installed")
def test_home_screen_constructs():
    from tui.screens.home import HomeScreen

    screen = HomeScreen()
    assert screen.TITLE == "home"
    crumbs = screen.breadcrumb_segments()
    assert crumbs == ["aot", "home"]
    hints = screen.footer_hints()
    assert any(k == "enter" for k, _ in hints)


@pytest.mark.skipif(not is_available(), reason="textual not installed")
def test_sessions_screen_constructs(plugin_data_dir):
    from tui.screens.sessions import SessionsScreen

    screen = SessionsScreen(data_dir=plugin_data_dir)
    assert screen.TITLE == "sessions"
    assert screen.breadcrumb_segments() == ["aot", "sessions"]


@pytest.mark.skipif(not is_available(), reason="textual not installed")
def test_timeline_screen_constructs(plugin_data_dir):
    from tui.screens.timeline import TimelineScreen

    screen = TimelineScreen("abcd-1234-5678", data_dir=plugin_data_dir)
    assert screen.session_id == "abcd-1234-5678"
    crumbs = screen.breadcrumb_segments()
    assert crumbs[0] == "aot"
    assert crumbs[-1] == "timeline"
    # Breadcrumb uses first 8 chars of the session id.
    assert crumbs[1] == "abcd-123"


@pytest.mark.skipif(not is_available(), reason="textual not installed")
def test_event_detail_screen_constructs():
    from tui.screens.event_detail import EventDetailScreen

    event = {
        "ts": "2026-05-15T10:00:00.000+00:00",
        "event_type": "pre_tool",
        "tool_name": "Read",
        "session_id": "abcd",
        "paths": ["/p/x.md"],
    }
    screen = EventDetailScreen(
        event=event,
        event_index=3,
        session_id="abcd-1234",
        all_events=[event],
    )
    crumbs = screen.breadcrumb_segments()
    assert "event 3" in crumbs[-1]
    assert "pre_tool" in crumbs[-1]


# ---- modal_form / inline_prompt skeleton smoke ----


@pytest.mark.skipif(not is_available(), reason="textual not installed")
def test_modal_form_field_types():
    from tui.widgets.modal_form import FormField, ModalForm

    fields = [
        FormField("name", "Name", "text", default=""),
        FormField("active", "Active", "bool", default=True),
        FormField("fmt", "Format", "enum", default="markdown", options=["markdown", "json"]),
        FormField("n", "Count", "number", default=3),
    ]
    form = ModalForm("Test", fields)
    # Cursor advance / cycle wraps correctly
    form._cursor = 1
    form.action_toggle()
    assert form._values["active"] is False
    form._cursor = 2
    form.action_inc()
    assert form._values["fmt"] == "json"


@pytest.mark.skipif(not is_available(), reason="textual not installed")
def test_inline_prompt_history_recall():
    from tui.widgets.inline_prompt import InlinePrompt

    prompt = InlinePrompt(history=["first", "second", "third"])
    assert prompt._history == ["first", "second", "third"]
    assert prompt._history_idx is None


# ---- end-to-end navigation smoke ----


@pytest.mark.skipif(not is_available(), reason="textual not installed")
@pytest.mark.asyncio
async def test_navigation_home_to_sessions_to_back(plugin_data_dir):
    """Home → Enter (drill to Sessions) → Esc (back to Home).

    Exercises the screen stack contract end to end on the live event
    loop without requiring a real terminal.
    """
    from core.recorder import append_event
    from tui.app import AOTApp

    append_event(
        {
            "v": 1,
            "engine": "claude-code",
            "event_type": "user_prompt",
            "session_id": "navsmoke-001",
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

    app = AOTApp(None, data_dir=plugin_data_dir)
    async with app.run_test() as pilot:
        # Initial screen is Home.
        await pilot.pause()
        top = app.screen
        assert top.__class__.__name__ == "HomeScreen"

        # Enter drills into Sessions (the first menu item).
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "SessionsScreen"

        # Esc returns to Home.
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "HomeScreen"


@pytest.mark.skipif(not is_available(), reason="textual not installed")
@pytest.mark.asyncio
async def test_enter_on_session_row_drills_into_timeline(plugin_data_dir):
    """Regression: DataTable consumes Enter via its own `select_cursor`
    action, which emits RowSelected. The screen has to listen for that
    message — relying on the screen-level "enter" binding alone leaves
    drill-in dead. (Phase 1 v0.7.0 originally shipped with this bug.)"""
    from core.recorder import append_event
    from tui.app import AOTApp

    append_event(
        {
            "v": 1,
            "engine": "claude-code",
            "event_type": "user_prompt",
            "session_id": "drill-001",
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

    app = AOTApp(None, data_dir=plugin_data_dir)
    async with app.run_test() as pilot:
        await pilot.pause()
        # Home → press Enter (select "Sessions" menu item)
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "SessionsScreen"
        # Sessions → press Enter on the highlighted row → Timeline
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "TimelineScreen"


@pytest.mark.skipif(not is_available(), reason="textual not installed")
@pytest.mark.asyncio
async def test_enter_on_event_row_drills_into_event_detail(plugin_data_dir):
    """Regression: same DataTable-eats-Enter issue on the Timeline screen.
    Pressing Enter on an event row must reach the Event Detail screen."""
    from core.recorder import append_event
    from tui.app import AOTApp

    append_event(
        {
            "v": 1,
            "engine": "claude-code",
            "event_type": "user_prompt",
            "session_id": "drill-002",
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

    app = AOTApp("drill-002", data_dir=plugin_data_dir)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.__class__.__name__ == "TimelineScreen"
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "EventDetailScreen"


@pytest.mark.skipif(not is_available(), reason="textual not installed")
@pytest.mark.asyncio
async def test_navigation_deep_link_session(plugin_data_dir):
    """`aot tui --session <id>` puts Home → Sessions → Timeline on the
    stack, so Esc/Esc/Esc walks the user back to Home cleanly."""
    from core.recorder import append_event
    from tui.app import AOTApp

    append_event(
        {
            "v": 1,
            "engine": "claude-code",
            "event_type": "user_prompt",
            "session_id": "deeplink-002",
            "ts": "2026-05-15T10:00:00.000+00:00",
            "cwd": "/p",
            "user_prompt_text": "hello",
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

    app = AOTApp("deeplink-002", data_dir=plugin_data_dir)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.__class__.__name__ == "TimelineScreen"
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "SessionsScreen"
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "HomeScreen"
