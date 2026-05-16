"""Doctor screen — self-diagnostic report.

Wraps `query.doctor.doctor()` (same backend the CLI uses) and renders
each check as a vertical card with status glyph + detail + optional
`fix:` hint.

  ✓ runtime
      Python 3.14.5 on Darwin arm64

  ⚠ data_dir
      resolved to /…/agent-output-tracer-... (2.8 MB)

  ✗ hooks_wiring
      no hooks.json found …
      fix: install the plugin: /plugin marketplace add …
"""

from __future__ import annotations

from rich.text import Text
from textual.binding import Binding
from textual.widgets import Static

from query.doctor import doctor as _doctor
from tui.router import AOTScreen

_STATUS_GLYPH = {"ok": "✓", "warn": "⚠", "fail": "✗"}
_STATUS_STYLE = {"ok": "green", "warn": "yellow", "fail": "red"}


class DoctorScreen(AOTScreen):
    TITLE = "doctor"

    BINDINGS = [
        Binding("r", "refresh", "refresh", show=False),
    ]

    def __init__(self, *, data_dir=None) -> None:
        self._data_dir = data_dir
        self._result: dict = {}
        super().__init__()

    def breadcrumb_segments(self) -> list[str]:
        return ["agent-output-tracer", "doctor"]

    def footer_hints(self) -> list[tuple[str, str]]:
        return [
            ("g/G", "top/bot"),
            ("r", "refresh"),
            ("esc", "back"),
            (":", "cmd"),
            ("?", "help"),
        ]

    def help_entries(self) -> list[tuple[str, str]]:
        return [
            ("r", "re-run all diagnostic checks"),
            ("g / G", "scroll to top / bottom"),
        ]

    def compose_body(self):
        yield Static("(running checks…)", id="doctor-body", expand=True, markup=False)

    def on_mount(self) -> None:
        self._refresh_view()

    def action_refresh(self) -> None:
        self._refresh_view()

    def yank_payload(self) -> str:
        try:
            content = self.query_one("#doctor-body", Static).content
            return content.plain if hasattr(content, "plain") else str(content)
        except Exception:
            return ""

    def _refresh_view(self) -> None:
        try:
            result = _doctor(data_dir=self._data_dir, fmt="json")
        except Exception as exc:
            self.query_one("#doctor-body", Static).update(
                Text(f"doctor crashed: {exc}", style="red")
            )
            return
        self._result = result
        self.query_one("#doctor-body", Static).update(_render_doctor(result))


def _render_doctor(result: dict) -> Text:
    text = Text()
    headline = "all checks pass" if result.get("ok") else "some checks need attention"
    text.append(
        headline + "\n\n",
        style=("bold green" if result.get("ok") else "bold yellow"),
    )
    for c in result.get("checks") or []:
        status = c.get("status", "?")
        glyph = _STATUS_GLYPH.get(status, "·")
        style = _STATUS_STYLE.get(status, "")
        text.append(f"{glyph} ", style=style + " bold")
        text.append(f"{c.get('name', '?')}\n", style="bold")
        detail = c.get("detail") or ""
        for line in str(detail).splitlines():
            text.append(f"    {line}\n", style="dim")
        fix = c.get("fix")
        if fix:
            text.append("    fix: ", style="dim italic")
            text.append(f"{fix}\n")
        text.append("\n")
    return text
