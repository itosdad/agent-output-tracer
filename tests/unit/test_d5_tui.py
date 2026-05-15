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
async def test_esc_on_home_is_noop_not_freeze(plugin_data_dir):
    """Regression: pressing Esc on Home must NOT pop the screen stack.

    Textual's default empty Screen sits at stack index 0; if we pop
    Home (stack index 1), that default empty Screen takes the viewport
    with no widgets, no bindings, no breadcrumb — and the user
    experiences a frozen TUI. v0.7.1 shipped with this bug.
    """
    from tui.app import AOTApp

    app = AOTApp(None, data_dir=plugin_data_dir)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.__class__.__name__ == "HomeScreen"
        depth_before = len(app.screen_stack)
        await pilot.press("escape")
        await pilot.pause()
        # Stack depth must not shrink and Home must stay on top.
        assert len(app.screen_stack) == depth_before
        assert app.screen.__class__.__name__ == "HomeScreen"


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
async def test_find_hallucinations_with_multiple_tokens_per_event(plugin_data_dir):
    """Regression for v0.9.6: a single agent_response can be the source
    of many hallucinations (one per extracted token). The find-results
    OptionList was keying options by event_idx and crashed with
    `DuplicateID` the moment the second token was added.
    """
    from core.recorder import append_event
    from tui.app import AOTApp
    from tui.screens.find_results import FindResultsScreen

    base = {
        "v": 1,
        "engine": "claude-code",
        "session_id": "dup-001",
        "cwd": "/p",
        "tool_name": None,
        "tool_input": None,
        "tool_response": None,
        "agent_response_text": None,
        "user_prompt_text": None,
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
            "ts": "2026-05-15T10:00:00.000+00:00",
            "user_prompt_text": "go",
        },
        data_dir=plugin_data_dir,
    )
    # Single agent response, three ungrounded tokens → three hits on
    # the same event_idx.
    append_event(
        {
            **base,
            "event_type": "agent_response",
            "ts": "2026-05-15T10:00:01.000+00:00",
            "agent_response_text": (
                "I'll check /a/b.md plus https://x.example/foo and Terminal.app"
            ),
        },
        data_dir=plugin_data_dir,
    )

    app = AOTApp(None, data_dir=plugin_data_dir)
    async with app.run_test() as pilot:
        await pilot.pause()
        # Drill through Home → Find → hallucinations via the palette
        # (shortest path to FindResultsScreen).
        from textual.widgets import Input, OptionList

        await pilot.press("colon")
        await pilot.pause()
        app.screen.query_one(Input).value = "find hallucinations"
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, FindResultsScreen)
        ol = app.screen.query_one(OptionList)
        # 3 matches must coexist without DuplicateID.
        assert ol.option_count >= 2


@pytest.mark.skipif(not is_available(), reason="textual not installed")
@pytest.mark.asyncio
async def test_palette_routes_to_doctor(plugin_data_dir):
    """`:doctor` ⏎ should dismiss the palette and push DoctorScreen."""
    from textual.widgets import Input

    from tui.app import AOTApp
    from tui.screens.palette import CommandPalette

    app = AOTApp(None, data_dir=plugin_data_dir)
    async with app.run_test() as pilot:
        await pilot.pause()
        # Open palette via the bound `:` key.
        await pilot.press("colon")
        await pilot.pause()
        assert isinstance(app.screen, CommandPalette)

        inp = app.screen.query_one(Input)
        inp.value = "doctor"
        await pilot.press("enter")
        await pilot.pause()
        # Palette dismissed, DoctorScreen on top.
        assert app.screen.__class__.__name__ == "DoctorScreen"


@pytest.mark.skipif(not is_available(), reason="textual not installed")
@pytest.mark.asyncio
async def test_palette_routes_to_find_with_vocab(plugin_data_dir):
    """`:find hallucinations` should jump straight to results."""
    from textual.widgets import Input

    from core.recorder import append_event
    from tui.app import AOTApp

    base = {
        "v": 1,
        "engine": "claude-code",
        "session_id": "pal-001",
        "cwd": "/p",
        "tool_name": None,
        "tool_input": None,
        "tool_response": None,
        "agent_response_text": None,
        "user_prompt_text": None,
        "stop_reason": None,
        "paths": [],
        "command": None,
        "result_bytes": 0,
        "raw_event": {},
    }
    append_event(
        {
            **base,
            "event_type": "agent_response",
            "ts": "2026-05-15T10:00:01.000+00:00",
            "agent_response_text": "let me check /proj/ghost.md",
        },
        data_dir=plugin_data_dir,
    )

    app = AOTApp(None, data_dir=plugin_data_dir)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("colon")
        await pilot.pause()
        inp = app.screen.query_one(Input)
        inp.value = "find hallucinations"
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "FindResultsScreen"


@pytest.mark.skipif(not is_available(), reason="textual not installed")
@pytest.mark.asyncio
async def test_home_drills_into_trace_then_results(plugin_data_dir):
    """Home → Trace → type phrase → enter → TraceResults."""
    from textual.widgets import Input, OptionList, Static

    from core.recorder import append_event
    from tui.app import AOTApp

    base = {
        "v": 1,
        "engine": "claude-code",
        "session_id": "trace-001",
        "cwd": "/p",
        "tool_name": None,
        "tool_input": None,
        "tool_response": None,
        "agent_response_text": None,
        "user_prompt_text": None,
        "stop_reason": None,
        "paths": [],
        "command": None,
        "result_bytes": 0,
        "raw_event": {},
    }
    append_event(
        {
            **base,
            "event_type": "agent_response",
            "ts": "2026-05-15T10:00:01.000+00:00",
            "agent_response_text": "I checked the hooks_wiring setup",
        },
        data_dir=plugin_data_dir,
    )

    app = AOTApp(None, data_dir=plugin_data_dir)
    async with app.run_test() as pilot:
        await pilot.pause()
        ol = app.screen.query_one(OptionList)
        ol.highlighted = 2  # Trace
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "TraceScreen"

        inp = app.screen.query_one(Input)
        inp.value = "hooks_wiring"
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "TraceResultsScreen"

        body = app.screen.query_one("#trace-body", Static)
        text = str(body.content)
        assert "First mention" in text


@pytest.mark.skipif(not is_available(), reason="textual not installed")
@pytest.mark.asyncio
async def test_home_drills_into_find_then_results_then_event(plugin_data_dir):
    """Full Phase 2.C path: Home → Find → vocab pick → FindResults →
    Enter on a match → EventDetail."""
    from textual.widgets import OptionList

    from core.recorder import append_event
    from tui.app import AOTApp

    # Seed a session where 'hallucinations' will definitely fire:
    # agent names a path nobody mentioned and no Read produced.
    base_ev = {
        "v": 1,
        "engine": "claude-code",
        "session_id": "find-001",
        "cwd": "/p",
        "tool_name": None,
        "tool_input": None,
        "tool_response": None,
        "agent_response_text": None,
        "user_prompt_text": None,
        "stop_reason": None,
        "paths": [],
        "command": None,
        "result_bytes": 0,
        "raw_event": {},
    }
    append_event(
        {
            **base_ev,
            "event_type": "user_prompt",
            "ts": "2026-05-15T10:00:00.000+00:00",
            "user_prompt_text": "do something",
        },
        data_dir=plugin_data_dir,
    )
    append_event(
        {
            **base_ev,
            "event_type": "agent_response",
            "ts": "2026-05-15T10:00:01.000+00:00",
            "agent_response_text": "Reading /proj/ghost.md to investigate",
        },
        data_dir=plugin_data_dir,
    )

    app = AOTApp(None, data_dir=plugin_data_dir)
    async with app.run_test() as pilot:
        await pilot.pause()

        # Home → Find (index 1)
        ol = app.screen.query_one(OptionList)
        ol.highlighted = 1
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "FindScreen"

        # Pick 'hallucinations' — it's the 6th entry (index 5) in VOCAB.
        # We could rely on default ordering; safer to find by id.
        ol = app.screen.query_one(OptionList)
        for i in range(ol.option_count):
            if ol.get_option_at_index(i).id == "hallucinations":
                ol.highlighted = i
                break
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "FindResultsScreen"

        # Enter on the first match → EventDetail
        ol = app.screen.query_one(OptionList)
        assert ol.option_count >= 1
        # If the first row is a "no matches" placeholder it has no id.
        first = ol.get_option_at_index(0)
        assert first.id is not None, "expected at least one hallucination match"
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "EventDetailScreen"


@pytest.mark.skipif(not is_available(), reason="textual not installed")
@pytest.mark.asyncio
async def test_home_drills_into_doctor(plugin_data_dir):
    """Home → Doctor menu item lands on DoctorScreen, which renders the
    same check vocabulary the CLI uses."""
    from textual.widgets import OptionList, Static

    from tui.app import AOTApp

    app = AOTApp(None, data_dir=plugin_data_dir)
    async with app.run_test() as pilot:
        await pilot.pause()
        ol = app.screen.query_one(OptionList)
        # Doctor is the 6th menu entry (index 5: sessions, find, trace,
        # search, stats, doctor).
        ol.highlighted = 5
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "DoctorScreen"
        body = app.screen.query_one("#doctor-body", Static)
        text = str(body.content)
        assert "runtime" in text


@pytest.mark.skipif(not is_available(), reason="textual not installed")
@pytest.mark.asyncio
async def test_home_drills_into_stats_with_seeded_session(plugin_data_dir):
    """Home → Stats opens the StatsScreen which resolves `latest` to
    the seeded session and renders its metrics."""
    from textual.widgets import OptionList, Static

    from core.recorder import append_event
    from tui.app import AOTApp

    append_event(
        {
            "v": 1,
            "engine": "claude-code",
            "event_type": "user_prompt",
            "session_id": "stat-001",
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
        ol = app.screen.query_one(OptionList)
        ol.highlighted = 4  # Stats
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "StatsScreen"
        body = app.screen.query_one("#stats-body", Static)
        text = str(body.content)
        assert "stat-001" in text  # resolved session id surfaces in the card
        assert "claude-code" in text


@pytest.mark.skipif(not is_available(), reason="textual not installed")
@pytest.mark.asyncio
async def test_help_overlay_opens_and_closes_on_any_key(plugin_data_dir):
    """`?` pushes a HelpOverlay modal and any keypress dismisses it."""
    from tui.app import AOTApp
    from tui.screens.help import HelpOverlay

    app = AOTApp(None, data_dir=plugin_data_dir)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.__class__.__name__ == "HomeScreen"
        depth_before = len(app.screen_stack)

        # Open help.
        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpOverlay)
        assert len(app.screen_stack) == depth_before + 1

        # Any key dismisses — try Enter, which on Home would normally
        # drill into Sessions but should NOT bleed through here.
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "HomeScreen"
        assert len(app.screen_stack) == depth_before


@pytest.mark.skipif(not is_available(), reason="textual not installed")
@pytest.mark.asyncio
async def test_help_overlay_shows_screen_and_global_keybinds(plugin_data_dir):
    """The rendered help text must include both this-screen entries
    and the universal global entries (`q`, `:`, `?`, `g/G`)."""
    from textual.widgets import Static

    from tui.app import AOTApp
    from tui.screens.help import HelpOverlay

    app = AOTApp(None, data_dir=plugin_data_dir)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpOverlay)

        body = app.screen.query_one("#help-body", Static)
        text = str(body.content)
        assert "This screen" in text
        assert "Global" in text
        assert "q" in text
        assert "quit" in text
        assert ":" in text
        assert "g / Home" in text  # global jump-top entry


@pytest.mark.skipif(not is_available(), reason="textual not installed")
@pytest.mark.asyncio
async def test_g_G_jump_top_and_bottom(plugin_data_dir):
    """vim-style top/bottom jumps on the focused list:
    `g` (or Home) → first row, `G` (or End) → last row."""
    from textual.widgets import OptionList

    from core.recorder import append_event
    from tui.app import AOTApp

    # 10 events so first ≠ last.
    for i in range(10):
        append_event(
            {
                "v": 1,
                "engine": "claude-code",
                "event_type": "user_prompt",
                "session_id": "jump-001",
                "ts": f"2026-05-15T10:00:0{i}.000+00:00",
                "cwd": "/p",
                "user_prompt_text": f"event {i}",
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

    app = AOTApp("jump-001", data_dir=plugin_data_dir)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.__class__.__name__ == "TimelineScreen"
        ol = app.screen.query_one(OptionList)
        # Initially highlighted on row 0 by _reload.
        assert ol.highlighted == 0

        # G → bottom
        await pilot.press("G")
        await pilot.pause()
        assert ol.highlighted == ol.option_count - 1

        # g → top
        await pilot.press("g")
        await pilot.pause()
        assert ol.highlighted == 0

        # End → bottom (alternate keybind)
        await pilot.press("end")
        await pilot.pause()
        assert ol.highlighted == ol.option_count - 1

        # Home → top (alternate keybind)
        await pilot.press("home")
        await pilot.pause()
        assert ol.highlighted == 0


@pytest.mark.skipif(not is_available(), reason="textual not installed")
@pytest.mark.asyncio
async def test_no_horizontal_overflow_at_half_desktop_width(plugin_data_dir):
    """The TUI must fit a 72-column viewport (the realistic minimum for
    a typical half-desktop terminal pane) without producing a
    horizontal scrollbar on any of the primary screens.

    We seed a session with one event whose body is long enough that an
    old column-based renderer would have forced horizontal scroll.
    """
    from textual.widgets import OptionList

    from core.recorder import append_event
    from tui.app import AOTApp

    long_body = (
        "describe phase D in detail — the plan and the layout we want, "
        "specifically the screen-based navigation, semantic prefixes, "
        "Codex theme tokens cited from openai/codex tui/src/, and the "
        "drill-in/out flow used by sessions and timeline screens."
    )
    append_event(
        {
            "v": 1,
            "engine": "claude-code",
            "event_type": "user_prompt",
            "session_id": "narrow-001",
            "ts": "2026-05-15T10:00:00.000+00:00",
            "cwd": "/p",
            "user_prompt_text": long_body,
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
    async with app.run_test(size=(72, 24)) as pilot:
        await pilot.pause()
        # Home — no horizontal scrollbar on the OptionList.
        ol = app.screen.query_one(OptionList)
        assert ol.show_horizontal_scrollbar is False

        # Drill into Sessions and confirm.
        await pilot.press("enter")
        await pilot.pause()
        ol = app.screen.query_one(OptionList)
        assert ol.show_horizontal_scrollbar is False

        # Drill into Timeline and confirm. The long body event must
        # render without a horizontal scrollbar at 72 cols.
        await pilot.press("enter")
        await pilot.pause()
        ol = app.screen.query_one(OptionList)
        assert ol.show_horizontal_scrollbar is False

        # Drill into Event Detail and confirm. Static content auto-wraps
        # so no horizontal scrollbar on its scroll container either.
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
