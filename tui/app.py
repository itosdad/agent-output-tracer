"""Top-level Textual App for `aot tui`.

Phase 1 architecture: screen-stack with one screen visible at a time.
The App owns the chrome that's persistent across screens (StatusBar)
and the keyboard contract for `q` / `Esc` / `:` / `?` / `t`. Per-screen
chrome (Breadcrumb, FooterHints) is mounted by the AOTScreen base.

Entry contract: `run(session_spec)` is what `cli/main.py` calls. When
`session_spec` is None / "home", we land on Home. When it's a session
id (or "latest"), we land on the corresponding Timeline directly, with
Home + Sessions pre-loaded on the stack so Esc → Esc still brings the
user back to Home.

Backwards compat: tests can still import `AOTApp` and `_render_row`
from this module.
"""

from __future__ import annotations

import os
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding

from core.session_io import list_sessions, load_metadata
from core.session_resolver import resolve_session_id
from tui.screens.home import HomeScreen
from tui.screens.sessions import SessionsScreen
from tui.screens.timeline import TimelineScreen, _render_row  # noqa: F401 — re-export
from tui.themes import CLAUDE_THEME, CODEX_THEME, theme_for_engine
from tui.widgets.status_bar import StatusBar

_THEMES_DIR = Path(__file__).resolve().parent / "themes"


class AOTApp(App):
    """Main TUI application."""

    CSS_PATH = [
        str(_THEMES_DIR / "base.tcss"),
        str(_THEMES_DIR / "codex.tcss"),
    ]

    BINDINGS = [
        Binding("ctrl+c", "quit", "quit", show=False),
    ]

    def __init__(
        self,
        session_id: str | None = None,
        *,
        data_dir=None,
    ) -> None:
        super().__init__()
        self._initial_session = session_id
        self._data_dir = data_dir
        # Back-compat for the D-5 smoke test that asserts app.session_id.
        self.session_id = session_id or ""
        # Once the user has explicitly chosen a theme (via `t` or the
        # ThemeScreen), Timeline._sync_theme_to_engine must stop
        # silently overriding their choice on every reload. This flag
        # carries the user's intent across screen pushes.
        self.user_theme_override: bool = False

    def compose(self) -> ComposeResult:
        yield StatusBar()

    def on_mount(self) -> None:
        # Register both engine themes and pick the right initial one.
        self.register_theme(CODEX_THEME)
        self.register_theme(CLAUDE_THEME)
        self.theme = self._initial_theme_name()

        # Always start at Home so users learn navigation. If --session
        # was provided, drill into the appropriate Timeline on top of
        # Home + Sessions so back-stack is correct.
        self.push_screen(HomeScreen())
        if self._initial_session:
            self.push_screen(SessionsScreen(data_dir=self._data_dir))
            try:
                resolved = resolve_session_id(self._initial_session, data_dir=self._data_dir)
            except Exception:
                resolved = self._initial_session
            self.push_screen(TimelineScreen(resolved, data_dir=self._data_dir))

    def _initial_theme_name(self) -> str:
        """Pick a starting theme. Precedence (top wins):

        1. `--session <sid>` → THAT session's engine. Explicit user
           intent: "I want to look at this session, theme it for that."

        2. **Plugin-host env var** → the engine whose CLI is hosting
           `aot tui` *right now*. `CLAUDE_PLUGIN_DATA` is set by
           Claude Code, `CODEX_PLUGIN_DATA` by Codex. This is the
           strongest "where am I now" signal — stronger than the
           newest captured session, because that session might be a
           stale Codex run from earlier in the day while the operator
           has since switched engines.

        3. Newest captured session's engine. Useful when running `aot
           tui` from a bare shell outside either CLI — picks up
           whichever engine the user was last debugging.

        4. Codex as universal default (cyan plays well with the widest
           range of terminal palettes).
        """
        # 1) explicit session wins
        if self._initial_session:
            try:
                resolved = resolve_session_id(self._initial_session, data_dir=self._data_dir)
                meta = load_metadata(resolved, data_dir=self._data_dir) or {}
                if engine := meta.get("engine"):
                    return theme_for_engine(engine)
            except Exception:
                pass
        # 2) plugin-host env var — "which CLI am I inside right now"
        if os.environ.get("CLAUDE_PLUGIN_DATA") or os.environ.get("CLAUDE_PLUGIN_ROOT"):
            return theme_for_engine("claude-code")
        if os.environ.get("CODEX_PLUGIN_DATA") or os.environ.get("CODEX_PLUGIN_ROOT"):
            return theme_for_engine("codex")
        # 3) newest session
        try:
            sessions = list_sessions(data_dir=self._data_dir)
        except Exception:
            sessions = []
        if sessions:
            engine = sessions[0].get("engine") or ""
            if engine:
                return theme_for_engine(engine)
        # 4) universal default
        return theme_for_engine("")


# ------------- entry point -------------


def run(session_spec: str | None = "latest", *, data_dir=None) -> int:
    """Resolve the initial screen and start the textual app loop.

    `session_spec` accepts:
      - None or "home" / ""  → start at Home
      - "latest" or session id / prefix → drill into that Timeline
    """
    sid: str | None
    if session_spec in (None, "", "home"):
        sid = None
    else:
        sid = session_spec
    app = AOTApp(sid, data_dir=data_dir)
    app.run()
    return 0
