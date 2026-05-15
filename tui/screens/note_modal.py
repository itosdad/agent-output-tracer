"""Note modal — single-line note attached to an event.

Triggered by `n` on Event Detail. The session_id and event_idx are
already known from the parent screen, so this modal only collects
the note body. Tag defaults to `observation`; richer tag selection
is a palette concern (`:note tag:question body…`).
"""

from __future__ import annotations

from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static


class NoteModal(ModalScreen[str | None]):
    """Single-line note input. Dismisses with the typed body on Enter,
    or None on Esc."""

    DEFAULT_CSS = """
    NoteModal {
        align: center middle;
    }
    NoteModal > Vertical {
        width: 60;
        height: auto;
        padding: 1 2;
        background: $panel;
        border: round cyan;
    }
    NoteModal #note-label {
        height: 1;
        color: cyan;
        text-style: bold;
    }
    NoteModal #note-hint {
        height: 1;
        color: $text-muted;
        padding-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "cancel", show=False),
    ]

    def __init__(self, *, prefill: str = "", label: str = "Add note") -> None:
        super().__init__()
        self._prefill = prefill
        self._label = label

    def compose(self):
        with Vertical():
            yield Static(self._label, id="note-label", markup=False)
            yield Input(value=self._prefill, placeholder="type your note…", id="note-input")
            yield Static("enter save · esc cancel", id="note-hint", markup=False)

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        body = (event.value or "").strip()
        self.dismiss(body or None)

    def action_cancel(self) -> None:
        self.dismiss(None)
