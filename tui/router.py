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
        Binding("escape", "safe_back", "back", show=False),
        Binding("q", "app.quit", "quit", show=False),
        Binding("question_mark", "noop_help", "help", show=False),
        Binding("colon", "noop_palette", "palette", show=False),
        Binding("t", "noop_theme", "theme", show=False),
        # vim-style + Home/End jump to top / bottom of the focused
        # list or scrollable container. Universal across every screen.
        Binding("g,home", "jump_top", "top", show=False),
        Binding("G,end", "jump_bottom", "bottom", show=False),
    ]

    TITLE: str = "screen"

    # Subclasses representing the root of the screen stack (= Home)
    # set this to True so Esc becomes a no-op there. Popping the root
    # exposes Textual's default empty Screen and the app appears
    # frozen to the user.
    IS_ROOT: bool = False

    # ---- subclass hooks for the help overlay ----

    def help_entries(self) -> list[tuple[str, str]]:
        """Return `[(key, label), ...]` for the help overlay's
        "This screen" section. Defaults to `footer_hints()` — screens
        with extra non-advertised bindings can override to expose them.
        """
        return list(self.footer_hints())

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

    # ---- universal navigation ----

    def action_safe_back(self) -> None:
        """Esc handler — pop unless we're already at the root.

        Without this guard, pressing Esc on Home would call
        `app.pop_screen()` and expose Textual's default empty Screen
        below it, leaving the app visually frozen and unresponsive.
        """
        if self.IS_ROOT:
            self.app.bell()
            return
        self.app.pop_screen()

    def action_jump_top(self) -> None:
        """`g` / `Home` — jump to the first row of the focused list,
        or scroll the focused container to the top."""
        self._jump(to_bottom=False)

    def action_jump_bottom(self) -> None:
        """`G` / `End` — jump to the last row of the focused list, or
        scroll the focused container to the bottom."""
        self._jump(to_bottom=True)

    def _jump(self, *, to_bottom: bool) -> None:
        # Lazy imports so the router stays cheap to import.
        from textual.containers import ScrollableContainer
        from textual.widgets import DataTable, OptionList

        target = self.focused
        if target is None:
            self.app.bell()
            return
        if isinstance(target, OptionList):
            if target.option_count == 0:
                self.app.bell()
                return
            target.highlighted = (target.option_count - 1) if to_bottom else 0
            return
        if isinstance(target, DataTable):
            if target.row_count == 0:
                self.app.bell()
                return
            target.move_cursor(row=(target.row_count - 1) if to_bottom else 0)
            return
        if isinstance(target, ScrollableContainer):
            if to_bottom:
                target.scroll_end(animate=False)
            else:
                target.scroll_home(animate=False)
            return
        # Fall back to scroll_home/end on whatever the focused widget is.
        method = "scroll_end" if to_bottom else "scroll_home"
        fn = getattr(target, method, None)
        if callable(fn):
            try:
                fn(animate=False)
                return
            except TypeError:
                fn()
                return
        self.app.bell()

    # ---- universal actions ----

    def action_noop_help(self) -> None:
        """`?` — open the help overlay for this screen."""
        from tui.screens.help import HelpOverlay

        self.app.push_screen(
            HelpOverlay(
                screen_title=self.TITLE,
                entries=self.help_entries(),
            )
        )

    # ---- placeholders for phase 2 / 3 actions still to wire ----

    def action_noop_palette(self) -> None:
        """`:` — open the command palette."""
        from tui.screens.palette import CommandPalette

        data_dir = getattr(self.app, "_data_dir", None)
        self.app.push_screen(CommandPalette(data_dir=data_dir))

    def action_noop_theme(self) -> None:
        self.app.bell()
