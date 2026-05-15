"""Sessions screen — list of captured sessions, newest first.

Rendered as a vertical OptionList (not a multi-column DataTable) so
the screen stays readable at half-desktop widths (~72 cols) without
horizontal scrolling. Each session occupies two lines:

    ● 781ff3fa
      claude-code · 120 events · 19:42

The `●` marker tags the most-recent session; the cursor (Textual's
own highlight) shows the current selection.
"""

from __future__ import annotations

from rich.text import Text
from textual.binding import Binding
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from core.session_io import list_sessions
from core.time_utils import short_time
from tui.router import AOTScreen


class SessionsScreen(AOTScreen):
    TITLE = "sessions"

    BINDINGS = [
        Binding("enter", "open", "open", show=False),
        Binding("r", "refresh", "refresh", show=False),
        Binding("e", "export", "export", show=False),
    ]

    def __init__(self, data_dir=None) -> None:
        super().__init__()
        self._data_dir = data_dir
        # Parallel list of session ids in the order they were added,
        # so we can resolve `option.id` → session id quickly.
        self._sids: list[str] = []

    def breadcrumb_segments(self) -> list[str]:
        return ["aot", "sessions"]

    def footer_hints(self) -> list[tuple[str, str]]:
        return [
            ("↑↓", "select"),
            ("g/G", "top/bot"),
            ("enter", "open"),
            ("e", "export"),
            ("r", "refresh"),
            ("esc", "back"),
        ]

    def compose_body(self):
        yield OptionList(id="sessions-list")

    def on_mount(self) -> None:
        self._reload()
        self.query_one(OptionList).focus()

    def action_refresh(self) -> None:
        self._reload()

    def action_open(self) -> None:
        # OptionList handles Enter via its own action, which emits
        # `OptionList.OptionSelected`. We don't normally reach here.
        self._open_highlighted()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Primary drill-in path: OptionList's own Enter handler."""
        self._open_by_id(event.option.id or "")

    def _open_highlighted(self) -> None:
        ol = self.query_one(OptionList)
        idx = ol.highlighted
        if idx is None or idx < 0 or idx >= len(self._sids):
            return
        self._open_by_id(self._sids[idx])

    def _open_by_id(self, sid: str) -> None:
        if not sid:
            return
        from tui.screens.timeline import TimelineScreen

        self.app.push_screen(TimelineScreen(sid, data_dir=self._data_dir))

    def action_export(self) -> None:
        ol = self.query_one(OptionList)
        idx = ol.highlighted
        if idx is None or idx < 0 or idx >= len(self._sids):
            self.app.bell()
            return
        sid = self._sids[idx]
        from tui.screens.export_modal import ExportModal

        self.app.push_screen(
            ExportModal(session_short=sid[:8]),
            lambda values: _run_export(self.app, sid, values, self._data_dir),
        )

    def _reload(self) -> None:
        ol = self.query_one(OptionList)
        ol.clear_options()
        self._sids = []
        try:
            sessions = list_sessions(data_dir=self._data_dir)
        except Exception:
            sessions = []
        if not sessions:
            ol.add_option(Option(Text("(no sessions captured yet)", style="dim")))
            return
        for i, meta in enumerate(sessions):
            sid = meta.get("session_id") or "?"
            self._sids.append(sid)
            ol.add_option(Option(_render_session(meta, is_latest=(i == 0)), id=sid))
        # OptionList does not auto-highlight after `add_option()` (only
        # after init-time options), so without this Enter is a no-op
        # on first focus.
        ol.highlighted = 0


def _run_export(app, session_id: str, values: dict | None, data_dir) -> None:
    if not values:
        return
    from pathlib import Path

    from query.export import export_safe_share, export_trace

    fmt = values.get("format", "markdown")
    safe = bool(values.get("safe_share", True))
    excerpt = int(values.get("excerpt", 0))
    output = values.get("output") or ""
    try:
        if safe:
            export_safe_share(
                session_id,
                data_dir=data_dir,
                fmt=fmt,
                keep_excerpt=excerpt,
                output_path=Path(output) if output and fmt != "json" else None,
            )
        else:
            export_trace(
                session_id,
                data_dir=data_dir,
                output_path=Path(output) if output else None,
            )
    except Exception as exc:
        app.notify(f"export failed: {exc}", severity="error", title="aot")
        return
    label = output or "(stdout)"
    app.notify(f"exported → {label}", severity="information", title="aot", timeout=3)


def _render_session(meta: dict, *, is_latest: bool) -> Text:
    """Two-line Rich Text rendering: id line + metadata line."""
    sid = meta.get("session_id") or "?"
    engine = meta.get("engine") or "?"
    ts_end = short_time(meta.get("ts_end"))
    count = meta.get("tool_calls_total", 0)
    text = Text()
    text.append("● " if is_latest else "  ", style="bold cyan" if is_latest else "dim")
    text.append(sid[:8], style="bold")
    text.append("\n")
    text.append("  ")
    text.append(engine, style="dim")
    text.append(" · ", style="dim")
    text.append(f"{count} events", style="dim")
    text.append(" · ", style="dim")
    text.append(ts_end, style="dim")
    return text
