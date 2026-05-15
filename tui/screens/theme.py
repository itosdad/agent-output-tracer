"""Theme picker — explicit alternative to the `t` keyboard cycle.

Lists the two registered engine themes; Enter applies the highlighted
one and pops back. The keyboard `t` cycle on every screen still works
in parallel for power users.
"""

from __future__ import annotations

from rich.text import Text
from textual.binding import Binding
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from tui.router import AOTScreen
from tui.themes import CLAUDE_THEME, CODEX_THEME


class ThemeScreen(AOTScreen):
    TITLE = "theme"

    BINDINGS = [
        Binding("enter", "apply", "apply", show=False),
    ]

    def breadcrumb_segments(self) -> list[str]:
        return ["aot", "theme"]

    def footer_hints(self) -> list[tuple[str, str]]:
        return [
            ("↑↓", "select"),
            ("enter", "apply"),
            ("esc", "back"),
        ]

    def help_entries(self) -> list[tuple[str, str]]:
        return [
            ("↑↓", "select theme"),
            ("enter", "apply this theme"),
            ("t", "cycle to the other theme (universal binding)"),
            ("esc", "back without changing"),
        ]

    def compose_body(self):
        yield OptionList(id="theme-list")

    def on_mount(self) -> None:
        ol = self.query_one(OptionList)
        current = self.app.theme
        for theme, label, desc in (
            (CODEX_THEME, "Codex", "cyan accent · Codex CLI flavored"),
            (CLAUDE_THEME, "Claude", "salmon accent · Claude Code β-flavored"),
        ):
            marker = "●" if theme.name == current else "○"
            text = Text()
            text.append(f"{marker} ", style=theme.primary or "")
            text.append(f"{label:<8}", style="bold")
            text.append(f"  {desc}", style="dim")
            ol.add_option(Option(text, id=theme.name))
        # Pre-highlight the active theme so Enter is a confirm-current,
        # arrow-then-Enter is a switch.
        for i in range(ol.option_count):
            if ol.get_option_at_index(i).id == current:
                ol.highlighted = i
                break
        else:
            ol.highlighted = 0
        ol.focus()

    def action_apply(self) -> None:
        ol = self.query_one(OptionList)
        idx = ol.highlighted
        if idx is None:
            return
        try:
            opt = ol.get_option_at_index(idx)
        except Exception:
            return
        self._apply(opt.id or "")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._apply(event.option.id or "")

    def _apply(self, name: str) -> None:
        if not name:
            return
        try:
            self.app.theme = name
            self.app.notify(f"theme: {name}", severity="information", title="aot", timeout=1)
        except Exception:
            self.app.bell()
            return
        self.app.pop_screen()
