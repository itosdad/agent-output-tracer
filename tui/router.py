"""Base class for all screens in the aot TUI.

Each screen contributes:
  - `screen_title` for the breadcrumb (e.g. "timeline", "event 1")
  - `breadcrumb_segments()` for the full path (parents up to "aot")
  - `footer_hints()` for the bottom hint row
  - `compose_body()` yields the screen's main widgets

The chrome (Breadcrumb / FooterHints) is mounted in compose() by the
base class; subclasses only worry about the body.

Universal keybinds live here:
  esc   pop screen (drill back one level)
  q     quit
  ?     help overlay (Phase 2)
  :     command palette (Phase 2)
  t     toggle theme (Phase 3)
"""

from __future__ import annotations

from textual.binding import Binding
from textual.containers import Container
from textual.screen import Screen

from tui.widgets.breadcrumb import Breadcrumb
from tui.widgets.footer import FooterHints


class AOTScreen(Screen):
    """Base class for every aot TUI screen.

    Universal contract:
      - drill in: push another AOTScreen onto the app stack
      - drill out: `escape` pops back (handled by base BINDINGS)
      - quit: `q` exits

    Subclasses override `compose_body()`, `breadcrumb_segments()`,
    `footer_hints()`. Everything else is provided by this base.
    """

    BINDINGS = [
        Binding("escape", "app.pop_screen", "back", show=False),
        Binding("q", "app.quit", "quit", show=False),
        Binding("question_mark", "noop_help", "help", show=False),
        Binding("colon", "noop_palette", "palette", show=False),
        Binding("t", "noop_theme", "theme", show=False),
    ]

    TITLE: str = "screen"

    # ---- subclass hooks ----

    def compose_body(self):
        """Yield widgets that fill the body. Subclasses override."""
        return ()

    def breadcrumb_segments(self) -> list[str]:
        """Return ['aot', ..., self.TITLE] for the breadcrumb bar."""
        return ["aot", self.TITLE]

    def footer_hints(self) -> list[tuple[str, str]]:
        """Per-screen keybind hints — `[(key, label), ...]`."""
        return [("esc", "back"), ("q", "quit"), ("?", "help"), (":", "command")]

    # ---- compose ----

    def compose(self):
        yield Breadcrumb(self.breadcrumb_segments())
        yield Container(*self.compose_body(), classes="body")
        yield FooterHints(self.footer_hints())

    # ---- placeholders for phase 2 / 3 actions ----

    def action_noop_help(self) -> None:
        """Bound to `?`. Phase 2 will mount a help overlay; for now,
        we no-op so the binding is visible in `footer_hints()` even
        before the feature lands."""
        self.app.bell()

    def action_noop_palette(self) -> None:
        self.app.bell()

    def action_noop_theme(self) -> None:
        self.app.bell()
