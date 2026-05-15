"""Export modal — `e` on Sessions or Timeline.

Multi-field form: format (markdown / json / archive), safe-share
(on/off), excerpt size (numeric), output path. Tuned for the common
case `e Enter` → markdown safe-share with empty body excerpts, output
to `~/aot-export-<sid8>.md`.

Phase 3 wires per-field defaults to `query.config_cmd` so they survive
process restarts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from tui.config import get_history, save_config

_FORMATS = ["markdown", "json", "archive"]


class ExportModal(ModalScreen[dict | None]):
    """Returns a dict on submit, or None on cancel.

    Result keys: format ∈ {markdown, json, archive}, safe_share: bool,
    excerpt: int, output: str.
    """

    DEFAULT_CSS = """
    ExportModal {
        align: center middle;
    }
    ExportModal > Vertical {
        width: 60;
        height: auto;
        padding: 1 2;
        background: $panel;
        border: round cyan;
    }
    ExportModal #title {
        height: 1;
        color: cyan;
        text-style: bold;
    }
    ExportModal #hint {
        height: 1;
        color: $text-muted;
        padding-top: 1;
    }
    """

    BINDINGS = [
        Binding("up", "prev", "prev field", show=False),
        Binding("down", "next", "next field", show=False),
        Binding("left", "dec", "←", show=False),
        Binding("right", "inc", "→", show=False),
        Binding("space", "toggle", "toggle", show=False),
        Binding("enter", "submit", "submit", show=False),
        Binding("escape", "cancel", "cancel", show=False),
    ]

    def __init__(self, *, session_short: str = "session") -> None:
        super().__init__()
        self._session_short = session_short
        # Pre-fill from saved sticky defaults; fall back to the
        # markdown/safe-share/no-excerpt baseline if the user has never
        # exported before.
        fmt = get_history("export_format", "markdown")
        if fmt not in _FORMATS:
            fmt = "markdown"
        suffix = {"markdown": "md", "json": "json", "archive": "tar.gz"}.get(fmt, "md")
        self._values: dict[str, Any] = {
            "format": fmt,
            "safe_share": bool(get_history("export_safe_share", True)),
            "excerpt": int(get_history("export_excerpt", 0) or 0),
            "output": str(Path.home() / f"aot-export-{session_short}.{suffix}"),
        }
        self._cursor = 0
        self._fields = ["format", "safe_share", "excerpt", "output"]

    def compose(self):
        with Vertical():
            yield Static(f"Export · {self._session_short}", id="title", markup=False)
            for f in self._fields:
                yield Static("", id=f"field-{f}", markup=False)
            yield Static(
                "↑↓ field · ←→ cycle / +- · space toggle · enter export · esc cancel",
                id="hint",
                markup=False,
            )

    def on_mount(self) -> None:
        self._refresh_all()

    def action_prev(self) -> None:
        self._cursor = (self._cursor - 1) % len(self._fields)
        self._refresh_all()

    def action_next(self) -> None:
        self._cursor = (self._cursor + 1) % len(self._fields)
        self._refresh_all()

    def action_inc(self) -> None:
        f = self._fields[self._cursor]
        if f == "format":
            cur = self._values["format"]
            i = (_FORMATS.index(cur) + 1) % len(_FORMATS)
            self._values["format"] = _FORMATS[i]
            self._refresh_field(f)
        elif f == "excerpt":
            self._values["excerpt"] = int(self._values["excerpt"]) + 100
            self._refresh_field(f)

    def action_dec(self) -> None:
        f = self._fields[self._cursor]
        if f == "format":
            cur = self._values["format"]
            i = (_FORMATS.index(cur) - 1) % len(_FORMATS)
            self._values["format"] = _FORMATS[i]
            self._refresh_field(f)
        elif f == "excerpt":
            self._values["excerpt"] = max(0, int(self._values["excerpt"]) - 100)
            self._refresh_field(f)

    def action_toggle(self) -> None:
        f = self._fields[self._cursor]
        if f == "safe_share":
            self._values["safe_share"] = not self._values["safe_share"]
            self._refresh_field(f)

    def action_submit(self) -> None:
        # Persist the format / safe-share / excerpt knobs so the next
        # `e` opens with the same shape. Output path is per-session and
        # not worth pinning across sessions.
        save_config(
            {
                "history": {
                    "export_format": self._values["format"],
                    "export_safe_share": bool(self._values["safe_share"]),
                    "export_excerpt": int(self._values["excerpt"]),
                }
            }
        )
        self.dismiss(dict(self._values))

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _refresh_all(self) -> None:
        for f in self._fields:
            self._refresh_field(f)

    def _refresh_field(self, name: str) -> None:
        i = self._fields.index(name)
        marker = "→" if i == self._cursor else " "
        try:
            self.query_one(f"#field-{name}", Static).update(f"{marker} {self._render_field(name)}")
        except Exception:
            pass

    def _render_field(self, name: str) -> str:
        v = self._values[name]
        if name == "format":
            cells = [f"[{o}]" if o == v else o for o in _FORMATS]
            return f"format        {'  '.join(cells)}"
        if name == "safe_share":
            return f"safe-share    [{'✓' if v else ' '}] {'on' if v else 'off'}"
        if name == "excerpt":
            return f"excerpt       {v} chars"
        if name == "output":
            return f"output        {v}"
        return f"{name}        {v}"
