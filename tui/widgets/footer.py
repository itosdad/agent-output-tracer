"""Per-screen footer hint row: `↑↓ select   enter open   :  command`.

Every screen exposes its own keybinds via `footer_hints()`. The
contents of this widget are refreshed when the active screen changes.
"""

from __future__ import annotations

from rich.text import Text
from textual.widget import Widget


class FooterHints(Widget):
    """Compact, always-visible footer that lists the current screen's
    keybinds. Reads `(key, label)` pairs and renders them inline."""

    DEFAULT_CSS = """
    FooterHints {
        height: 1;
        padding: 0 1;
        background: $surface;
    }
    """

    def __init__(self, hints: list[tuple[str, str]] | None = None) -> None:
        super().__init__()
        self._hints = list(hints) if hints else []

    def set_hints(self, hints: list[tuple[str, str]]) -> None:
        self._hints = list(hints)
        self.refresh()

    def render(self) -> Text:
        text = Text()
        for i, (key, label) in enumerate(self._hints):
            if i > 0:
                text.append("   ")
            text.append(key, style="bold cyan")
            text.append(" ")
            text.append(label, style="dim")
        return text
