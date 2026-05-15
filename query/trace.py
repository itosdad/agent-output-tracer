"""`agent-output-tracer trace --session <id> --output <text>` — DESIGN §7.3.2.

For a phrase that appears in an agent's output, walk back to find:
- the first agent_response event that contains it
- the most-recent user_prompt before that (and whether the user mentioned it)
- every prior Read with whether the file's content contained the phrase
- a hallucination_candidate flag (no user mention anywhere + no Read source)
"""

from __future__ import annotations

import sys
from typing import IO

from core.session_io import load_events
from core.time_utils import short_time


def trace(
    session_id: str,
    output_excerpt: str,
    *,
    data_dir=None,
    stream: IO[str] | None = None,
) -> dict:
    if stream is None:
        stream = sys.stdout

    events = load_events(session_id, data_dir=data_dir)

    first_idx, first_event = _find_first_mention(events, output_excerpt)
    result: dict = {
        "session_id": session_id,
        "output_excerpt": output_excerpt,
        "first_mention_event": first_event,
        "first_mention_ts": first_event["ts"] if first_event else None,
        "user_prompt_source": None,
        "read_sources": [],
        "hallucination_candidate": False,
    }

    if first_event is None:
        stream.write(
            f"Output {output_excerpt!r} not found in any agent_response of session {session_id}.\n"
        )
        return result

    prior = events[:first_idx]
    result["user_prompt_source"] = _user_prompt_source(prior, output_excerpt)
    result["read_sources"] = _read_sources(prior, output_excerpt)
    result["hallucination_candidate"] = _is_hallucination(prior, output_excerpt)

    _render_text(result, stream)
    return result


# ---------- analysis ----------


def _find_first_mention(events, excerpt):
    """Return (index, event) of the first agent_response containing excerpt."""
    for i, ev in enumerate(events):
        if ev.get("event_type") != "agent_response":
            continue
        text = ev.get("agent_response_text") or ""
        if excerpt in text:
            return i, ev
    return -1, None


def _user_prompt_source(prior_events, excerpt):
    """Most-recent user_prompt before first mention.

    `matched` reflects whether that specific prompt's text contains the
    excerpt. The whole-session search for hallucination is separate.
    """
    for ev in reversed(prior_events):
        if ev.get("event_type") == "user_prompt":
            text = ev.get("user_prompt_text") or ""
            return {"event": ev, "matched": excerpt in text}
    return None


def _read_sources(prior_events, excerpt):
    """Every prior `post_tool` Read with whether its response contains
    the excerpt."""
    out = []
    for ev in prior_events:
        if ev.get("event_type") != "post_tool":
            continue
        if ev.get("tool_name") != "Read":
            continue
        response = ev.get("tool_response") or ""
        for path in ev.get("paths") or []:
            out.append(
                {
                    "event": ev,
                    "path": path,
                    "contains": excerpt in response,
                }
            )
    return out


def _is_hallucination(prior_events, excerpt):
    """True when no user_prompt in the whole prior context mentions the
    excerpt, AND no Read tool_response contains it. We check the whole
    `prior_events` (not just the immediately preceding user_prompt) so
    we don't false-positive on a user who introduced the phrase earlier
    in the session."""
    for ev in prior_events:
        et = ev.get("event_type")
        if et == "user_prompt":
            text = ev.get("user_prompt_text") or ""
            if excerpt in text:
                return False
        elif et == "post_tool" and ev.get("tool_name") == "Read":
            response = ev.get("tool_response") or ""
            if excerpt in response:
                return False
    return True


# ---------- rendering ----------


def _render_text(result, stream):
    excerpt = result["output_excerpt"]
    first = result["first_mention_event"]
    stream.write(
        f"Output {excerpt!r} first appeared at {short_time(first['ts'])} "
        f"(first mention by agent).\n"
    )
    stream.write("\nCausal trail (prior events):\n")

    up = result["user_prompt_source"]
    if up:
        ev = up["event"]
        marker = "✓ mentioned" if up["matched"] else "✗ not mentioned"
        text = (ev.get("user_prompt_text") or "")[:120]
        stream.write(f"  - last user prompt at {short_time(ev['ts'])}: {marker}\n      {text}\n")
    else:
        stream.write("  - no user prompt before this output\n")

    sources = result["read_sources"]
    if sources:
        stream.write("  - files read prior to this output:\n")
        for s in sources:
            ts = short_time(s["event"]["ts"])
            mark = "✓ contains" if s["contains"] else "✗ does not contain"
            stream.write(f"      [{ts}] {s['path']}: {mark}\n")
    else:
        stream.write("  - no Read events before this output\n")

    if result["hallucination_candidate"]:
        stream.write(
            f"\n⚠️  HALLUCINATION CANDIDATE: {excerpt!r} has no visible source "
            f"in user prompts or tool results before the agent said it.\n"
        )
