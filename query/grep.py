"""`agent-output-tracer grep --session <id> --pattern <regex>` —
session-wide full-text search across all string-valued fields.
"""

from __future__ import annotations

import re
import sys
from typing import IO

from core.session_io import load_events
from core.time_utils import short_time, truncate

MATCH_PREVIEW_LIMIT = 200


def grep(
    session_id: str,
    pattern: str,
    *,
    data_dir=None,
    ignore_case: bool = False,
    stream: IO[str] | None = None,
) -> int:
    """Print one line per match. Returns the total match count.

    Re-raises `re.error` on invalid pattern (caller / CLI decides how
    to surface it).
    """
    if stream is None:
        stream = sys.stdout

    flags = re.IGNORECASE if ignore_case else 0
    regex = re.compile(pattern, flags)

    events = load_events(session_id, data_dir=data_dir)
    count = 0
    for ev in events:
        for field, text in _iter_searchable(ev):
            if not isinstance(text, str):
                continue
            if regex.search(text):
                ts = short_time(ev.get("ts"))
                etype = ev.get("event_type")
                preview = truncate(text.replace("\n", " "), MATCH_PREVIEW_LIMIT)
                stream.write(f"[{ts}] {etype}.{field}: {preview}\n")
                count += 1
    return count


SEARCHABLE_TOP_LEVEL_FIELDS = (
    "user_prompt_text",
    "agent_response_text",
    "tool_response",
    "command",
    "tool_name",
    "stop_reason",
    "cwd",
)


def _iter_searchable(event):
    """Yield (field_name, text) tuples for every string-bearing field."""
    if not isinstance(event, dict):
        return
    for f in SEARCHABLE_TOP_LEVEL_FIELDS:
        v = event.get(f)
        if isinstance(v, str) and v:
            yield f, v

    for i, p in enumerate(event.get("paths") or []):
        if isinstance(p, str) and p:
            yield f"paths[{i}]", p

    tinp = event.get("tool_input")
    if isinstance(tinp, dict):
        for key, value in tinp.items():
            if isinstance(value, str) and value:
                yield f"tool_input.{key}", value
