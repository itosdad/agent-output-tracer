"""Bottom-inline single-line input. Lazygit / vim ex-line style.

The prompt sits as a single row at the bottom of the active screen,
takes focus when activated, and dismisses on Enter (submit) or Esc
(cancel). It does not steal the screen — the underlying content
remains visible above. History recall on `↑` / `↓` is wired here so
that every consumer screen gets it for free.

Phase 1 skeleton — wiring to specific commands lives in Phase 2.
"""

from __future__ import annotations

from collections.abc import Callable

from textual import events, on
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Input, Static


class InlinePrompt(Horizontal):
    """`<label> <input>` row, hidden by default, shown via `.open()`."""

    DEFAULT_CSS = """
    InlinePrompt {
        height: 1;
        padding: 0 1;
        background: $surface-lighten-1;
        display: none;
    }
    InlinePrompt.-visible {
        display: block;
    }
    InlinePrompt > Static.prompt-label {
        width: auto;
        padding-right: 1;
        color: $accent;
    }
    InlinePrompt > Input {
        border: none;
        background: $surface-lighten-1;
        padding: 0;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "cancel", show=False),
        Binding("up", "history_prev", "↑ recall", show=False),
        Binding("down", "history_next", "↓ recall", show=False),
    ]

    def __init__(self, label: str = "> ", history: list[str] | None = None) -> None:
        super().__init__()
        self._label = label
        self._history: list[str] = list(history) if history else []
        self._history_idx: int | None = None
        self._on_submit: Callable[[str], None] | None = None
        self._on_cancel: Callable[[], None] | None = None

    def compose(self):
        yield Static(self._label, classes="prompt-label")
        yield Input(id="inline-prompt-input")

    def open(
        self,
        *,
        on_submit: Callable[[str], None],
        on_cancel: Callable[[], None] | None = None,
        prefill: str = "",
        label: str | None = None,
    ) -> None:
        """Show the prompt, focus it, and register callbacks."""
        self._on_submit = on_submit
        self._on_cancel = on_cancel
        if label is not None:
            self._label = label
            self.query_one(Static).update(label)
        inp = self.query_one(Input)
        inp.value = prefill
        self._history_idx = None
        self.add_class("-visible")
        inp.focus()

    def close(self) -> None:
        self.remove_class("-visible")
        self._on_submit = None
        self._on_cancel = None

    def action_cancel(self) -> None:
        if self._on_cancel:
            self._on_cancel()
        self.close()

    def action_history_prev(self) -> None:
        if not self._history:
            return
        if self._history_idx is None:
            self._history_idx = len(self._history) - 1
        else:
            self._history_idx = max(0, self._history_idx - 1)
        self.query_one(Input).value = self._history[self._history_idx]

    def action_history_next(self) -> None:
        if not self._history or self._history_idx is None:
            return
        if self._history_idx >= len(self._history) - 1:
            self._history_idx = None
            self.query_one(Input).value = ""
        else:
            self._history_idx += 1
            self.query_one(Input).value = self._history[self._history_idx]

    @on(Input.Submitted)
    def _on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value
        if value and (not self._history or self._history[-1] != value):
            self._history.append(value)
        if self._on_submit:
            self._on_submit(value)
        self.close()

    def on_key(self, event: events.Key) -> None:
        # Re-route up/down so they don't go to the underlying screen.
        if event.key in ("up", "down") and self.has_class("-visible"):
            event.stop()
