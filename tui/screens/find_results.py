"""Find results screen — the match list for one (vocab, session).

Runs `query.find.find(session, vocab)` once on mount and renders each
match as a 2-line card. Enter on a match drills into Event Detail
for the source event.
"""

from __future__ import annotations

from rich.text import Text
from textual.binding import Binding
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from core.session_io import load_events
from core.session_resolver import resolve_session_id
from core.time_utils import short_time
from query.find import find as _find
from tui.router import AOTScreen


class FindResultsScreen(AOTScreen):
    TITLE = "find"

    DEFAULT_CSS = """
    FindResultsScreen > .body {
        align: center middle;
    }
    FindResultsScreen #find-results-list {
        width: 100%;
        max-width: 120;
    }
    """

    BINDINGS = [
        Binding("enter", "open", "detail", show=False),
        Binding("r", "refresh", "refresh", show=False),
    ]

    def __init__(
        self,
        *,
        vocab: str,
        session_id: str = "latest",
        threshold: int | None = None,
        data_dir=None,
    ) -> None:
        self.vocab = vocab
        self.session_id = session_id
        self.threshold = threshold
        self._data_dir = data_dir
        self._matches: list[dict] = []
        self._events: list[dict] = []
        self._resolved_sid: str = session_id
        super().__init__()

    def breadcrumb_segments(self) -> list[str]:
        return ["agent-output-tracer", "find", self.vocab, self._resolved_sid[:8] or "?"]

    def footer_hints(self) -> list[tuple[str, str]]:
        return [
            ("↑↓", "step"),
            ("g/G", "top/bot"),
            ("enter", "detail"),
            ("r", "refresh"),
            ("esc", "back"),
        ]

    def help_entries(self) -> list[tuple[str, str]]:
        return [
            ("↑↓", "step through matches"),
            ("g / G", "first / last match"),
            ("enter", "open the source event"),
            ("r", "re-run find on this session"),
        ]

    def compose_body(self):
        yield OptionList(id="find-results-list")

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
        event_idx = self._matches[match_idx].get("event_idx")
        if not isinstance(event_idx, int):
            return
        if event_idx < 0 or event_idx >= len(self._events):
            return
        event = self._events[event_idx]
        from tui.screens.event_detail import EventDetailScreen

        self.app.push_screen(
            EventDetailScreen(
                event=event,
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

        kwargs: dict = {"data_dir": self._data_dir, "stream": _NullStream()}
        if self.threshold is not None:
            kwargs["threshold"] = self.threshold
        try:
            result = _find(resolved, self.vocab, **kwargs)
            self._matches = result.get("matches") or []
        except Exception as exc:
            self._matches = []
            self._show_error(str(exc))
            return

        ol = self.query_one(OptionList)
        ol.clear_options()
        try:
            from tui.widgets.breadcrumb import Breadcrumb

            self.query_one(Breadcrumb).set_segments(self.breadcrumb_segments())
        except Exception:
            pass
        if not self._matches:
            empty = Text()
            empty.append(f"(no matches for '{self.vocab}' in this session)\n", style="dim")
            empty.append(
                "   This is the healthy outcome — the detector ran and\n",
                style="dim",
            )
            empty.append("   nothing tripped it. Press ", style="dim")
            empty.append("esc", style="bold")
            empty.append(" to try a different vocab.", style="dim")
            ol.add_option(Option(empty))
            return
        # OptionList enforces unique ids. Several hallucinations matches
        # can share the same `event_idx` (one agent_response, many tokens
        # extracted), so we identify rows by `match-<index>` and store
        # the underlying event_idx separately for drill-in.
        from tui._accent import warning

        warn_col = warning(self.app)
        for i, m in enumerate(self._matches):
            try:
                ol.add_option(Option(_render_match(m, warn_col=warn_col), id=f"match-{i}"))
            except Exception:
                continue
        ol.highlighted = 0

    def _show_error(self, msg: str) -> None:
        from tui._accent import error

        ol = self.query_one(OptionList)
        ol.clear_options()
        ol.add_option(Option(Text(f"error: {msg}", style=error(self.app))))


class _NullStream:
    """`query.find.find` writes its CLI-style rendering to a stream;
    the TUI ignores it and reads the structured result dict instead."""

    def write(self, _s: str) -> int:
        return 0

    def flush(self) -> None:
        return None


def _render_match(m: dict, *, warn_col: str = "yellow") -> Text:
    """Two-line card for one match. Line 1: ts + key fact; line 2:
    secondary fields. Compact enough for half-desktop layouts."""
    ts = short_time(m.get("ts"))
    text = Text()
    text.append("•  ", style=f"bold {warn_col}")
    text.append(ts, style="dim")
    text.append("  event ", style="dim")
    text.append(str(m.get("event_idx", "?")), style="bold")

    # Line 2: kind-specific summary
    line2_parts: list[str] = []
    for key in ("path", "token", "tool"):
        v = m.get(key)
        if v is not None:
            line2_parts.append(f"{key}={v}")
    for key in ("count", "size_bytes", "pattern"):
        v = m.get(key)
        if v is not None:
            line2_parts.append(f"{key}={v}")
    if line2_parts:
        text.append("\n   ")
        text.append("  ·  ".join(line2_parts), style="dim")
    return text
