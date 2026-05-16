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
from textual.containers import Vertical
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from core.session_io import list_sessions, load_metadata
from core.time_utils import short_time
from tui.router import AOTScreen


class SessionsScreen(AOTScreen):
    TITLE = "sessions"

    DEFAULT_CSS = """
    SessionsScreen #sessions-list {
        height: auto;
        max-height: 55%;
    }
    SessionsScreen #sessions-preview {
        padding: 1 1 0 1;
        background: $surface;
    }
    """

    BINDINGS = [
        Binding("enter", "open", "open", show=False),
        Binding("r", "refresh", "refresh", show=False),
        Binding("e", "export", "export", show=False),
        # Session-scoped sub-actions (Phase 3.C). Uppercase to avoid
        # collision with the lowercase letters Textual's OptionList
        # consumes for first-letter search.
        Binding("S", "open_stats", "stats", show=False),
        Binding("T", "open_timeline", "timeline", show=False),
        Binding("F", "open_find", "find", show=False),
    ]

    def __init__(self, data_dir=None) -> None:
        super().__init__()
        self._data_dir = data_dir
        # Parallel list of session ids in the order they were added,
        # so we can resolve `option.id` → session id quickly.
        self._sids: list[str] = []

    def breadcrumb_segments(self) -> list[str]:
        return ["agent-output-tracer", "sessions"]

    def footer_hints(self) -> list[tuple[str, str]]:
        return [
            ("↑↓", "select"),
            ("enter", "timeline"),
            ("S/T/F", "stats/tl/find"),
            ("e", "export"),
            ("esc", "back"),
        ]

    def help_entries(self) -> list[tuple[str, str]]:
        return [
            ("↑↓", "select session"),
            ("g / G", "first / last session"),
            ("enter", "open this session's timeline"),
            ("S", "open Stats for this session"),
            ("T", "open Timeline for this session (same as Enter)"),
            ("F", "open Find vocab picker scoped to this session"),
            ("e", "export this session (markdown / json / archive)"),
            ("r", "refresh sessions list from disk"),
        ]

    def compose_body(self):
        with Vertical():
            yield OptionList(id="sessions-list")
            yield Static(
                "(highlight a session to see details)",
                id="sessions-preview",
                markup=False,
            )

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

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        """Refresh the per-session preview as the cursor steps through.

        The preview reads `metadata.json` for the highlighted session
        — engine, span, event count, byte total, top anomaly counters
        — so the operator can decide whether to drill in without
        opening the full Timeline. Best-effort; missing fields just
        render as `?`."""
        sid = event.option.id or ""
        if not sid or not sid.startswith(("/", "")):
            pass
        try:
            from tui._accent import warning

            self.query_one("#sessions-preview", Static).update(
                _render_session_preview(sid, data_dir=self._data_dir, warn_col=warning(self.app))
            )
        except Exception:
            pass

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

    def action_open_stats(self) -> None:
        sid = self._highlighted_sid()
        if sid is None:
            return
        from tui.screens.stats import StatsScreen

        self.app.push_screen(StatsScreen(sid, data_dir=self._data_dir))

    def action_open_timeline(self) -> None:
        sid = self._highlighted_sid()
        if sid is None:
            return
        self._open_by_id(sid)

    def action_open_find(self) -> None:
        sid = self._highlighted_sid()
        if sid is None:
            return
        from tui.screens.find import FindScreen

        self.app.push_screen(FindScreen(session_id=sid, data_dir=self._data_dir))

    def _highlighted_sid(self) -> str | None:
        ol = self.query_one(OptionList)
        idx = ol.highlighted
        if idx is None or idx < 0 or idx >= len(self._sids):
            self.app.bell()
            return None
        return self._sids[idx]

    def _reload(self) -> None:
        ol = self.query_one(OptionList)
        ol.clear_options()
        self._sids = []
        try:
            sessions = list_sessions(data_dir=self._data_dir)
        except Exception:
            sessions = []
        if not sessions:
            empty = Text()
            empty.append("(no sessions captured yet)\n", style="dim")
            empty.append(
                "   Run a tool call in Claude Code or Codex with the\n",
                style="dim",
            )
            empty.append("   aot plugin active — events land in ", style="dim")
            empty.append("data_dir/sessions/", style="dim italic")
            empty.append(".\n   Try ", style="dim")
            empty.append("aot doctor", style="bold")
            empty.append(" if you expected sessions here.", style="dim")
            ol.add_option(Option(empty))
            return
        from tui._accent import accent

        col = accent(self.app)
        for i, meta in enumerate(sessions):
            sid = meta.get("session_id") or "?"
            self._sids.append(sid)
            ol.add_option(Option(_render_session(meta, is_latest=(i == 0), accent_col=col), id=sid))
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
        app.notify(f"export failed: {exc}", severity="error", title="agent-output-tracer")
        return
    label = output or "(stdout)"
    app.notify(
        f"exported → {label}", severity="information", title="agent-output-tracer", timeout=3
    )


def _render_session_preview(sid: str, *, data_dir, warn_col: str = "yellow") -> Text:
    """Per-session preview card shown below the list. Pulls everything
    from metadata.json — no extra event-file scan, so the highlight
    callback stays cheap (cursor stepping must not stutter)."""
    text = Text()
    if not sid:
        text.append("(no session highlighted)", style="dim italic")
        return text
    try:
        meta = load_metadata(sid, data_dir=data_dir) or {}
    except Exception:
        text.append(f"(failed to load metadata for {sid[:8]})", style="dim italic")
        return text

    engine = meta.get("engine") or "?"
    ts_start = short_time(meta.get("ts_start"))
    ts_end = short_time(meta.get("ts_end"))
    events_total = meta.get("events_total") or meta.get("tool_calls_total") or 0
    bytes_read = meta.get("total_bytes_read") or 0
    user_prompts = meta.get("user_prompts") or 0
    agent_responses = meta.get("agent_responses") or 0
    anomalies = meta.get("anomaly_counters") or {}
    tool_mix = meta.get("tool_mix") or {}
    cwd = meta.get("cwd") or ""

    text.append(f"{sid}\n", style="bold")
    text.append("  engine ", style="dim")
    text.append(engine)
    text.append("    span ", style="dim")
    text.append(f"{ts_start} → {ts_end}")
    text.append("    cwd ", style="dim")
    text.append(cwd if cwd else "?", style="dim italic")
    text.append("\n")

    text.append("  events ", style="dim")
    text.append(f"{events_total}")
    text.append("  ·  prompts ", style="dim")
    text.append(f"{user_prompts}u / {agent_responses}a")
    if bytes_read:
        text.append("  ·  read ", style="dim")
        text.append(_human_bytes(bytes_read))
    text.append("\n")

    if tool_mix:
        items = sorted(tool_mix.items(), key=lambda kv: -kv[1])[:5]
        text.append("  tools  ", style="dim")
        text.append(" · ".join(f"{n} {c}" for n, c in items))
        text.append("\n")

    if anomalies:
        items = sorted(anomalies.items(), key=lambda kv: -kv[1])[:5]
        text.append("  anom   ", style="dim")
        text.append(" · ".join(f"{n} {c}" for n, c in items), style=warn_col)
    return text


def _human_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit != "B" else f"{n} {unit}"
        n = int(n / 1024)
    return f"{n} TB"


def _render_session(meta: dict, *, is_latest: bool, accent_col: str = "cyan") -> Text:
    """Two-line Rich Text rendering: id line + metadata line."""
    sid = meta.get("session_id") or "?"
    engine = meta.get("engine") or "?"
    ts_end = short_time(meta.get("ts_end"))
    count = meta.get("tool_calls_total", 0)
    text = Text()
    text.append("● " if is_latest else "  ", style=f"bold {accent_col}" if is_latest else "dim")
    text.append(sid[:8], style="bold")
    text.append("\n")
    text.append("  ")
    text.append(engine, style="dim")
    text.append(" · ", style="dim")
    text.append(f"{count} events", style="dim")
    text.append(" · ", style="dim")
    text.append(ts_end, style="dim")
    return text
