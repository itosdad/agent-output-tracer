"""`agent-output-tracer state-at --session <id> --time <ts>` —
session state snapshot at a chosen moment (DESIGN §7.3.5).
"""

from __future__ import annotations

import re
import sys
from datetime import datetime
from typing import IO

from core.session_io import load_events
from core.time_utils import human_bytes

HHMMSS_RE = re.compile(r"^\d{2}:\d{2}:\d{2}$")
REPEAT_THRESHOLD = 3
TOP_READ_LIMIT = 10


def _parse_target(time_spec, events):
    """Parse a time spec into a comparable string.

    Spec forms:
      - `latest`: returns None, meaning "no truncation"
      - HH:MM:SS: rendered against the first event's date
      - ISO 8601 datetime: kept as-is
    """
    if not isinstance(time_spec, str) or not time_spec:
        raise ValueError(f"empty time spec: {time_spec!r}")
    if time_spec == "latest":
        return None
    if HHMMSS_RE.match(time_spec):
        if not events:
            raise ValueError("HH:MM:SS form needs at least one event for the date")
        first_ts = events[0].get("ts") or ""
        date_prefix = first_ts[:10]
        offset_suffix = first_ts[-6:] if len(first_ts) >= 6 else "+00:00"
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_prefix):
            raise ValueError(f"cannot infer date from first event ts: {first_ts!r}")
        return f"{date_prefix}T{time_spec}{offset_suffix}"
    try:
        datetime.fromisoformat(time_spec)
    except ValueError as exc:
        raise ValueError(f"invalid time spec: {time_spec!r}") from exc
    return time_spec


def _ts_le(event_ts, target):
    """True if event_ts <= target. Both are ISO 8601 strings parsed to
    aware datetimes for safe comparison."""
    if target is None:
        return True
    if not isinstance(event_ts, str):
        return False
    try:
        et = datetime.fromisoformat(event_ts)
        tt = datetime.fromisoformat(target)
    except ValueError:
        return False
    return et <= tt


def state_at(
    session_id,
    time_spec,
    *,
    data_dir=None,
    stream: IO[str] | None = None,
):
    if stream is None:
        stream = sys.stdout

    events = load_events(session_id, data_dir=data_dir)
    target = _parse_target(time_spec, events)
    truncated = [e for e in events if _ts_le(e.get("ts"), target)]

    files_read = {}
    total_bytes = 0
    user_prompts = 0
    tool_calls = 0
    agent_responses = 0

    for e in truncated:
        et = e.get("event_type")
        if et == "user_prompt":
            user_prompts += 1
        elif et == "agent_response":
            agent_responses += 1
        elif et == "pre_tool":
            tool_calls += 1
        elif et == "post_tool" and e.get("tool_name") == "Read":
            for p in e.get("paths") or []:
                if isinstance(p, str):
                    files_read[p] = files_read.get(p, 0) + 1
            total_bytes += int(e.get("result_bytes") or 0)

    label = time_spec
    stream.write(f"State at {label}:\n")
    stream.write(
        f"  Files read so far: {len(files_read)} unique, {sum(files_read.values())} total reads\n"
    )
    stream.write(f"  Total bytes from Read: {human_bytes(total_bytes)} ({total_bytes:,} B)\n")
    stream.write(f"  User prompts so far: {user_prompts}\n")
    stream.write(f"  Tool calls so far: {tool_calls}\n")
    stream.write(f"  Agent responses so far: {agent_responses}\n")

    if files_read:
        stream.write("\nTop read files:\n")
        for path, count in sorted(files_read.items(), key=lambda kv: -kv[1])[:TOP_READ_LIMIT]:
            marker = " ⚠️ repeated" if count >= REPEAT_THRESHOLD else ""
            stream.write(f"  {count}x  {path}{marker}\n")
