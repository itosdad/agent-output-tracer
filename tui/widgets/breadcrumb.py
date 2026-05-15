"""Title-bar breadcrumb: `aot · sessions · 781ff3fa · timeline`.

The screen stack drives the segments — each screen contributes one
segment via its `breadcrumb_segments()` hook on AOTScreen.
"""

from __future__ import annotations

from rich.text import Text
from textual.widget import Widget


class Breadcrumb(Widget):
    """Single-line breadcrumb at the top of every screen."""

    DEFAULT_CSS = """
    Breadcrumb {
        height: 1;
        padding: 0 1;
        background: $surface;
    }
    """

    def __init__(self, segments: list[str] | None = None) -> None:
        super().__init__()
        self._segments = list(segments) if segments else []

    def set_segments(self, segments: list[str]) -> None:
        self._segments = list(segments)
        self.refresh()

    def render(self) -> Text:
        text = Text()
        last = len(self._segments) - 1
        for i, seg in enumerate(self._segments):
            if i > 0:
                text.append("  ·  ", style="dim")
            text.append(seg, style="bold" if i == last else "dim")
        return text
