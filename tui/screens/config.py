"""Config viewer — shows the sticky-defaults persisted under
`~/.config/aot/config.toml` (or `$XDG_CONFIG_HOME` / `$AOT_CONFIG_HOME`).

Read-only by design: the values are written by the screens themselves
when the user submits Find / Trace / Search / Export. `c` clears all
sticky defaults so the next time those screens open they fall back to
their hardcoded baselines.
"""

from __future__ import annotations

from rich.text import Text
from textual.binding import Binding
from textual.widgets import Static

from tui.config import _config_path, clear_history, load_config
from tui.router import AOTScreen


class ConfigScreen(AOTScreen):
    TITLE = "config"

    DEFAULT_CSS = """
    /* Config viewer is a small card. Centre + cap width. */
    ConfigScreen > .body {
        align: center middle;
    }
    ConfigScreen #config-body {
        width: 100%;
        max-width: 96;
        height: auto;
    }
    """

    BINDINGS = [
        Binding("r", "refresh", "refresh", show=False),
        Binding("c", "clear", "clear", show=False),
    ]

    def breadcrumb_segments(self) -> list[str]:
        return ["agent-output-tracer", "config"]

    def footer_hints(self) -> list[tuple[str, str]]:
        return [
            ("r", "refresh"),
            ("c", "clear history"),
            ("esc", "back"),
        ]

    def help_entries(self) -> list[tuple[str, str]]:
        return [
            ("r", "re-read config.toml from disk"),
            ("c", "clear all sticky defaults (Find / Trace / Search / Export)"),
            ("esc", "back to home"),
        ]

    def compose_body(self):
        yield Static("(loading)", id="config-body", expand=True, markup=False)

    def on_mount(self) -> None:
        self._refresh_view()

    def action_refresh(self) -> None:
        self._refresh_view()

    def action_clear(self) -> None:
        """Reset the `[history]` section. Other top-level sections (if
        we ever add any) are left untouched."""
        had_history = bool(load_config().get("history"))
        clear_history()
        if had_history:
            self.app.notify(
                "sticky defaults cleared",
                severity="information",
                title="agent-output-tracer",
                timeout=2,
            )
        else:
            self.app.notify(
                "nothing to clear", severity="information", title="agent-output-tracer", timeout=1
            )
        self._refresh_view()

    def _refresh_view(self) -> None:
        path = _config_path()
        cfg = load_config()
        text = Text()
        text.append("Config file\n", style="bold")
        text.append(f"  {path}\n", style="dim")
        text.append("  (exists)" if path.exists() else "  (not created yet)", style="dim")
        text.append("\n\n")

        history = cfg.get("history", {}) if isinstance(cfg, dict) else {}
        text.append("Sticky defaults  ", style="bold")
        text.append("(history)\n", style="dim")
        if not history:
            text.append("  none recorded yet — Find / Trace / Search / Export\n", style="dim")
            text.append("  inputs are persisted here once you submit them.\n", style="dim")
        else:
            for key in (
                "find_vocab",
                "trace_phrase",
                "search_regex",
                "export_format",
                "export_safe_share",
                "export_excerpt",
            ):
                if key in history:
                    text.append(f"  {key:<20}", style="dim")
                    text.append(f"{history[key]!r}\n")
            # Surface any unknown keys so a future addition is visible
            # without code changes here.
            known = {
                "find_vocab",
                "trace_phrase",
                "search_regex",
                "export_format",
                "export_safe_share",
                "export_excerpt",
            }
            for key, val in history.items():
                if key not in known:
                    text.append(f"  {key:<20}", style="dim")
                    text.append(f"{val!r}\n")

        text.append("\n")
        text.append("Theme\n", style="bold")
        text.append(f"  active: {self.app.theme}\n", style="dim")
        text.append("  (theme is intentionally NOT persisted — auto-detect from\n", style="dim")
        text.append("   the newest session's engine runs fresh on every launch)\n", style="dim")
        self.query_one("#config-body", Static).update(text)
