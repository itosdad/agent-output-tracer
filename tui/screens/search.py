"""Search screen — regex full-text within one session.

Submit a regex, the screen collects matches across every searchable
field of every event in the latest session, drills into
SearchResultsScreen.

Cross-session search is deferred to Phase 2.G (`:search <regex>`
without a session-scope flag can fan out across the global index).
"""

from __future__ import annotations

from textual import events
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Input, Static

from tui.config import get_history, set_history
from tui.router import AOTScreen


class SearchScreen(AOTScreen):
    TITLE = "search"

    DEFAULT_CSS = """
    /* Same pattern as TraceScreen — centre the label + input. */
    SearchScreen > .body {
        align: center middle;
    }
    SearchScreen #search-wrap {
        width: 100%;
        max-width: 80;
        height: auto;
    }
    """

    BINDINGS = [
        Binding("enter", "submit", "search", show=False),
    ]

    _history: list[str] = []

    def __init__(self, session_id: str = "latest", *, data_dir=None) -> None:
        self.session_id = session_id
        self._data_dir = data_dir
        self._history_idx: int | None = None
        super().__init__()

    def breadcrumb_segments(self) -> list[str]:
        return ["agent-output-tracer", "search"]

    def footer_hints(self) -> list[tuple[str, str]]:
        return [
            ("enter", "search"),
            ("↑↓", "recall"),
            ("esc", "back"),
            (":", "cmd"),
            ("?", "help"),
        ]

    def help_entries(self) -> list[tuple[str, str]]:
        return [
            ("enter", "run regex search on the latest session"),
            ("↑ / ↓", "recall previous queries"),
            ("esc", "back to home"),
        ]

    def compose_body(self):
        yield Vertical(
            Static(
                "Regex to search across event fields (latest session):",
                id="search-label",
                markup=False,
            ),
            Input(placeholder=r"e.g.  JWT|token", id="search-input"),
            id="search-wrap",
        )

    def on_mount(self) -> None:
        inp = self.query_one(Input)
        if last := get_history("search_regex"):
            inp.value = last
        inp.focus()

    def action_submit(self) -> None:
        self._submit(self.query_one(Input).value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit(event.value)

    def _submit(self, pattern: str) -> None:
        pattern = pattern.strip()
        if not pattern:
            self.app.bell()
            return
        if not SearchScreen._history or SearchScreen._history[-1] != pattern:
            SearchScreen._history.append(pattern)
            SearchScreen._history = SearchScreen._history[-50:]
        set_history("search_regex", pattern)
        from tui.screens.search_results import SearchResultsScreen

        self.app.push_screen(
            SearchResultsScreen(
                pattern=pattern,
                session_id=self.session_id,
                data_dir=self._data_dir,
            )
        )

    def on_key(self, event: events.Key) -> None:
        if event.key not in ("up", "down"):
            return
        inp = self.query_one(Input)
        if self.focused is not inp:
            return
        if not SearchScreen._history:
            return
        if event.key == "up":
            self._history_idx = (
                len(SearchScreen._history) - 1
                if self._history_idx is None
                else max(0, self._history_idx - 1)
            )
            inp.value = SearchScreen._history[self._history_idx]
        else:
            if self._history_idx is None:
                return
            if self._history_idx >= len(SearchScreen._history) - 1:
                self._history_idx = None
                inp.value = ""
            else:
                self._history_idx += 1
                inp.value = SearchScreen._history[self._history_idx]
        event.stop()
