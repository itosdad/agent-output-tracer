"""`aot tail --session SPEC [--format text|stream-json]` —
DESIGN_FORENSIC_UX §7.10.

Follow events.jsonl as a session progresses. `stream-json` emits each
event as a single-line JSON object so log forwarders / CI can consume
it directly.
"""

from __future__ import annotations

import json
import sys
from typing import IO

from core.follower import follow_events
from core.time_utils import short_time


def tail(
    session_id: str,
    *,
    data_dir=None,
    fmt: str = "text",
    from_start: bool = False,
    poll_interval: float = 0.5,
    stop_after_seconds: float | None = None,
    stream: IO[str] | None = None,
) -> int:
    if stream is None:
        stream = sys.stdout
    n = 0
    for ev in follow_events(
        session_id,
        data_dir=data_dir,
        from_start=from_start,
        poll_interval=poll_interval,
        stop_after_seconds=stop_after_seconds,
    ):
        if fmt == "stream-json":
            stream.write(json.dumps(ev, ensure_ascii=False) + "\n")
        else:
            stream.write(_render_event(ev))
        stream.flush()
        n += 1
    return n


def _render_event(ev: dict) -> str:
    ts = short_time(ev.get("ts"))
    et = ev.get("event_type") or "?"
    body = (
        ev.get("user_prompt_text")
        or ev.get("agent_response_text")
        or ev.get("command")
        or ""
    )
    paths = ev.get("paths") or []
    tool = ev.get("tool_name") or ""
    extras = []
    if tool:
        extras.append(tool)
    if paths:
        extras.append(paths[0])
    extra_str = (" " + " ".join(extras)) if extras else ""
    snippet = body[:140].replace("\n", " ") if body else ""
    return f"[{ts}] {et:<14}{extra_str}  {snippet}\n"
