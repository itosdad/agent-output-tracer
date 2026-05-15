"""Timeline screen — events for one session, in order.

Renders each event with a semantic prefix glyph (Codex theme):
  ›  user_prompt        bold dim
  ⏵  pre_tool           accent
  ✓  post_tool          green (success) / red (error)
  •  agent_response     accent
  ─  session_end / system markers

Body is truncated; Enter drills into Event Detail for the full payload.
`o` toggles live follow. `/` opens an inline filter prompt.
"""

from __future__ import annotations

from textual.binding import Binding
from textual.widgets import DataTable

from core.session_io import list_sessions, load_events
from core.time_utils import short_time, truncate
from tui.router import AOTScreen

_PREFIX = {
    "user_prompt": "›",
    "pre_tool": "⏵",
    "post_tool": "✓",
    "agent_response": "•",
    "session_start": "─",
    "session_end": "─",
    "pre_compact": "─",
    "post_compact": "─",
}


class TimelineScreen(AOTScreen):
    BINDINGS = [
        Binding("enter", "open", "detail", show=False),
        Binding("o", "toggle_follow", "follow", show=False),
        Binding("r", "refresh", "refresh", show=False),
        Binding("slash", "search", "search", show=False),
    ]

    TITLE = "timeline"

    def __init__(self, session_id: str, *, data_dir=None) -> None:
        self.session_id = session_id
        self._data_dir = data_dir
        self._search_term: str = ""
        self._events: list[dict] = []
        self._follow: bool = False
        super().__init__()

    def breadcrumb_segments(self) -> list[str]:
        return ["aot", self.session_id[:8], "timeline"]

    def footer_hints(self) -> list[tuple[str, str]]:
        return [
            ("↑↓", "scroll"),
            ("enter", "detail"),
            ("o", "follow" if not self._follow else "stop follow"),
            ("/", "search"),
            ("esc", "back"),
        ]

    def compose_body(self):
        table = DataTable(id="timeline-table")
        table.cursor_type = "row"
        table.add_columns("", "ts", "type", "tool / path", "body")
        yield table

    def on_mount(self) -> None:
        self._reload()
        table = self.query_one(DataTable)
        table.focus()

    def action_refresh(self) -> None:
        self._reload()

    def action_open(self) -> None:
        # See SessionsScreen — DataTable swallows Enter via its own
        # action and emits RowSelected. We mirror the same pattern.
        self._open_cursor_row()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Primary drill-in path: DataTable's own Enter → RowSelected."""
        self._open_cursor_row()

    def _open_cursor_row(self) -> None:
        table = self.query_one(DataTable)
        if table.row_count == 0:
            return
        idx = table.cursor_row
        if idx < 0 or idx >= len(self._events):
            return
        event = self._events[idx]
        from tui.screens.event_detail import EventDetailScreen

        self.app.push_screen(
            EventDetailScreen(
                event=event,
                event_index=idx,
                session_id=self.session_id,
                all_events=self._events,
                data_dir=self._data_dir,
            )
        )

    def action_toggle_follow(self) -> None:
        # Phase 1: snap to bottom on demand; live follower thread is
        # already implemented in core.follower and will be wired here
        # as part of the chrome status indicator. For now `o` simply
        # refreshes and jumps to the newest event.
        self._follow = not self._follow
        self._reload()
        table = self.query_one(DataTable)
        if self._follow and table.row_count > 0:
            table.move_cursor(row=table.row_count - 1)
        # update footer hint label
        try:
            from tui.widgets.footer import FooterHints

            self.query_one(FooterHints).set_hints(self.footer_hints())
        except Exception:
            pass

    def action_search(self) -> None:
        # Phase 2 will mount an InlinePrompt; for now beep.
        self.app.bell()

    def _resolve_session(self) -> str:
        """Resolve 'latest' / prefix → concrete id."""
        if self.session_id != "latest":
            return self.session_id
        try:
            sessions = list_sessions(data_dir=self._data_dir)
        except Exception:
            return self.session_id
        if sessions:
            sid = sessions[0].get("session_id")
            if sid:
                self.session_id = sid
                # update breadcrumb
                try:
                    from tui.widgets.breadcrumb import Breadcrumb

                    self.query_one(Breadcrumb).set_segments(self.breadcrumb_segments())
                except Exception:
                    pass
        return self.session_id

    def _reload(self) -> None:
        self._resolve_session()
        table = self.query_one(DataTable)
        table.clear()
        try:
            events = load_events(self.session_id, data_dir=self._data_dir)
        except Exception:
            events = []
        self._events = events
        term = self._search_term.lower()
        for ev in events:
            row = _render_row(ev)
            if term and term not in " ".join(row).lower():
                continue
            table.add_row(*row)


def _render_row(ev: dict) -> tuple[str, str, str, str, str]:
    ts = short_time(ev.get("ts"))
    et = ev.get("event_type") or "?"
    prefix = _PREFIX.get(et, " ")
    tool = ev.get("tool_name") or ""
    paths = ev.get("paths") or []
    locus = tool
    if paths:
        locus = (tool + " " + paths[0]).strip()
    body = (
        ev.get("user_prompt_text")
        or ev.get("agent_response_text")
        or ev.get("command")
        or ev.get("tool_response")
        or ""
    )
    if not isinstance(body, str):
        body = str(body)
    return (prefix, ts, et, truncate(locus, 30), truncate(body, 60))
