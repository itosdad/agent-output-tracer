"""Trace screen — phrase → causal trail.

Submit a phrase, the screen calls `query.trace.trace()` against the
latest session (or `--session` later via the command palette), and
drills into TraceResultsScreen.

Layout puts the input as the focal element of the screen, not as a
bottom popup — for Trace, typing the phrase IS the primary task.
History recall on ↑/↓ via a small instance-local ring buffer; the
buffer is in-memory only in Phase 2.D (config-persisted recall lands
in Phase 3).
"""

from __future__ import annotations

from textual import events
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Input, Static

from tui.config import get_history, set_history
from tui.router import AOTScreen


class TraceScreen(AOTScreen):
    TITLE = "trace"

    DEFAULT_CSS = """
    /* Single label + input — centre vertically. The wrap has auto
     * height (sum of label + input) so the parent's `align: center
     * middle` actually positions it in the visual middle. */
    TraceScreen > .body {
        align: center middle;
    }
    TraceScreen #trace-wrap {
        width: 100%;
        max-width: 80;
        height: auto;
    }
    """

    BINDINGS = [
        Binding("enter", "submit", "trace", show=False),
    ]

    # Process-local recall buffer shared across pushes of this screen.
    _history: list[str] = []

    def __init__(self, session_id: str = "latest", *, data_dir=None) -> None:
        self.session_id = session_id
        self._data_dir = data_dir
        self._history_idx: int | None = None
        super().__init__()

    def breadcrumb_segments(self) -> list[str]:
        return ["agent-output-tracer", "trace"]

    def footer_hints(self) -> list[tuple[str, str]]:
        return [
            ("enter", "trace"),
            ("↑↓", "recall"),
            ("esc", "back"),
            (":", "cmd"),
            ("?", "help"),
        ]

    def help_entries(self) -> list[tuple[str, str]]:
        return [
            ("enter", "run trace on latest session"),
            ("↑ / ↓", "recall previously-traced phrases"),
            ("esc", "back to home"),
        ]

    def compose_body(self):
        yield Vertical(
            Static(
                "Phrase to trace back to its source:",
                id="trace-label",
                markup=False,
            ),
            Input(placeholder="e.g. hooks_wiring", id="trace-input"),
            id="trace-wrap",
        )

    def on_mount(self) -> None:
        inp = self.query_one(Input)
        # Pre-fill with the last phrase the user typed, if any. The
        # input is selected so a single keystroke replaces it — sticky
        # default behaves like "remembered", not "stuck".
        if last := get_history("trace_phrase"):
            inp.value = last
        inp.focus()

    def action_submit(self) -> None:
        self._submit(self.query_one(Input).value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # `Input` consumes Enter and emits Submitted before the screen
        # binding fires; this handler is the actual trigger.
        self._submit(event.value)

    def _submit(self, phrase: str) -> None:
        phrase = phrase.strip()
        if not phrase:
            self.app.bell()
            return
        # Push onto the shared recall ring.
        if not TraceScreen._history or TraceScreen._history[-1] != phrase:
            TraceScreen._history.append(phrase)
            TraceScreen._history = TraceScreen._history[-50:]
        set_history("trace_phrase", phrase)
        from tui.screens.trace_results import TraceResultsScreen

        self.app.push_screen(
            TraceResultsScreen(
                phrase=phrase,
                session_id=self.session_id,
                data_dir=self._data_dir,
            )
        )

    def on_key(self, event: events.Key) -> None:
        # ↑/↓ on the input recall previously-traced phrases.
        if event.key not in ("up", "down"):
            return
        inp = self.query_one(Input)
        if self.focused is not inp:
            return
        if not TraceScreen._history:
            return
        if event.key == "up":
            self._history_idx = (
                len(TraceScreen._history) - 1
                if self._history_idx is None
                else max(0, self._history_idx - 1)
            )
            inp.value = TraceScreen._history[self._history_idx]
        else:
            if self._history_idx is None:
                return
            if self._history_idx >= len(TraceScreen._history) - 1:
                self._history_idx = None
                inp.value = ""
            else:
                self._history_idx += 1
                inp.value = TraceScreen._history[self._history_idx]
        event.stop()
