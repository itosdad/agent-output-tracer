"""Textual application for `aot tui` (DESIGN_FORENSIC_UX §5).

Side-channel forensic UI: runs in its own process, reads
events.jsonl with a polling follower, never talks to the agent
process. Two-pane layout:

  ┌─ session list ──┬─ main pane ─────────────────────────┐
  │ ● current        │  timeline (event rows)              │
  │ ○ recent N       │                                     │
  │                  │                                     │
  └──────────────────┴─────────────────────────────────────┘
  status bar: session id · engine · event count · hints

Keybinds (subset; remaining modes ship incrementally):
  j / ↓        next event
  k / ↑        previous event
  g / G        jump to top / bottom
  s            session picker (switch current)
  r            refresh session list
  /            quick search filter on the timeline
  o            toggle live-follow on the current session
  q / esc      quit

Optional dep — only loaded when `aot tui` is run.
"""

from __future__ import annotations

import threading

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Header, Input, Static

from core.follower import follow_events
from core.session_io import list_sessions, load_events
from core.session_resolver import resolve_session_id
from core.time_utils import short_time, truncate


class SessionPicker(ModalScreen[str]):
    """Modal that surfaces every session and returns the chosen id."""

    BINDINGS = [
        Binding("escape", "dismiss", "cancel"),
    ]

    def __init__(self, data_dir, current_id: str | None):
        super().__init__()
        self._data_dir = data_dir
        self._current_id = current_id

    def compose(self) -> ComposeResult:
        table = DataTable(id="session-picker-table")
        table.cursor_type = "row"
        table.add_columns("session", "engine", "events", "ts_end")
        yield Vertical(
            Static("Pick a session (Enter = select, Esc = cancel)"),
            table,
        )

    def on_mount(self) -> None:
        table = self.query_one("#session-picker-table", DataTable)
        for meta in list_sessions(data_dir=self._data_dir):
            sid = meta.get("session_id") or "?"
            mark = "●" if sid == self._current_id else " "
            table.add_row(
                f"{mark} {sid[:12]}",
                meta.get("engine") or "?",
                str(meta.get("tool_calls_total", 0)),
                short_time(meta.get("ts_end")),
                key=sid,
            )
        table.focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.dismiss(event.row_key.value)


class AOTApp(App):
    """The main TUI. `--session` chooses the initial session."""

    CSS = """
    Screen {
        layers: base overlay;
    }
    #left {
        width: 32;
        border-right: solid $panel;
    }
    #main {
        width: 1fr;
    }
    #status {
        dock: bottom;
        height: 1;
        background: $panel;
        color: $text;
    }
    """

    BINDINGS = [
        Binding("j,down", "cursor_down", "next event"),
        Binding("k,up", "cursor_up", "prev event"),
        Binding("g", "scroll_top", "top"),
        Binding("G", "scroll_bottom", "bottom"),
        Binding("s", "pick_session", "session"),
        Binding("r", "refresh", "refresh"),
        Binding("o", "toggle_follow", "follow"),
        Binding("slash", "search", "search"),
        Binding("q,escape", "quit", "quit"),
    ]

    session_id: reactive[str] = reactive("", recompose=False)
    follow_enabled: reactive[bool] = reactive(False)

    def __init__(self, session_id: str, data_dir=None):
        super().__init__()
        self._data_dir = data_dir
        self.session_id = session_id
        self._follower_thread: threading.Thread | None = None
        self._follower_stop = threading.Event()
        self._search_term: str = ""

    # --- layout ---

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Horizontal(
            Vertical(
                Static("[b]Sessions[/b]", id="sessions-label"),
                DataTable(id="session-list"),
                id="left",
            ),
            Vertical(
                Static("[b]Timeline[/b]", id="timeline-label"),
                DataTable(id="timeline"),
                id="main",
            ),
        )
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        self._setup_session_list()
        self._setup_timeline()
        self._refresh_timeline()
        self._update_status()

    def _setup_session_list(self) -> None:
        table = self.query_one("#session-list", DataTable)
        table.cursor_type = "row"
        table.add_columns("id", "engine", "events")
        self._reload_session_rows()

    def _reload_session_rows(self) -> None:
        table = self.query_one("#session-list", DataTable)
        table.clear()
        for meta in list_sessions(data_dir=self._data_dir):
            sid = meta.get("session_id") or "?"
            mark = "●" if sid == self.session_id else "○"
            table.add_row(
                f"{mark} {sid[:8]}",
                (meta.get("engine") or "?")[:6],
                str(meta.get("tool_calls_total", 0)),
                key=sid,
            )

    def _setup_timeline(self) -> None:
        table = self.query_one("#timeline", DataTable)
        table.cursor_type = "row"
        table.add_columns("ts", "type", "tool/path", "body")

    def _refresh_timeline(self) -> None:
        table = self.query_one("#timeline", DataTable)
        table.clear()
        events = load_events(self.session_id, data_dir=self._data_dir) if self.session_id else []
        for i, ev in enumerate(events):
            row = _render_row(ev)
            if self._search_term and self._search_term.lower() not in " ".join(row).lower():
                continue
            table.add_row(*row, key=str(i))

    # --- actions ---

    def action_cursor_down(self) -> None:
        self.query_one("#timeline", DataTable).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#timeline", DataTable).action_cursor_up()

    def action_scroll_top(self) -> None:
        table = self.query_one("#timeline", DataTable)
        if table.row_count > 0:
            table.move_cursor(row=0)

    def action_scroll_bottom(self) -> None:
        table = self.query_one("#timeline", DataTable)
        if table.row_count > 0:
            table.move_cursor(row=table.row_count - 1)

    def action_refresh(self) -> None:
        self._reload_session_rows()
        self._refresh_timeline()
        self._update_status()

    async def action_pick_session(self) -> None:
        chosen = await self.push_screen_wait(SessionPicker(self._data_dir, self.session_id))
        if chosen:
            self._stop_follower()
            self.session_id = chosen
            self.action_refresh()

    def action_toggle_follow(self) -> None:
        if self.follow_enabled:
            self._stop_follower()
            self.follow_enabled = False
        else:
            self._start_follower()
            self.follow_enabled = True
        self._update_status()

    def action_search(self) -> None:
        self.push_screen(_SearchPrompt(self._search_term), self._apply_search)

    def action_quit(self) -> None:
        self._stop_follower()
        self.exit()

    # --- follower thread ---

    def _start_follower(self) -> None:
        if self._follower_thread and self._follower_thread.is_alive():
            return
        self._follower_stop.clear()
        sid = self.session_id
        data_dir = self._data_dir

        def runner() -> None:
            for _ in follow_events(
                sid,
                data_dir=data_dir,
                from_start=False,
                poll_interval=0.5,
                stop_predicate=self._follower_stop.is_set,
            ):
                self.call_from_thread(self._refresh_timeline)
                self.call_from_thread(self._update_status)

        self._follower_thread = threading.Thread(target=runner, daemon=True)
        self._follower_thread.start()

    def _stop_follower(self) -> None:
        self._follower_stop.set()
        self._follower_thread = None

    # --- search ---

    def _apply_search(self, term: str | None) -> None:
        if term is None:
            return
        self._search_term = term
        self._refresh_timeline()

    # --- status ---

    def _update_status(self) -> None:
        status = self.query_one("#status", Static)
        table = self.query_one("#timeline", DataTable)
        flag = "FOLLOW" if self.follow_enabled else "static"
        sid = self.session_id[:12] if self.session_id else "(none)"
        status.update(f" {sid} · events={table.row_count} · {flag} · q quit")


class _SearchPrompt(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "dismiss", "cancel")]

    def __init__(self, initial: str):
        super().__init__()
        self._initial = initial

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static("Filter (Enter to apply, Esc to cancel):"),
            Input(value=self._initial, id="search-input"),
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)


def _render_row(ev: dict) -> tuple[str, str, str, str]:
    ts = short_time(ev.get("ts"))
    et = ev.get("event_type") or "?"
    tool_or_path = ev.get("tool_name") or ""
    paths = ev.get("paths") or []
    if paths:
        tool_or_path = (tool_or_path + " " + paths[0]).strip()
    body = (
        ev.get("user_prompt_text")
        or ev.get("agent_response_text")
        or ev.get("command")
        or ev.get("tool_response")
        or ""
    )
    return (ts, et, truncate(tool_or_path, 30), truncate(body, 60))


# ------------- entry point -------------


def run(session_spec: str = "latest", *, data_dir=None) -> int:
    """Resolve the session and start the textual app loop."""
    sid = resolve_session_id(session_spec, data_dir=data_dir)
    app = AOTApp(sid, data_dir=data_dir)
    app.run()
    return 0
