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
        # Shimmer state for the live indicator: toggles `●` ↔ `○`
        # while `follow` is on, driven by a Textual interval timer
        # mounted in `on_mount`. Static when follow is off.
        self._shimmer_on: bool = True
        self._shimmer_timer = None

    def on_mount(self) -> None:
        # 700ms interval gives a calm pulse without feeling jittery.
        # The timer is paused when no follow target is active.
        self._shimmer_timer = self.set_interval(0.7, self._tick_shimmer, pause=True)

    def _tick_shimmer(self) -> None:
        self._shimmer_on = not self._shimmer_on
        self.refresh()

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
            # Drive the shimmer only when we're actually tailing.
            timer = self._shimmer_timer
            if timer is not None:
                if follow:
                    self._shimmer_on = True
                    timer.resume()
                else:
                    timer.pause()
        if event_count is not None:
            self.event_count = event_count
        if session_short is not None:
            self.session_short = session_short
        self.refresh()

    def render(self) -> Text:
        from tui._accent import accent

        col = accent(self.app)
        text = Text()
        text.append(self.engine, style=f"bold {col}")
        if self.session_short:
            text.append("  ·  ", style="dim")
            text.append(self.session_short, style="bold")
        text.append("  ·  ", style="dim")
        text.append(f"events={self.event_count}")
        text.append("  ·  ", style="dim")
        if self.follow:
            # Shimmer between `●` (filled, bright) and `○` (hollow,
            # dim) — eye catches the pulse without the bar being
            # visually noisy. Uses theme.success so Claude shows a
            # warmer leaf-green pulse and Codex shows the bright
            # terminal-green pulse.
            from tui._accent import success

            ok_col = success(self.app)
            glyph = "●" if self._shimmer_on else "○"
            style = f"bold {ok_col}" if self._shimmer_on else ok_col
            text.append(f"{glyph} live", style=style)
        else:
            text.append("○ static", style="dim")
        text.append("  ·  ", style="dim")
        text.append(datetime.now().strftime("%H:%M"), style="dim")
        return text
