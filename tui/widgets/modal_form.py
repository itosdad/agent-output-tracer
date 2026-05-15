"""Modal form widget for multi-field input (export options etc).

Phase 1 skeleton — the actual command wiring lands in Phase 2 along
with Find / Trace / Export screens. The contract is fixed here so
those screens can build on it without changing the widget API.

Each field is one of:
  - text    free-form input
  - bool    `[✓] / [ ]` toggle (Space)
  - enum    `[current]  other  other` cycle (←/→)
  - number  numeric input with default visible

Navigation: ↑↓ between fields, Enter submits the whole form, Esc
cancels. Defaults sticky via a caller-supplied dict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

FieldKind = Literal["text", "bool", "enum", "number"]


@dataclass
class FormField:
    name: str
    label: str
    kind: FieldKind
    default: Any
    options: list[str] = field(default_factory=list)  # for enum


class ModalForm(ModalScreen[dict | None]):
    """A keyboard-only modal that collects multiple fields.

    Returns a dict {field_name: value} on submit, or None on cancel.
    """

    DEFAULT_CSS = """
    ModalForm {
        align: center middle;
    }
    ModalForm > Vertical {
        width: 60;
        height: auto;
        padding: 1 2;
        background: $panel;
        border: round $accent;
    }
    """

    BINDINGS = [
        Binding("up", "prev_field", "prev field"),
        Binding("down", "next_field", "next field"),
        Binding("left", "dec", "←"),
        Binding("right", "inc", "→"),
        Binding("space", "toggle", "toggle"),
        Binding("enter", "submit", "submit"),
        Binding("escape", "cancel", "cancel"),
    ]

    def __init__(self, title: str, fields: list[FormField]) -> None:
        super().__init__()
        self._title = title
        self._fields = fields
        self._values: dict[str, Any] = {f.name: f.default for f in fields}
        self._cursor = 0

    def compose(self):
        with Vertical():
            yield Static(self._title, id="form-title")
            for f in self._fields:
                yield Static(self._render_field(f), id=f"field-{f.name}")
            yield Static("", id="form-help")

    def on_mount(self) -> None:
        self._refresh()

    # --- nav ---

    def action_prev_field(self) -> None:
        self._cursor = (self._cursor - 1) % len(self._fields)
        self._refresh()

    def action_next_field(self) -> None:
        self._cursor = (self._cursor + 1) % len(self._fields)
        self._refresh()

    def action_inc(self) -> None:
        f = self._fields[self._cursor]
        if f.kind == "enum" and f.options:
            cur = self._values[f.name]
            i = (f.options.index(cur) + 1) % len(f.options) if cur in f.options else 0
            self._values[f.name] = f.options[i]
            self._refresh()

    def action_dec(self) -> None:
        f = self._fields[self._cursor]
        if f.kind == "enum" and f.options:
            cur = self._values[f.name]
            i = (f.options.index(cur) - 1) % len(f.options) if cur in f.options else 0
            self._values[f.name] = f.options[i]
            self._refresh()

    def action_toggle(self) -> None:
        f = self._fields[self._cursor]
        if f.kind == "bool":
            self._values[f.name] = not bool(self._values[f.name])
            self._refresh()

    def action_submit(self) -> None:
        self.dismiss(dict(self._values))

    def action_cancel(self) -> None:
        self.dismiss(None)

    # --- render ---

    def _refresh(self) -> None:
        for i, f in enumerate(self._fields):
            marker = "→" if i == self._cursor else " "
            try:
                self.query_one(f"#field-{f.name}", Static).update(
                    f"{marker} {self._render_field(f)}"
                )
            except Exception:
                pass

    def _render_field(self, f: FormField) -> str:
        val = self._values[f.name]
        if f.kind == "bool":
            return f"{f.label:14} [{'✓' if val else ' '}] {'on' if val else 'off'}"
        if f.kind == "enum":
            cells = []
            for opt in f.options:
                cells.append(f"[{opt}]" if opt == val else opt)
            return f"{f.label:14} {'  '.join(cells)}"
        return f"{f.label:14} {val}"
