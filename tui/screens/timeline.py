"""Timeline screen — events for one session, in chronological order.

Rendered as a vertical OptionList (not a multi-column DataTable) so
the screen stays readable at half-desktop widths (~72 cols) without
horizontal scrolling. Each event renders as a 2-line "card":

    ›  19:42:06  user_prompt
       describe phase D — the plan and the layout we want

    ⏵  19:42:08  pre_tool · Read
       DESIGN.md (47 KB)

Semantic prefixes (Codex theme, source-cited in themes/codex.tcss):
  ›  user_prompt
  ⏵  pre_tool
  ✓  post_tool
  •  agent_response
  ─  session_start / session_end / pre_compact / post_compact

Body previews are truncated to a single line per card. Enter drills
into the Event Detail screen for the full payload. `o` toggles live
follow.
"""

from __future__ import annotations

import threading

from rich.text import Text
from textual.binding import Binding
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from core.follower import follow_events
from core.session_io import list_sessions, load_events
from core.time_utils import short_time, truncate
from tui.router import AOTScreen

_PREFIX = {
    "user_prompt": "›",
    "pre_tool": "⏵",
    "post_tool": "✓",
    "agent_response": "•",
    "session_start": "─",
    "session_end": "─",
    "pre_compact": "─",
    "post_compact": "─",
}


class TimelineScreen(AOTScreen):
    TITLE = "timeline"

    BINDINGS = [
        Binding("enter", "open", "detail", show=False),
        Binding("o", "toggle_follow", "follow", show=False),
        Binding("r", "refresh", "refresh", show=False),
        Binding("slash", "search", "search", show=False),
    ]

    def __init__(self, session_id: str, *, data_dir=None) -> None:
        self.session_id = session_id
        self._data_dir = data_dir
        self._search_term: str = ""
        self._events: list[dict] = []
        # Indices of events visible after filtering, parallel to the
        # OptionList. Lets us resolve `option.id` (a stringified index
        # into _events) back to the underlying event.
        self._follow: bool = False
        # Follower thread + stop flag, owned by the screen instance.
        self._follower_thread: threading.Thread | None = None
        self._follower_stop = threading.Event()
        super().__init__()

    def breadcrumb_segments(self) -> list[str]:
        return ["aot", self.session_id[:8], "timeline"]

    def footer_hints(self) -> list[tuple[str, str]]:
        return [
            ("↑↓", "step"),
            ("g/G", "top/bot"),
            ("enter", "detail"),
            ("o", "follow" if not self._follow else "stop"),
            ("esc", "back"),
        ]

    def help_entries(self) -> list[tuple[str, str]]:
        return [
            ("↑↓", "step through events"),
            ("g / G", "first / last event"),
            ("enter", "open event detail"),
            ("o", "toggle live follow"),
            ("r", "refresh from disk"),
            ("/", "search in this timeline  (Phase 2.E)"),
        ]

    def compose_body(self):
        yield OptionList(id="timeline-list")

    def on_mount(self) -> None:
        self._reload()
        self.query_one(OptionList).focus()

    def action_refresh(self) -> None:
        self._reload()

    def action_open(self) -> None:
        self._open_highlighted()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Primary drill-in path: OptionList Enter → OptionSelected."""
        self._open_by_id(event.option.id or "")

    def _open_highlighted(self) -> None:
        ol = self.query_one(OptionList)
        idx = ol.highlighted
        if idx is None:
            return
        # OptionList highlight indexes the visible (post-filter) list;
        # the option's id is the absolute index into self._events.
        try:
            opt = ol.get_option_at_index(idx)
        except Exception:
            return
        self._open_by_id(opt.id or "")

    def _open_by_id(self, opt_id: str) -> None:
        try:
            idx = int(opt_id)
        except (TypeError, ValueError):
            return
        if idx < 0 or idx >= len(self._events):
            return
        event = self._events[idx]
        from tui.screens.event_detail import EventDetailScreen

        self.app.push_screen(
            EventDetailScreen(
                event=event,
                event_index=idx,
                session_id=self.session_id,
                all_events=self._events,
                data_dir=self._data_dir,
            )
        )

    def action_toggle_follow(self) -> None:
        self._follow = not self._follow
        self._reload()
        ol = self.query_one(OptionList)
        if self._follow:
            if ol.option_count > 0:
                ol.highlighted = ol.option_count - 1
            self._start_follower()
        else:
            self._stop_follower()
        try:
            from tui.widgets.footer import FooterHints

            self.query_one(FooterHints).set_hints(self.footer_hints())
        except Exception:
            pass
        self._update_status_bar()

    def on_unmount(self) -> None:
        # Drilling away or quitting must shut the polling thread down,
        # otherwise it keeps tailing events.jsonl in the background.
        self._stop_follower()

    def _start_follower(self) -> None:
        if self._follower_thread and self._follower_thread.is_alive():
            return
        self._follower_stop.clear()
        sid = self.session_id
        data_dir = self._data_dir

        def runner() -> None:
            try:
                for _ in follow_events(
                    sid,
                    data_dir=data_dir,
                    from_start=False,
                    poll_interval=0.5,
                    stop_predicate=self._follower_stop.is_set,
                ):
                    self.app.call_from_thread(self._reload)
            except Exception:
                # Best-effort — never raise into the TUI loop.
                pass

        self._follower_thread = threading.Thread(target=runner, daemon=True)
        self._follower_thread.start()

    def _stop_follower(self) -> None:
        self._follower_stop.set()
        self._follower_thread = None

    def action_search(self) -> None:
        # Phase 2 will mount an InlinePrompt; for now beep.
        self.app.bell()

    def _sync_theme_to_engine(self) -> None:
        """Match the active Textual theme to the session's `engine`
        field. Best-effort — we don't want a stale metadata read to
        propagate as a UI exception."""
        try:
            from core.session_io import load_metadata
            from tui.themes import theme_for_engine

            meta = load_metadata(self.session_id, data_dir=self._data_dir) or {}
            wanted = theme_for_engine(meta.get("engine"))
            if self.app.theme != wanted:
                self.app.theme = wanted
        except Exception:
            pass

    def _resolve_session(self) -> str:
        """Resolve 'latest' / prefix → concrete id."""
        if self.session_id != "latest":
            return self.session_id
        try:
            sessions = list_sessions(data_dir=self._data_dir)
        except Exception:
            return self.session_id
        if sessions:
            sid = sessions[0].get("session_id")
            if sid:
                self.session_id = sid
                try:
                    from tui.widgets.breadcrumb import Breadcrumb

                    self.query_one(Breadcrumb).set_segments(self.breadcrumb_segments())
                except Exception:
                    pass
        return self.session_id

    def _reload(self) -> None:
        self._resolve_session()
        # Auto-switch the theme to match this session's engine if it
        # differs from the currently active one. Operator can still
        # override with `t`.
        self._sync_theme_to_engine()
        ol = self.query_one(OptionList)
        ol.clear_options()
        try:
            events = load_events(self.session_id, data_dir=self._data_dir)
        except Exception:
            events = []
        self._events = events
        if not events:
            empty = Text()
            empty.append("(no events recorded for this session)\n", style="dim")
            empty.append("   The session's metadata.json exists but events.jsonl\n", style="dim")
            empty.append(
                "   is empty — likely a recording aborted before any\n   tool call fired. Try ",
                style="dim",
            )
            empty.append("aot doctor", style="bold")
            empty.append(" to diagnose hooks wiring.", style="dim")
            ol.add_option(Option(empty))
            return
        term = self._search_term.lower()
        added = 0
        for i, ev in enumerate(events):
            rendered = _render_event(ev)
            if term and term not in rendered.plain.lower():
                continue
            ol.add_option(Option(rendered, id=str(i)))
            added += 1
        # OptionList does not auto-highlight after `add_option()` (only
        # after init-time options), so without this Enter is a no-op
        # on first focus.
        if added > 0:
            ol.highlighted = 0
        self._update_status_bar()

    def _update_status_bar(self) -> None:
        """Push session id / engine / event count / follow state to the
        App-level StatusBar so the chrome reflects what this screen is
        actually showing. Best-effort — failure to find the StatusBar
        must not crash a timeline reload."""
        try:
            from core.session_io import load_metadata
            from tui.widgets.status_bar import StatusBar

            meta = load_metadata(self.session_id, data_dir=self._data_dir) or {}
            bar = self.app.query_one(StatusBar)
            bar.update_state(
                engine=meta.get("engine") or "—",
                follow=self._follow,
                event_count=len(self._events),
                session_short=self.session_id[:8] if self.session_id else "",
            )
        except Exception:
            pass


def _render_event(ev: dict) -> Text:
    """Two-line Rich Text rendering of one event card.

    Line 1: <prefix>  <ts>  <type>[  <tool · path>]
    Line 2:    <body single-line preview>
    """
    ts = short_time(ev.get("ts"))
    et = ev.get("event_type") or "?"
    prefix = _PREFIX.get(et, " ")
    tool = ev.get("tool_name") or ""
    paths = ev.get("paths") or []
    # locus = the tool · first path (basename-friendly — full path
    # would force horizontal scroll on half-desktop layouts)
    locus = ""
    if tool and paths:
        locus = f"{tool} · {_short_path(paths[0])}"
    elif tool:
        locus = tool
    elif paths:
        locus = _short_path(paths[0])

    text = Text()
    text.append(f"{prefix}  ", style=_prefix_style(et))
    text.append(ts, style="dim")
    text.append("  ")
    text.append(et)
    if locus:
        text.append("  ·  ", style="dim")
        text.append(locus, style="dim")

    body = _first_body(ev)
    if body:
        # one-line preview; the option renderer hard-wraps at the
        # widget width if the line is still wider than the viewport.
        preview = body.split("\n", 1)[0].strip()
        if preview:
            text.append("\n   ")
            text.append(preview)
    return text


def _short_path(p: str) -> str:
    """Render a path as just its basename if it's an absolute path.

    Half-desktop layouts can't afford 60-char absolute paths in the
    list. The Event Detail screen shows the full path.
    """
    if not isinstance(p, str) or not p:
        return ""
    if p.startswith(("/", "~")):
        # Keep the last two path components when meaningful, else just
        # the basename.
        parts = [part for part in p.split("/") if part]
        if len(parts) >= 2:
            return ".../" + "/".join(parts[-2:])
        if parts:
            return "/" + parts[-1]
    return p


def _first_body(ev: dict) -> str:
    body = (
        ev.get("user_prompt_text")
        or ev.get("agent_response_text")
        or ev.get("command")
        or ev.get("tool_response")
        or ""
    )
    if not isinstance(body, str):
        body = str(body)
    return body


def _prefix_style(event_type: str) -> str:
    return {
        "user_prompt": "bold",
        "pre_tool": "bold cyan",
        "post_tool": "bold green",
        "agent_response": "bold",
        "session_start": "dim",
        "session_end": "dim",
        "pre_compact": "dim",
        "post_compact": "dim",
    }.get(event_type, "")


# ---- back-compat for tests that imported _render_row ----


def _render_row(ev: dict) -> tuple[str, str, str, str, str]:
    """Legacy 5-tuple (prefix, ts, type, locus, body) — kept so the
    existing semantic-prefix unit test in test_d5_tui.py keeps
    asserting the prefix vocabulary, even though the screen no
    longer uses a tuple-based DataTable row."""
    ts = short_time(ev.get("ts"))
    et = ev.get("event_type") or "?"
    prefix = _PREFIX.get(et, " ")
    tool = ev.get("tool_name") or ""
    paths = ev.get("paths") or []
    locus = tool
    if paths:
        locus = (tool + " " + paths[0]).strip()
    body = _first_body(ev)
    return (prefix, ts, et, truncate(locus, 30), truncate(body, 60))
