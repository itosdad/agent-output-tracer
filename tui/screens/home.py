"""Home screen — function picker.

Lists the top-level tracer functions (Sessions / Find / Trace /
Search / Stats / Doctor / Theme / Config). Enter on a row drills into
that function. This is the canonical entry point of the TUI.

In Phase 1 only Sessions is wired to a real screen; the rest are
visible but marked `(Phase 2)` so the navigation model is discoverable
from day one.
"""

from __future__ import annotations

from rich.text import Text
from textual.binding import Binding
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from tui.router import AOTScreen


def _menu_item(key: str, name: str, desc: str, available: bool = True) -> Option:
    text = Text()
    text.append(f"{name:<10}", style="bold")
    text.append(" ", style="")
    if available:
        text.append(desc, style="dim")
    else:
        text.append(desc + "   (Phase 2)", style="dim italic")
    return Option(text, id=key, disabled=not available)


class HomeScreen(AOTScreen):
    TITLE = "home"

    BINDINGS = [
        Binding("enter", "select", "open", show=False),
    ]

    def breadcrumb_segments(self) -> list[str]:
        return ["aot", "home"]

    def footer_hints(self) -> list[tuple[str, str]]:
        return [
            ("↑↓", "select"),
            ("enter", "open"),
            (":", "command"),
            ("?", "help"),
            ("q", "quit"),
        ]

    def compose_body(self):
        yield OptionList(
            _menu_item("sessions", "Sessions", "browse captured sessions"),
            _menu_item("find", "Find", "anomaly vocabulary detection", available=False),
            _menu_item("trace", "Trace", "causal trail for an output phrase", available=False),
            _menu_item("search", "Search", "full-text across sessions", available=False),
            _menu_item("stats", "Stats", "session metrics", available=False),
            _menu_item("doctor", "Doctor", "self-diagnostic", available=False),
            _menu_item("theme", "Theme", "engine: codex (Phase 3 adds Claude)", available=False),
            _menu_item("config", "Config", "CLI defaults", available=False),
            id="home-list",
        )

    def on_mount(self) -> None:
        self.query_one(OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._route(event.option.id or "")

    def action_select(self) -> None:
        ol = self.query_one(OptionList)
        if ol.highlighted is None:
            return
        opt = ol.get_option_at_index(ol.highlighted)
        self._route(opt.id or "")

    def _route(self, key: str) -> None:
        if key == "sessions":
            from tui.screens.sessions import SessionsScreen

            self.app.push_screen(SessionsScreen())
        else:
            # Phase 2 routes — beep until wired.
            self.app.bell()
