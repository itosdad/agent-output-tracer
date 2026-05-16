"""Search results screen — regex matches across one session's events.

Walks the same fields `query.grep` searches and renders each match as
a 2-line card: ts + event-type.field, then a truncated preview of the
matching text. Enter on a match drills into the source event's Event
Detail.
"""

from __future__ import annotations

import re

from rich.text import Text
from textual.binding import Binding
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from core.session_io import load_events
from core.session_resolver import resolve_session_id
from core.time_utils import short_time, truncate
from query.grep import _iter_searchable
from tui.router import AOTScreen

PREVIEW_LIMIT = 120


class SearchResultsScreen(AOTScreen):
    TITLE = "search"

    BINDINGS = [
        Binding("enter", "open", "open event", show=False),
        Binding("r", "refresh", "refresh", show=False),
    ]

    def __init__(
        self,
        *,
        pattern: str,
        session_id: str = "latest",
        data_dir=None,
    ) -> None:
        self.pattern = pattern
        self.session_id = session_id
        self._data_dir = data_dir
        self._matches: list[tuple[int, dict]] = []
        self._events: list[dict] = []
        self._resolved_sid: str = ""
        super().__init__()

    def breadcrumb_segments(self) -> list[str]:
        preview = self.pattern[:18] + ("…" if len(self.pattern) > 18 else "")
        return ["agent-output-tracer", "search", repr(preview)]

    def footer_hints(self) -> list[tuple[str, str]]:
        return [
            ("↑↓", "step"),
            ("g/G", "top/bot"),
            ("enter", "open event"),
            ("r", "refresh"),
            ("esc", "back"),
        ]

    def help_entries(self) -> list[tuple[str, str]]:
        return [
            ("↑↓", "step through matches"),
            ("g / G", "first / last match"),
            ("enter", "open source event"),
            ("r", "re-run search"),
        ]

    def compose_body(self):
        yield OptionList(id="search-results-list")

    def on_mount(self) -> None:
        self._reload()
        self.query_one(OptionList).focus()

    def action_refresh(self) -> None:
        self._reload()

    def action_open(self) -> None:
        self._open_highlighted()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._open_by_id(event.option.id or "")

    def _open_highlighted(self) -> None:
        ol = self.query_one(OptionList)
        idx = ol.highlighted
        if idx is None:
            return
        try:
            opt = ol.get_option_at_index(idx)
        except Exception:
            return
        self._open_by_id(opt.id or "")

    def _open_by_id(self, opt_id: str) -> None:
        if not opt_id or not opt_id.startswith("match-"):
            return
        try:
            match_idx = int(opt_id.split("-", 1)[1])
        except (TypeError, ValueError):
            return
        if match_idx < 0 or match_idx >= len(self._matches):
            return
        event_idx, _m = self._matches[match_idx]
        if event_idx < 0 or event_idx >= len(self._events):
            return
        from tui.screens.event_detail import EventDetailScreen

        self.app.push_screen(
            EventDetailScreen(
                event=self._events[event_idx],
                event_index=event_idx,
                session_id=self._resolved_sid,
                all_events=self._events,
                data_dir=self._data_dir,
            )
        )

    def _reload(self) -> None:
        try:
            resolved = resolve_session_id(self.session_id, data_dir=self._data_dir)
        except Exception:
            resolved = self.session_id
        self._resolved_sid = resolved or ""
        try:
            self._events = load_events(resolved, data_dir=self._data_dir)
        except Exception:
            self._events = []

        ol = self.query_one(OptionList)
        ol.clear_options()
        try:
            from tui.widgets.breadcrumb import Breadcrumb

            self.query_one(Breadcrumb).set_segments(self.breadcrumb_segments())
        except Exception:
            pass

        from tui._accent import error, warning

        try:
            regex = re.compile(self.pattern)
        except re.error as exc:
            ol.add_option(Option(Text(f"invalid regex: {exc}", style=error(self.app))))
            return

        self._matches = []
        for i, ev in enumerate(self._events):
            for field, text in _iter_searchable(ev):
                if regex.search(text):
                    self._matches.append((i, {"field": field, "text": text, "ev": ev}))

        if not self._matches:
            empty = Text()
            empty.append(f"(no matches for /{self.pattern}/)\n", style="dim")
            empty.append("   Python `re` syntax: ", style="dim")
            empty.append("|", style="bold")
            empty.append(" alternation, ", style="dim")
            empty.append("(?i)", style="bold")
            empty.append(" case-insensitive, ", style="dim")
            empty.append("\\b", style="bold")
            empty.append(" word boundary.", style="dim")
            ol.add_option(Option(empty))
            return

        # Same caveat as FindResults: many matches can share one
        # event_idx (the same event has the pattern in several fields).
        warn_col = warning(self.app)
        for i, (event_idx, m) in enumerate(self._matches):
            try:
                ol.add_option(
                    Option(_render_match(event_idx, m, warn_col=warn_col), id=f"match-{i}")
                )
            except Exception:
                continue
        ol.highlighted = 0


def _render_match(event_idx: int, m: dict, *, warn_col: str = "yellow") -> Text:
    ev = m["ev"]
    text = Text()
    text.append("•  ", style=f"bold {warn_col}")
    text.append(short_time(ev.get("ts")), style="dim")
    text.append("  ")
    text.append(f"{ev.get('event_type', '?')}.{m['field']}", style="")
    text.append("  ·  ", style="dim")
    text.append(f"event {event_idx}", style="dim")
    text.append("\n   ")
    preview = truncate(str(m["text"]).replace("\n", " "), PREVIEW_LIMIT)
    text.append(preview)
    return text
