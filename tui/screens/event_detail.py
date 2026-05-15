"""Event Detail screen — full event payload for the row the user
selected on Timeline.

Renders:
  metadata block      ts / type / tool / paths / sha256
  tool_input          pretty-printed JSON when applicable
  tool_response       truncated body, `r` toggles raw, `s` shows
                      the safe-share sanitised version
  related events      same correlation_id, sorted chronologically;
                      Enter on a related row pushes a fresh Detail
                      screen for that event

Esc returns to Timeline.
"""

from __future__ import annotations

import json
from typing import Any

from rich.text import Text
from textual.binding import Binding
from textual.widgets import Static

from tui.router import AOTScreen


class EventDetailScreen(AOTScreen):
    BINDINGS = [
        Binding("r", "toggle_raw", "raw", show=False),
        Binding("s", "toggle_sanitised", "sanitised", show=False),
        Binding("y", "yank", "yank", show=False),
        Binding("n", "noop_note", "note", show=False),
        Binding("enter", "drill_related", "drill", show=False),
        Binding("j,down", "next_event", "next", show=False),
        Binding("k,up", "prev_event", "prev", show=False),
    ]

    TITLE = "event"

    def __init__(
        self,
        *,
        event: dict,
        event_index: int,
        session_id: str,
        all_events: list[dict],
        data_dir=None,
    ) -> None:
        self._event = event
        self._idx = event_index
        self._session_id = session_id
        self._all_events = all_events
        self._data_dir = data_dir
        self._show_raw: bool = False
        self._show_sanitised: bool = False
        super().__init__()

    def breadcrumb_segments(self) -> list[str]:
        return [
            "aot",
            self._session_id[:8],
            "timeline",
            f"event {self._idx} · {self._event.get('event_type') or '?'}",
        ]

    def footer_hints(self) -> list[tuple[str, str]]:
        # Keep this row narrow — half-desktop layouts can be as tight
        # as 72 cols, and a 1-row footer that wraps looks broken.
        # Less-essential hints (`y` yank, `n` note) are still bound,
        # just not advertised here. g/G scroll the static-detail body.
        return [
            ("↑↓/jk", "step"),
            ("g/G", "top/bot"),
            ("r", "raw"),
            ("s", "safe"),
            ("enter", "rel"),
            ("esc", "back"),
        ]

    def help_entries(self) -> list[tuple[str, str]]:
        # The richer set — what `?` advertises but the cramped footer
        # cannot show.
        return [
            ("↑↓ / j k", "previous / next event"),
            ("g / G", "first / last event"),
            ("r", "toggle raw event JSON"),
            ("s", "toggle safe-share preview"),
            ("y", "yank event JSON to clipboard"),
            ("n", "add a note  (Phase 2.F)"),
            ("enter", "jump to related event (same correlation_id)"),
        ]

    def compose_body(self):
        # markup=False keeps Rich Text styles in `update()` exact;
        # shrink=False + expand keeps wrapping on for narrow terminals.
        yield Static("(loading)", id="event-detail", expand=True, markup=False)

    def on_mount(self) -> None:
        self._refresh_view()
        # Static can't take focus; defer key handling to the screen
        # itself (which is fine — j/k/r/s/y are screen-level bindings).

    def action_toggle_raw(self) -> None:
        self._show_raw = not self._show_raw
        if self._show_raw:
            self._show_sanitised = False
        self._refresh_view()

    def action_toggle_sanitised(self) -> None:
        self._show_sanitised = not self._show_sanitised
        if self._show_sanitised:
            self._show_raw = False
        self._refresh_view()

    def action_yank(self) -> None:
        # Phase 1: best-effort clipboard via pyperclip if available.
        try:
            import pyperclip

            pyperclip.copy(json.dumps(self._event, ensure_ascii=False, indent=2))
            self.app.bell()
        except Exception:
            self.app.bell()

    def action_noop_note(self) -> None:
        from tui.screens.note_modal import NoteModal

        self.app.push_screen(NoteModal(), self._on_note_submitted)

    def _on_note_submitted(self, body) -> None:
        if not body:
            return
        from query.note import note_add

        try:
            note_add(
                self._session_id,
                body,
                event_idx=self._idx,
                data_dir=self._data_dir,
            )
        except Exception as exc:
            self.app.notify(
                f"note save failed: {exc}",
                severity="error",
                title="aot",
            )
            return
        # Toast confirmation — silent disk writes leave the user
        # wondering whether anything happened.
        self.app.notify(
            f"note saved on event {self._idx}",
            severity="information",
            title="aot",
            timeout=2,
        )

    def action_next_event(self) -> None:
        if self._idx + 1 >= len(self._all_events):
            return
        self._idx += 1
        self._event = self._all_events[self._idx]
        self._show_raw = False
        self._show_sanitised = False
        self._refresh_chrome()
        self._refresh_view()

    def action_prev_event(self) -> None:
        if self._idx <= 0:
            return
        self._idx -= 1
        self._event = self._all_events[self._idx]
        self._show_raw = False
        self._show_sanitised = False
        self._refresh_chrome()
        self._refresh_view()

    def action_drill_related(self) -> None:
        # Phase 1: jump to the first related event (same correlation_id),
        # skipping self. Phase 2 will surface a picker if multiple.
        cid = self._event.get("correlation_id")
        if not cid:
            self.app.bell()
            return
        for i, ev in enumerate(self._all_events):
            if i == self._idx:
                continue
            if ev.get("correlation_id") == cid:
                self._idx = i
                self._event = ev
                self._show_raw = False
                self._show_sanitised = False
                self._refresh_chrome()
                self._refresh_view()
                return
        self.app.bell()

    # ---- chrome ----

    def _refresh_chrome(self) -> None:
        try:
            from tui.widgets.breadcrumb import Breadcrumb

            self.query_one(Breadcrumb).set_segments(self.breadcrumb_segments())
        except Exception:
            pass

    # ---- view refresh (NOT _render — that's a Textual Widget hook
    # that returns a visual; overriding it returns None and crashes
    # the compositor with 'NoneType has no render_strips') ----

    def _refresh_view(self) -> None:
        text = Text()
        if self._show_raw:
            text.append("─ raw event JSON ─\n", style="bold")
            text.append(json.dumps(self._event, ensure_ascii=False, indent=2))
        elif self._show_sanitised:
            text.append("─ safe-share preview ─\n", style="bold")
            text.append(_sanitise_one(self._event))
        else:
            self._append_metadata(text)
            self._append_input(text)
            self._append_response(text)
            self._append_related(text)
        self.query_one("#event-detail", Static).update(text)

    def _append_metadata(self, text: Text) -> None:
        for k in ("ts", "event_type", "tool_name", "session_id", "correlation_id"):
            v = self._event.get(k)
            if v is None:
                continue
            text.append(f"{k:<18}", style="dim")
            text.append(f"{v}\n")
        paths = self._event.get("paths") or []
        if paths:
            text.append(f"{'paths':<18}", style="dim")
            text.append(f"{', '.join(str(p) for p in paths)}\n")
        sha = self._event.get("response_sha256")
        if sha:
            text.append(f"{'response_sha256':<18}", style="dim")
            text.append(f"{sha}\n")
        size = self._event.get("response_size_bytes") or self._event.get("result_bytes")
        if size:
            text.append(f"{'response_bytes':<18}", style="dim")
            text.append(f"{size}\n")

    def _append_input(self, text: Text) -> None:
        ti = self._event.get("tool_input")
        if ti:
            text.append("\n─ tool_input ─\n", style="bold")
            text.append(_pretty(ti))

    def _append_response(self, text: Text) -> None:
        for key, header in (
            ("user_prompt_text", "user_prompt"),
            ("agent_response_text", "agent_response"),
            ("command", "command"),
            ("tool_response", "tool_response"),
        ):
            v = self._event.get(key)
            if not v:
                continue
            text.append(f"\n─ {header} ─\n", style="bold")
            if isinstance(v, (dict, list)):
                text.append(_pretty(v))
            else:
                s = str(v)
                if len(s) > 2000:
                    text.append(s[:2000])
                    text.append(f"\n… ({len(s) - 2000} more chars; press r for raw)\n", style="dim")
                else:
                    text.append(s)

    def _append_related(self, text: Text) -> None:
        cid = self._event.get("correlation_id")
        if not cid:
            return
        related = [
            (i, ev)
            for i, ev in enumerate(self._all_events)
            if ev.get("correlation_id") == cid and i != self._idx
        ]
        if not related:
            return
        text.append("\n─ related (same correlation_id) ─\n", style="bold")
        for i, ev in related:
            text.append(f"  ↳ event {i}", style="dim")
            text.append(f"  {ev.get('event_type')}  {ev.get('tool_name') or ''}\n")


def _pretty(v: Any) -> str:
    try:
        return json.dumps(v, ensure_ascii=False, indent=2)
    except Exception:
        return str(v)


def _sanitise_one(ev: dict) -> str:
    """Run the safe-share sanitiser over a single event for the
    sanitised-preview view. Falls back to repr on failure."""
    try:
        from core.sanitiser import sanitise_session

        cleaned, _meta = sanitise_session([ev], None, keep_excerpt=200)
        return _pretty(cleaned[0]) if cleaned else _pretty(ev)
    except Exception:
        return _pretty(ev)
