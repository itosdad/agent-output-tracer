"""Home screen — banner + function picker + preview pane.

Top: an OhMyZsh-style ASCII banner (slant figlet "AOT" + tagline +
version + quick-key hints) renders the project's formal name —
"agent-output-tracer" — so the operator never has to wonder what
they're looking at.

Middle: the function picker.

Bottom: a preview pane explaining what the highlighted function does,
what data it'll show, and one example finding. Both banner and
preview live on Home only; deeper screens own their own chrome.
"""

from __future__ import annotations

from rich.text import Text
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from tui._banner import render_banner
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


# Preview content per menu key. Three lines each — "what it does",
# "what you'll see", "example finding". Concrete examples > abstract
# taglines (the old "anomaly vocabulary detection" told you nothing).
_PREVIEWS: dict[str, tuple[str, str, str]] = {
    "sessions": (
        "Browse every captured session — newest first, with engine, "
        "event count, and end time per row.",
        "Each row: ● <session-id-8>  <engine> · N events · HH:MM.",
        "Enter drills into the Timeline; S/T/F open Stats/Timeline/Find scoped to the row.",
    ),
    "find": (
        "Run one of ten anomaly detectors against a session: "
        "hallucinations, unmentioned-reads, repeated-reads, "
        "glob-burst, large-read, silent-failure, and more.",
        "A match list — one row per finding, with event index and the offending token/path/tool.",
        "e.g. 'agent named /a/b.md but no Read ever fetched it (event 47, hallucinations)'.",
    ),
    "trace": (
        "Given a phrase the agent emitted, walk the event log backward "
        "to find the first event that introduced it.",
        "A causal trail card: first mention timestamp, source event, intermediate touches.",
        "e.g. trace 'hooks_wiring' → first appeared in Read of doctor.py at 19:42.",
    ),
    "search": (
        "Regex full-text search across every searchable field of every "
        "event in the latest session.",
        "Each row: event-type.field · event N · matched preview (120-char window).",
        "e.g. /JWT|token/ surfaces 5 matches across tool_response and agent_response.",
    ),
    "stats": (
        "One-screen metrics card for a session: tool mix, prompt counts, "
        "byte totals, anomaly counters, token usage.",
        "Bullet list with sub-headings (Tools, Files, Anomalies, Tokens).",
        "e.g. 'Read 18 · Bash 4 · Edit 2  ·  3 unique paths · 14 KB read'.",
    ),
    "doctor": (
        "Self-diagnostic: confirms the recorder pipeline is healthy.",
        "Checks: runtime, data_dir, recent_sessions, hooks_wiring — each ✓ / ⚠ / ✗.",
        "e.g. ⚠ data_dir exists but sessions/ has not been created (fix: trigger any tool call).",
    ),
    "theme": (
        "Switch between the two engine-flavoured themes: aot-codex (cyan) and aot-claude (salmon).",
        "A short picker; the active theme has a ● marker.",
        "`t` from any screen does the same cycle; this picker exposes both choices side by side.",
    ),
    "config": (
        "View the sticky defaults persisted to ~/.config/aot/config.toml: "
        "last Find vocab, Trace phrase, Search regex, Export knobs.",
        "Each saved key with its value, plus the config-file path.",
        "`c` clears all sticky defaults; `r` re-reads from disk.",
    ),
}


def _render_preview(key: str) -> Text:
    text = Text()
    entry = _PREVIEWS.get(key)
    if entry is None:
        text.append("(no preview)", style="dim italic")
        return text
    what, sees, example = entry
    text.append("What it does\n", style="bold")
    text.append(f"  {what}\n\n", style="dim")
    text.append("What you'll see\n", style="bold")
    text.append(f"  {sees}\n\n", style="dim")
    text.append("Example\n", style="bold")
    text.append(f"  {example}", style="dim italic")
    return text


class HomeScreen(AOTScreen):
    TITLE = "home"
    IS_ROOT = True  # Esc on Home is a no-op — see AOTScreen.action_safe_back.

    DEFAULT_CSS = """
    /* Home stacks banner + picker + preview. The Vertical wrap has
     * auto height (sum of children) so the body's `align: center
     * middle` actually centres it instead of being absorbed by a
     * 1fr-height Vertical filling the container. */
    HomeScreen > .body {
        align: center middle;
    }
    HomeScreen #home-wrap {
        width: 100%;
        max-width: 100;
        height: auto;
    }
    HomeScreen #home-banner {
        height: auto;
        padding: 1 1 0 1;
    }
    HomeScreen #home-list {
        height: auto;
        max-height: 40%;
        padding: 1 1 0 1;
    }
    HomeScreen #home-preview {
        padding: 1 1 0 1;
        background: $surface;
    }
    """

    BINDINGS = [
        Binding("enter", "select", "open", show=False),
    ]

    def breadcrumb_segments(self) -> list[str]:
        return ["agent-output-tracer", "home"]

    def footer_hints(self) -> list[tuple[str, str]]:
        return [
            ("↑↓", "select"),
            ("enter", "open"),
            (":", "cmd"),
            ("?", "help"),
            ("q", "quit"),
        ]

    def help_entries(self) -> list[tuple[str, str]]:
        return [
            ("↑↓", "select a function — preview updates below"),
            ("g / G", "first / last function"),
            ("enter", "open the highlighted function"),
            (":", "command palette (jump anywhere by name)"),
            ("t", "cycle theme  (codex ↔ claude)"),
        ]

    def compose_body(self):
        # Construct the Vertical explicitly rather than using
        # `with Vertical():` — the `with` form relies on Textual's
        # compose-time widget stack, which is only active inside
        # `compose()` itself, not in helper methods like
        # `compose_body()`. Using it here previously caused the
        # Vertical to mount as a SIBLING of `.body` (eating 15 rows
        # of dead space above the actual content). Explicit
        # construction makes the wrap a real child of `.body`.
        yield Vertical(
            # Banner content is rendered against the active theme on
            # mount (we need `self.app` for the accent colour, which
            # isn't available during compose).
            Static("", id="home-banner", markup=False),
            OptionList(
                _menu_item(
                    "sessions",
                    "Sessions",
                    "list of captured sessions, engine + event count per row",
                ),
                _menu_item(
                    "find", "Find", "ten anomaly detectors (hallucinations, unmentioned-reads, …)"
                ),
                _menu_item(
                    "trace", "Trace", "causal back-walk: where did this output phrase come from?"
                ),
                _menu_item("search", "Search", "regex full-text across every event field"),
                _menu_item(
                    "stats", "Stats", "one-screen session metrics (tools, anomalies, tokens)"
                ),
                _menu_item("doctor", "Doctor", "self-diagnostic: recorder pipeline health"),
                _menu_item("theme", "Theme", "switch engine accent (codex cyan / claude salmon)"),
                _menu_item("config", "Config", "view and clear sticky defaults"),
                id="home-list",
            ),
            Static(_render_preview("sessions"), id="home-preview", markup=False),
            id="home-wrap",
        )

    def on_mount(self) -> None:
        try:
            self.query_one("#home-banner", Static).update(render_banner(self.app))
        except Exception:
            pass
        self.query_one(OptionList).focus()

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        """Update the preview pane as the user steps through the menu."""
        try:
            self.query_one("#home-preview", Static).update(_render_preview(event.option.id or ""))
        except Exception:
            pass

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._route(event.option.id or "")

    def action_select(self) -> None:
        ol = self.query_one(OptionList)
        if ol.highlighted is None:
            return
        opt = ol.get_option_at_index(ol.highlighted)
        self._route(opt.id or "")

    def _route(self, key: str) -> None:
        # Forward the App's data_dir to every child screen — without
        # this, screens fall back to resolve_data_dir's filesystem
        # scan, which picks up unrelated session stores (e.g.
        # ~/.claude/plugins/data/...) when the App was launched against
        # an explicit data_dir (notably the screenshot harness in
        # tools/capture_screenshots.py).
        data_dir = getattr(self.app, "_data_dir", None)
        if key == "sessions":
            from tui.screens.sessions import SessionsScreen

            self.app.push_screen(SessionsScreen(data_dir=data_dir))
            return
        if key == "stats":
            from tui.screens.stats import StatsScreen

            self.app.push_screen(StatsScreen(data_dir=data_dir))
            return
        if key == "doctor":
            from tui.screens.doctor import DoctorScreen

            self.app.push_screen(DoctorScreen(data_dir=data_dir))
            return
        if key == "find":
            from tui.screens.find import FindScreen

            self.app.push_screen(FindScreen(data_dir=data_dir))
            return
        if key == "trace":
            from tui.screens.trace import TraceScreen

            self.app.push_screen(TraceScreen(data_dir=data_dir))
            return
        if key == "search":
            from tui.screens.search import SearchScreen

            self.app.push_screen(SearchScreen(data_dir=data_dir))
            return
        if key == "theme":
            from tui.screens.theme import ThemeScreen

            self.app.push_screen(ThemeScreen())
            return
        if key == "config":
            from tui.screens.config import ConfigScreen

            self.app.push_screen(ConfigScreen())
            return
        self.app.bell()
