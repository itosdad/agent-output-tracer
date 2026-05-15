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

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding

from core.session_resolver import resolve_session_id
from tui.screens.home import HomeScreen
from tui.screens.sessions import SessionsScreen
from tui.screens.timeline import TimelineScreen, _render_row  # noqa: F401 — re-export
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

    def compose(self) -> ComposeResult:
        yield StatusBar()

    def on_mount(self) -> None:
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
