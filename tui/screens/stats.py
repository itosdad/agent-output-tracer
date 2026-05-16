"""Stats screen — read-only session metrics.

Wraps `query.stats.stats()` and renders the result as a compact card.
By default opens on the latest session; switching sessions is a
Phase 2.G command-palette concern (`:stats --session <id>`) — for now
the user can also reach this screen from a specific Sessions row via
the upcoming `S` binding in Phase 2.E.
"""

from __future__ import annotations

from rich.text import Text
from textual.binding import Binding
from textual.widgets import Static

from core.session_resolver import resolve_session_id
from core.time_utils import short_time
from query.stats import stats as _stats
from tui.router import AOTScreen


class StatsScreen(AOTScreen):
    TITLE = "stats"

    DEFAULT_CSS = """
    /* Stats is a single short card. Centre it vertically so it
     * doesn't float at the top with 20+ rows of dead space below.
     * max-width caps the card on wide terminals — readability over
     * full-width stretching. */
    StatsScreen > .body {
        align: center middle;
    }
    StatsScreen #stats-body {
        width: 100%;
        max-width: 96;
        height: auto;
    }
    """

    BINDINGS = [
        Binding("r", "refresh", "refresh", show=False),
    ]

    def __init__(self, session_id: str = "latest", *, data_dir=None) -> None:
        self.session_id = session_id
        self._data_dir = data_dir
        self._result: dict = {}
        super().__init__()

    def breadcrumb_segments(self) -> list[str]:
        sid_short = self.session_id[:8] if self.session_id != "latest" else "latest"
        return ["agent-output-tracer", "stats", sid_short]

    def footer_hints(self) -> list[tuple[str, str]]:
        return [
            ("g/G", "top/bot"),
            ("r", "refresh"),
            ("esc", "back"),
            (":", "cmd"),
            ("?", "help"),
        ]

    def help_entries(self) -> list[tuple[str, str]]:
        return [
            ("r", "refresh metrics from disk"),
            ("g / G", "scroll to top / bottom"),
        ]

    def compose_body(self):
        yield Static("(loading)", id="stats-body", expand=True, markup=False)

    def on_mount(self) -> None:
        self._refresh_view()

    def action_refresh(self) -> None:
        self._refresh_view()

    def yank_payload(self) -> str:
        """Yank the rendered stats body — useful for pasting a session
        summary into an issue tracker."""
        try:
            content = self.query_one("#stats-body", Static).content
            return content.plain if hasattr(content, "plain") else str(content)
        except Exception:
            return ""

    def _refresh_view(self) -> None:
        try:
            resolved = resolve_session_id(self.session_id, data_dir=self._data_dir)
        except Exception:
            resolved = self.session_id
        try:
            result = _stats(resolved, data_dir=self._data_dir)
        except Exception as exc:
            from tui._accent import error

            self.query_one("#stats-body", Static).update(
                Text(f"could not compute stats: {exc}", style=error(self.app))
            )
            return
        self._result = result
        if resolved and resolved != self.session_id:
            self.session_id = resolved
            try:
                from tui.widgets.breadcrumb import Breadcrumb

                self.query_one(Breadcrumb).set_segments(self.breadcrumb_segments())
            except Exception:
                pass
        self.query_one("#stats-body", Static).update(_render_stats(result))


def _render_stats(r: dict) -> Text:
    text = Text()
    sid = r.get("session_id") or "?"
    engine = r.get("engine") or "?"
    engine_v = r.get("engine_version")
    text.append("Session  ", style="dim")
    text.append(f"{sid}\n")
    text.append("Engine   ", style="dim")
    text.append(engine)
    if engine_v:
        text.append(f"  {engine_v}", style="dim")
    text.append("\n")

    ts_start = short_time(r.get("ts_start"))
    ts_end = short_time(r.get("ts_end"))
    text.append("Period   ", style="dim")
    text.append(f"{ts_start} → {ts_end}\n\n")

    text.append("Events   ", style="dim")
    text.append(f"{r.get('events_total', 0)}\n")
    text.append("Prompts  ", style="dim")
    text.append(f"{r.get('user_prompts', 0)} user · {r.get('agent_responses', 0)} agent\n")

    tool_mix = r.get("tool_mix") or {}
    if tool_mix:
        items = sorted(tool_mix.items(), key=lambda kv: -kv[1])
        text.append("Tools    ", style="dim")
        text.append(" · ".join(f"{name} {count}" for name, count in items[:6]))
        if len(items) > 6:
            text.append("  · …", style="dim")
        text.append("\n")

    text.append("\n")
    text.append("Files    ", style="dim")
    text.append(f"{r.get('unique_paths_read', 0)} unique")
    nb = r.get("total_bytes_read", 0)
    if nb:
        text.append(f" · {_human_bytes(nb)} read", style="dim")
    text.append("\n")

    anomalies = r.get("anomaly_counters") or {}
    if anomalies:
        text.append("\n")
        text.append("Anomalies\n", style="bold")
        for name, count in sorted(anomalies.items(), key=lambda kv: -kv[1]):
            text.append(f"  {name:<22}", style="dim")
            text.append(f"{count}\n")

    tokens = r.get("tokens_total") or {}
    if tokens:
        text.append("\n")
        text.append("Tokens\n", style="bold")
        for name, count in sorted(tokens.items()):
            text.append(f"  {name:<22}", style="dim")
            text.append(f"{count}\n")
    return text


def _human_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} {unit}"
        n = int(n / 1024)
    return f"{n} TB"
