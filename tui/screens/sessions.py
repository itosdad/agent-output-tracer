"""Sessions screen — list of captured sessions, newest first.

Enter drills into the selected session's Timeline screen.

Columns (kept minimal — the principle is list-pick-detail, not
all-info-at-once):
  marker  short session id  engine  ts_end  event count

Footer hints: ↑↓ select   enter open   o follow   / search   esc back.
"""

from __future__ import annotations

from textual.binding import Binding
from textual.widgets import DataTable

from core.session_io import list_sessions
from core.time_utils import short_time
from tui.router import AOTScreen


class SessionsScreen(AOTScreen):
    TITLE = "sessions"

    BINDINGS = [
        Binding("enter", "open", "open", show=False),
        Binding("r", "refresh", "refresh", show=False),
    ]

    def __init__(self, data_dir=None) -> None:
        super().__init__()
        self._data_dir = data_dir

    def breadcrumb_segments(self) -> list[str]:
        return ["aot", "sessions"]

    def footer_hints(self) -> list[tuple[str, str]]:
        return [
            ("↑↓", "select"),
            ("enter", "open"),
            ("r", "refresh"),
            ("esc", "back"),
            (":", "command"),
            ("?", "help"),
        ]

    def compose_body(self):
        table = DataTable(id="sessions-table")
        table.cursor_type = "row"
        table.add_columns("", "session", "engine", "ts_end", "events")
        yield table

    def on_mount(self) -> None:
        self._reload()
        table = self.query_one(DataTable)
        table.focus()

    def action_refresh(self) -> None:
        self._reload()

    def action_open(self) -> None:
        table = self.query_one(DataTable)
        if table.row_count == 0:
            return
        sid = table.get_row_at(table.cursor_row)[1]
        # Strip any cursor marker / styling — col 1 holds the full id.
        sid_str = str(sid)
        from tui.screens.timeline import TimelineScreen

        self.app.push_screen(TimelineScreen(sid_str, data_dir=self._data_dir))

    def _reload(self) -> None:
        table = self.query_one(DataTable)
        table.clear()
        try:
            sessions = list_sessions(data_dir=self._data_dir)
        except Exception:
            sessions = []
        for i, meta in enumerate(sessions):
            sid = meta.get("session_id") or "?"
            marker = "●" if i == 0 else " "
            table.add_row(
                marker,
                sid,
                meta.get("engine") or "?",
                short_time(meta.get("ts_end")),
                str(meta.get("tool_calls_total", 0)),
                key=sid,
            )
