"""Help overlay — `?` from any screen.

A ModalScreen that renders the current screen's keybinds in a
compact two-section layout (this-screen / global). Designed for
half-desktop layouts: width capped, single column, no decorations
that won't fit at 72 cols.

Dismiss on any key (`?`, `esc`, Enter, Space, etc.) so the operator
doesn't have to memorise which key closes it.
"""

from __future__ import annotations

from rich.text import Text
from textual import events
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

# Global keybinds (live on AOTScreen.BINDINGS, always available regardless
# of the foreground screen). One source of truth.
GLOBAL_HELP_ENTRIES: list[tuple[str, str]] = [
    ("esc", "back (or close this help)"),
    ("g / Home", "jump to top"),
    ("G / End", "jump to bottom"),
    (":", "command palette  (Phase 2.G)"),
    ("?", "this help"),
    ("t", "toggle theme    (Phase 3)"),
    ("q", "quit"),
]


class HelpOverlay(ModalScreen[None]):
    """`?` overlay — displays current-screen + global keybinds.

    Press any key to dismiss.
    """

    DEFAULT_CSS = """
    HelpOverlay {
        align: center middle;
    }
    HelpOverlay > Vertical {
        width: 56;
        height: auto;
        max-height: 80%;
        padding: 1 2;
        background: $panel;
        border: round cyan;
    }
    HelpOverlay #help-body {
        height: auto;
    }
    HelpOverlay #help-footer {
        height: 1;
        padding-top: 1;
        color: $text-muted;
        text-align: center;
    }
    """

    def __init__(
        self,
        *,
        screen_title: str,
        entries: list[tuple[str, str]],
    ) -> None:
        super().__init__()
        self._screen_title = screen_title
        self._entries = entries

    def compose(self):
        with Vertical():
            yield Static(self._render_body(), id="help-body", markup=False)
            yield Static("press any key to close", id="help-footer")

    def on_key(self, event: events.Key) -> None:
        # Any key closes the overlay — most intuitive for a help popup.
        event.stop()
        self.dismiss(None)

    def _render_body(self) -> Text:
        text = Text()
        text.append(f"help · {self._screen_title}\n\n", style="bold cyan")

        if self._entries:
            text.append("This screen\n", style="bold")
            for key, label in self._entries:
                _append_help_row(text, key, label)
            text.append("\n")

        text.append("Global\n", style="bold")
        for key, label in GLOBAL_HELP_ENTRIES:
            _append_help_row(text, key, label)
        return text


def _append_help_row(text: Text, key: str, label: str) -> None:
    # Two-column row: `<key:12>  <label>`. The 12-col reservation keeps
    # the second column aligned without being so wide that long-name
    # labels wrap on a 56-col modal.
    text.append(f"  {key:<12}", style="bold cyan")
    text.append(f"  {label}\n")
