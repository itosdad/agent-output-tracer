"""Minimalist single-line status bar, bottom of the App.

Renders engine · follow indicator · event count · current time. Lives
at the App level, not per-screen — its content is updated via
`App.update_status()` whenever any of the underlying state changes.
"""

from __future__ import annotations

from datetime import datetime

from rich.text import Text
from textual.widget import Widget


class StatusBar(Widget):
    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        padding: 0 1;
        background: $surface-darken-1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.engine: str = "—"
        self.follow: bool = False
        self.event_count: int = 0
        self.session_short: str = ""

    def update_state(
        self,
        *,
        engine: str | None = None,
        follow: bool | None = None,
        event_count: int | None = None,
        session_short: str | None = None,
    ) -> None:
        if engine is not None:
            self.engine = engine
        if follow is not None:
            self.follow = follow
        if event_count is not None:
            self.event_count = event_count
        if session_short is not None:
            self.session_short = session_short
        self.refresh()

    def render(self) -> Text:
        accent = _accent(self.app)
        text = Text()
        text.append(self.engine, style=f"bold {accent}")
        if self.session_short:
            text.append("  ·  ", style="dim")
            text.append(self.session_short, style="bold")
        text.append("  ·  ", style="dim")
        text.append(f"events={self.event_count}")
        text.append("  ·  ", style="dim")
        text.append(
            "● live" if self.follow else "○ static",
            style="bold green" if self.follow else "dim",
        )
        text.append("  ·  ", style="dim")
        text.append(datetime.now().strftime("%H:%M"), style="dim")
        return text


def _accent(app) -> str:
    try:
        return app.current_theme.accent or "cyan"
    except Exception:
        return "cyan"
