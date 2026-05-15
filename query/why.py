"""`agent-output-tracer why --session <id> --path <p>` — DESIGN §7.3.3.

For a specific event in a session, surface the context that may have
caused it: the three events immediately before, the most-recent user
prompt, and (when applicable) the prior Glob result that introduced
the target's path.
"""

from __future__ import annotations

import sys
from typing import IO

from core.session_io import load_events
from core.time_utils import short_time


class EventNotFound(LookupError):
    """No event matched the supplied selectors."""


def why(
    session_id: str,
    *,
    path: str | None = None,
    tool: str | None = None,
    ts: str | None = None,
    event_index: int | None = None,
    data_dir=None,
    stream: IO[str] | None = None,
) -> dict:
    if stream is None:
        stream = sys.stdout

    events = load_events(session_id, data_dir=data_dir)
    target_idx, target = _locate(events, path=path, tool=tool, ts=ts, event_index=event_index)

    preceding = events[max(0, target_idx - 3) : target_idx]
    last_prompt = _last_user_prompt(events[:target_idx])
    glob_origin = _glob_origin(events[:target_idx], target)

    result = {
        "session_id": session_id,
        "target": target,
        "preceding": preceding,
        "last_user_prompt": last_prompt,
        "glob_origin": glob_origin,
    }
    _render_text(result, stream)
    return result


# ---------- locator ----------


def _locate(events, *, path, tool, ts, event_index):
    if event_index is not None:
        if not (0 <= event_index < len(events)):
            raise EventNotFound(
                f"event_index {event_index} out of range (session has {len(events)} events)"
            )
        return event_index, events[event_index]

    if path is None and tool is None:
        raise EventNotFound("supply --path / --tool / --event-index to identify the target event")

    short_ts = ts

    for i, ev in enumerate(events):
        if path is not None and path not in (ev.get("paths") or []):
            continue
        if tool is not None and ev.get("tool_name") != tool:
            continue
        if short_ts is not None:
            ev_ts = ev.get("ts") or ""
            # ts may be "HH:MM:SS" or a full ISO string; match by suffix.
            if short_ts not in ev_ts:
                continue
        return i, ev

    selectors = []
    if path is not None:
        selectors.append(f"path={path!r}")
    if tool is not None:
        selectors.append(f"tool={tool!r}")
    if ts is not None:
        selectors.append(f"ts={ts!r}")
    raise EventNotFound(f"no event matches {' / '.join(selectors)}")


# ---------- helpers ----------


def _last_user_prompt(prior_events):
    for ev in reversed(prior_events):
        if ev.get("event_type") == "user_prompt":
            return ev
    return None


def _glob_origin(prior_events, target):
    """A prior post_tool Glob whose tool_response mentions any of the
    target's paths. Returns the latest such Glob (most recent context)."""
    target_paths = target.get("paths") or []
    if not target_paths:
        return None
    for ev in reversed(prior_events):
        if ev.get("event_type") != "post_tool":
            continue
        if ev.get("tool_name") != "Glob":
            continue
        response = ev.get("tool_response") or ""
        if any(p in response for p in target_paths):
            return ev
    return None


# ---------- rendering ----------


def _render_text(result, stream):
    t = result["target"]
    ts = short_time(t.get("ts"))
    tool = t.get("tool_name") or t.get("event_type") or "?"
    paths = t.get("paths") or []
    summary = paths[0] if paths else (t.get("command") or "")
    stream.write(f"Event: [{ts}] {tool} {summary}\n\n")

    stream.write("What came immediately before:\n")
    if result["preceding"]:
        for pe in result["preceding"]:
            stream.write(f"  - {_format_brief(pe)}\n")
    else:
        stream.write("  (no events before this)\n")

    stream.write("\nLast user prompt before this event:\n")
    up = result["last_user_prompt"]
    if up:
        text = (up.get("user_prompt_text") or "")[:200]
        stream.write(f"  [{short_time(up.get('ts'))}] {text}\n")
    else:
        stream.write("  (no user prompt before this event)\n")

    g = result["glob_origin"]
    if g:
        pattern = (g.get("tool_input") or {}).get("pattern", "")
        stream.write(
            f"\n⚠️  This path appeared in a Glob result at {short_time(g.get('ts'))}:\n"
            f"     Glob pattern: {pattern!r}\n"
            f"     (the agent picked this path from Glob results; no explicit user mention)\n"
        )


def _format_brief(ev):
    ts = short_time(ev.get("ts"))
    et = ev.get("event_type")
    if et == "user_prompt":
        text = (ev.get("user_prompt_text") or "")[:80]
        return f"[{ts}] user: {text}"
    if et in ("pre_tool", "post_tool"):
        tool = ev.get("tool_name") or "?"
        paths = ev.get("paths") or []
        cmd = ev.get("command")
        target = (
            paths[0]
            if paths
            else (cmd[:60] if cmd else (ev.get("tool_input") or {}).get("pattern", ""))
        )
        kind = "→" if et == "pre_tool" else "↳"
        return f"[{ts}] {kind} {tool} {target}"
    if et == "agent_response":
        text = (ev.get("agent_response_text") or "")[:80]
        return f"[{ts}] agent: {text}"
    return f"[{ts}] {et}"
