"""Trace results screen — the causal trail for one (phrase, session).

Renders the result of `query.trace.trace()`:
  - the first agent_response event that mentions the phrase
  - the most recent user_prompt before that (matched / not matched)
  - every prior Read with whether its body contained the phrase
  - a `⚠ HALLUCINATION CANDIDATE` banner when nothing grounded the
    phrase before the agent said it

Enter on the first-mention event drills into Event Detail.
"""

from __future__ import annotations

from rich.text import Text
from textual.binding import Binding
from textual.widgets import Static

from core.session_io import load_events
from core.session_resolver import resolve_session_id
from core.time_utils import short_time
from query.trace import trace as _trace
from tui.router import AOTScreen


class TraceResultsScreen(AOTScreen):
    TITLE = "trace"

    BINDINGS = [
        Binding("enter", "open_event", "open source event", show=False),
        Binding("r", "refresh", "refresh", show=False),
    ]

    def __init__(
        self,
        *,
        phrase: str,
        session_id: str = "latest",
        data_dir=None,
    ) -> None:
        self.phrase = phrase
        self.session_id = session_id
        self._data_dir = data_dir
        self._resolved_sid: str = ""
        self._events: list[dict] = []
        self._result: dict = {}
        super().__init__()

    def breadcrumb_segments(self) -> list[str]:
        preview = self.phrase[:14] + ("…" if len(self.phrase) > 14 else "")
        return ["agent-output-tracer", "trace", repr(preview)]

    def footer_hints(self) -> list[tuple[str, str]]:
        return [
            ("g/G", "top/bot"),
            ("enter", "open event"),
            ("r", "refresh"),
            ("esc", "back"),
        ]

    def help_entries(self) -> list[tuple[str, str]]:
        return [
            ("enter", "drill into the first-mention event"),
            ("r", "re-run trace"),
            ("g / G", "scroll to top / bottom"),
        ]

    def compose_body(self):
        yield Static("(tracing…)", id="trace-body", expand=True, markup=False)

    def on_mount(self) -> None:
        self._refresh_view()

    def action_refresh(self) -> None:
        self._refresh_view()

    def action_open_event(self) -> None:
        first = self._result.get("first_mention_event")
        if not first or not self._events:
            self.app.bell()
            return
        # Locate index by identity / ts match.
        target_ts = first.get("ts")
        for i, ev in enumerate(self._events):
            if ev.get("ts") == target_ts and ev.get("event_type") == "agent_response":
                from tui.screens.event_detail import EventDetailScreen

                self.app.push_screen(
                    EventDetailScreen(
                        event=ev,
                        event_index=i,
                        session_id=self._resolved_sid,
                        all_events=self._events,
                        data_dir=self._data_dir,
                    )
                )
                return
        self.app.bell()

    def _refresh_view(self) -> None:
        try:
            resolved = resolve_session_id(self.session_id, data_dir=self._data_dir)
        except Exception:
            resolved = self.session_id
        self._resolved_sid = resolved or ""
        try:
            self._events = load_events(resolved, data_dir=self._data_dir)
        except Exception:
            self._events = []
        try:
            self._result = _trace(
                resolved,
                self.phrase,
                data_dir=self._data_dir,
                stream=_NullStream(),
            )
        except Exception as exc:
            from tui._accent import error

            self.query_one("#trace-body", Static).update(
                Text(f"error: {exc}", style=error(self.app))
            )
            return
        self.query_one("#trace-body", Static).update(
            _render_trace(self.phrase, self._result, self.app)
        )


class _NullStream:
    def write(self, _s: str) -> int:
        return 0

    def flush(self) -> None:
        return None


def _render_trace(phrase: str, r: dict, app) -> Text:
    from tui._accent import error, success, warning

    ok_col = success(app)
    warn_col = warning(app)
    err_col = error(app)

    text = Text()
    first = r.get("first_mention_event")
    if first is None:
        text.append("phrase not found in any agent_response\n", style="dim")
        text.append("  phrase: ", style="dim")
        text.append(repr(phrase))
        return text

    text.append("First mention\n", style="bold")
    text.append("  ts:   ", style="dim")
    text.append(f"{short_time(first.get('ts'))}\n")
    excerpt = (first.get("agent_response_text") or "").split("\n", 1)[0][:120]
    if excerpt:
        text.append("  body: ", style="dim")
        text.append(f"{excerpt}\n")

    up = r.get("user_prompt_source")
    text.append("\nLast user prompt before\n", style="bold")
    if up is None:
        text.append(
            "  (none — agent introduced the phrase with no preceding prompt)\n", style="dim"
        )
    else:
        marker = "✓ mentioned" if up.get("matched") else "✗ not mentioned"
        style = ok_col if up.get("matched") else warn_col
        ev = up.get("event") or {}
        text.append(f"  {marker}", style=style)
        text.append(f"  at {short_time(ev.get('ts'))}\n", style="dim")
        prompt_excerpt = (ev.get("user_prompt_text") or "")[:120]
        if prompt_excerpt:
            text.append(f"  {prompt_excerpt}\n", style="dim")

    sources = r.get("read_sources") or []
    text.append("\nReads before\n", style="bold")
    if not sources:
        text.append("  (no prior Reads)\n", style="dim")
    else:
        for s in sources:
            ev = s.get("event") or {}
            mark = "✓ contains" if s.get("contains") else "✗ does not contain"
            style = ok_col if s.get("contains") else "dim"
            text.append(f"  [{short_time(ev.get('ts'))}] ", style="dim")
            text.append(f"{s.get('path', '?')}", style="")
            text.append(f"  {mark}\n", style=style)

    if r.get("hallucination_candidate"):
        text.append("\n")
        text.append("⚠ hallucination candidate\n", style=f"bold {err_col}")
        text.append(
            "  no user prompt or Read response grounded this phrase before the agent said it.\n",
            style=err_col,
        )

    return text
