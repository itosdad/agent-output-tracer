"""Command palette — `:` from any screen.

A single-line input modal that parses CLI-like syntax and routes to
the appropriate screen. Lets power users skip the menu hierarchy:

  :sessions                          → Sessions list
  :stats                             → latest session stats
  :stats <sid>                       → specific session stats
  :doctor                            → diagnostics
  :find <vocab>                      → find on latest with defaults
  :find <vocab> <n>                  → find with threshold n
  :trace <phrase>                    → trace phrase on latest
  :search <regex>                    → regex search on latest
  :home                              → reset to home
  :help                              → help overlay
  :quit                              → quit

History is recalled with ↑/↓ from a process-local ring buffer.
"""

from __future__ import annotations

import shlex
from collections.abc import Callable

from textual import events
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from query.find import VOCAB

_PALETTE_HISTORY: list[str] = []


class CommandPalette(ModalScreen[None]):
    """Single-line `:` palette. Dismisses self after dispatching."""

    DEFAULT_CSS = """
    CommandPalette {
        align: center middle;
    }
    CommandPalette > Vertical {
        width: 64;
        height: auto;
        padding: 1 2;
        background: $panel;
        border: round $accent;
    }
    CommandPalette #palette-label {
        height: 1;
        color: $accent;
        text-style: bold;
    }
    CommandPalette #palette-hint {
        height: 1;
        color: $text-muted;
        padding-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "cancel", show=False),
    ]

    def __init__(self, *, data_dir=None) -> None:
        super().__init__()
        self._data_dir = data_dir
        self._history_idx: int | None = None

    def compose(self):
        with Vertical():
            yield Static(": command palette", id="palette-label", markup=False)
            yield Input(
                placeholder="e.g.  find hallucinations · trace hooks_wiring · stats",
                id="palette-input",
            )
            yield Static(
                "enter run · esc cancel · ↑↓ recall",
                id="palette-hint",
                markup=False,
            )

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        line = (event.value or "").strip()
        if not line:
            self.dismiss(None)
            return
        if not _PALETTE_HISTORY or _PALETTE_HISTORY[-1] != line:
            _PALETTE_HISTORY.append(line)
            del _PALETTE_HISTORY[:-100]
        # Resolve into a callable that pushes the right screen, then
        # dismiss before invoking it so the palette isn't on the stack.
        action = _route(line, data_dir=self._data_dir, app=self.app)
        self.dismiss(None)
        if action is not None:
            action()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_key(self, event: events.Key) -> None:
        if event.key not in ("up", "down"):
            return
        inp = self.query_one(Input)
        if self.focused is not inp:
            return
        if not _PALETTE_HISTORY:
            return
        if event.key == "up":
            self._history_idx = (
                len(_PALETTE_HISTORY) - 1
                if self._history_idx is None
                else max(0, self._history_idx - 1)
            )
            inp.value = _PALETTE_HISTORY[self._history_idx]
        else:
            if self._history_idx is None:
                return
            if self._history_idx >= len(_PALETTE_HISTORY) - 1:
                self._history_idx = None
                inp.value = ""
            else:
                self._history_idx += 1
                inp.value = _PALETTE_HISTORY[self._history_idx]
        event.stop()


def _route(line: str, *, data_dir, app) -> Callable[[], None] | None:
    """Parse `line` and return a callable that effects the command.

    Returning a callable (rather than acting directly) lets the palette
    dismiss itself first so the new screen pushes onto the underlying
    stack instead of on top of the modal.
    """
    try:
        tokens = shlex.split(line)
    except ValueError:
        return lambda: app.bell()
    if not tokens:
        return None
    cmd = tokens[0].lower()
    args = tokens[1:]

    if cmd in ("quit", "exit", "q"):
        return app.exit
    if cmd in ("home",):
        return lambda: _go_home(app)
    if cmd == "help":
        return lambda: _push_help(app)
    if cmd == "sessions":
        return lambda: _push("sessions", app, data_dir=data_dir)
    if cmd == "doctor":
        return lambda: _push("doctor", app, data_dir=data_dir)
    if cmd == "stats":
        sid = args[0] if args else "latest"
        return lambda: _push("stats", app, data_dir=data_dir, session_id=sid)
    if cmd == "find":
        if not args:
            return lambda: _push("find", app, data_dir=data_dir)
        vocab = args[0]
        if vocab not in VOCAB:
            return lambda: app.bell()
        threshold = None
        session_id = "latest"
        for a in args[1:]:
            if a.startswith("--session="):
                session_id = a.split("=", 1)[1]
            elif a == "--session":
                continue
            else:
                try:
                    threshold = int(a)
                except ValueError:
                    pass
        return lambda: _push(
            "find_results",
            app,
            data_dir=data_dir,
            vocab=vocab,
            threshold=threshold,
            session_id=session_id,
        )
    if cmd == "trace":
        if not args:
            return lambda: _push("trace", app, data_dir=data_dir)
        phrase = " ".join(args)
        return lambda: _push("trace_results", app, data_dir=data_dir, phrase=phrase)
    if cmd == "search":
        if not args:
            return lambda: _push("search", app, data_dir=data_dir)
        pattern = " ".join(args)
        return lambda: _push(
            "search_results",
            app,
            data_dir=data_dir,
            pattern=pattern,
        )
    # Unknown command
    return lambda: app.bell()


def _push(target: str, app, *, data_dir, **kwargs) -> None:
    """Push the named screen with kwargs. Imports lazily to keep the
    palette module's startup cost low."""
    if target == "sessions":
        from tui.screens.sessions import SessionsScreen

        app.push_screen(SessionsScreen(data_dir=data_dir))
    elif target == "stats":
        from tui.screens.stats import StatsScreen

        app.push_screen(
            StatsScreen(session_id=kwargs.get("session_id", "latest"), data_dir=data_dir)
        )
    elif target == "doctor":
        from tui.screens.doctor import DoctorScreen

        app.push_screen(DoctorScreen(data_dir=data_dir))
    elif target == "find":
        from tui.screens.find import FindScreen

        app.push_screen(FindScreen(data_dir=data_dir))
    elif target == "find_results":
        from tui.screens.find_results import FindResultsScreen

        app.push_screen(
            FindResultsScreen(
                vocab=kwargs["vocab"],
                session_id=kwargs.get("session_id", "latest"),
                threshold=kwargs.get("threshold"),
                data_dir=data_dir,
            )
        )
    elif target == "trace":
        from tui.screens.trace import TraceScreen

        app.push_screen(TraceScreen(data_dir=data_dir))
    elif target == "trace_results":
        from tui.screens.trace_results import TraceResultsScreen

        app.push_screen(
            TraceResultsScreen(
                phrase=kwargs["phrase"],
                session_id=kwargs.get("session_id", "latest"),
                data_dir=data_dir,
            )
        )
    elif target == "search":
        from tui.screens.search import SearchScreen

        app.push_screen(SearchScreen(data_dir=data_dir))
    elif target == "search_results":
        from tui.screens.search_results import SearchResultsScreen

        app.push_screen(
            SearchResultsScreen(
                pattern=kwargs["pattern"],
                session_id=kwargs.get("session_id", "latest"),
                data_dir=data_dir,
            )
        )


def _push_help(app) -> None:
    from tui.screens.help import HelpOverlay

    entries = []
    try:
        entries = list(app.screen.help_entries())
    except Exception:
        entries = []
    title = getattr(app.screen, "TITLE", "screen")
    app.push_screen(HelpOverlay(screen_title=str(title), entries=entries))


def _go_home(app) -> None:
    """Pop until only Home remains."""
    while len(app.screen_stack) > 2:
        try:
            app.pop_screen()
        except Exception:
            break
