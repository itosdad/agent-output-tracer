"""`agent-output-tracer trace --session <id> --output <text>` — DESIGN §7.3.2.

For a phrase that appears in an agent's output, walk back to find:
- the first agent_response event that contains it
- the most-recent user_prompt before that (and whether the user mentioned it)
- every prior Read with whether the file's content contained the phrase
- a hallucination_candidate flag (no user mention anywhere + no Read source)

Phase D (DESIGN_FORENSIC_UX §7.1.2) adds two inverse / lookup modes:

- `trace_missing(...)` — given a phrase the user expected the agent to
  acknowledge and a list of reference paths, surface events where the
  phrase appeared in a tool_response but never made it into a subsequent
  agent_response. Use case: "I asked the agent to summarise X, and X
  shows up in the file it read, but the response forgot it."

- `trace_by_sha(...)` — given a SHA256 hash, list every post_tool event
  in the session whose response content-addressed to that hash. Pairs
  with the v2 `response_sha256` field and `core.indexer.content_hash_to_events`.
"""

from __future__ import annotations

import re
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


# ---------- trace --missing ----------


_WORD_RE = re.compile(r"[A-Za-z0-9_./-]{2,}")


def trace_missing(
    session_id: str,
    phrase: str,
    *,
    reference_paths: list[str] | None = None,
    data_dir=None,
    stream: IO[str] | None = None,
) -> dict:
    """Inverse hallucination: phrase appears in a tool_response (optionally
    restricted to `reference_paths`) but is absent from every later
    agent_response.

    Returns:
      {
        "session_id": ...,
        "phrase": ...,
        "reference_paths": [...],
        "appearances": [{event, path, ts}],
        "missing": bool — True when at least one appearance had no
          downstream agent_response mention,
        "downstream_agent_mention_idx": int | None — earliest agent
          response that did mention it (if any),
      }
    """
    if stream is None:
        stream = sys.stdout
    refs = reference_paths or []
    events = load_events(session_id, data_dir=data_dir)

    appearances: list[dict] = []
    first_appearance_idx = -1
    for i, ev in enumerate(events):
        if ev.get("event_type") != "post_tool":
            continue
        resp = ev.get("tool_response") or ""
        if phrase not in resp:
            continue
        paths = ev.get("paths") or []
        if refs and not any(p in refs for p in paths):
            continue
        appearances.append({"event_idx": i, "ts": ev.get("ts"), "paths": list(paths)})
        if first_appearance_idx == -1:
            first_appearance_idx = i

    downstream_idx: int | None = None
    if first_appearance_idx >= 0:
        for j in range(first_appearance_idx + 1, len(events)):
            ev = events[j]
            if ev.get("event_type") == "agent_response":
                text = ev.get("agent_response_text") or ""
                if phrase in text:
                    downstream_idx = j
                    break

    result = {
        "session_id": session_id,
        "phrase": phrase,
        "reference_paths": refs,
        "appearances": appearances,
        "downstream_agent_mention_idx": downstream_idx,
        "missing": bool(appearances) and downstream_idx is None,
    }
    _render_missing(result, stream)
    return result


def _render_missing(result, stream):
    phrase = result["phrase"]
    if not result["appearances"]:
        stream.write(
            f"{phrase!r} did not appear in any tool_response"
            + (
                f" within reference paths {result['reference_paths']}"
                if result["reference_paths"]
                else ""
            )
            + ".\n"
        )
        return
    stream.write(f"{phrase!r} surfaced in {len(result['appearances'])} tool_response(s):\n")
    for ap in result["appearances"]:
        ts = short_time(ap["ts"])
        stream.write(f"  - [{ts}] event {ap['event_idx']} paths={ap['paths']}\n")
    if result["downstream_agent_mention_idx"] is not None:
        stream.write(
            f"\n✓ Agent later acknowledged it at event {result['downstream_agent_mention_idx']}.\n"
        )
    else:
        stream.write(
            f"\n⚠️  MISSING: {phrase!r} appeared in tool output but the "
            f"agent never mentioned it in any subsequent response.\n"
        )


# ---------- trace --by-sha ----------


def trace_by_sha(
    session_id: str,
    sha: str,
    *,
    data_dir=None,
    stream: IO[str] | None = None,
) -> dict:
    """Find every post_tool event whose response content-addresses to
    the given SHA256.

    Falls back to recomputing the hash if the event predates v2 stamping.
    """
    if stream is None:
        stream = sys.stdout
    sha = sha.strip().lower()
    events = load_events(session_id, data_dir=data_dir)
    matches: list[dict] = []
    for i, ev in enumerate(events):
        if ev.get("event_type") != "post_tool":
            continue
        ev_sha = ev.get("response_sha256")
        if not ev_sha:
            resp = ev.get("tool_response")
            if isinstance(resp, str) and resp:
                import hashlib

                ev_sha = hashlib.sha256(resp.encode("utf-8")).hexdigest()
        if ev_sha == sha:
            matches.append(
                {
                    "event_idx": i,
                    "ts": ev.get("ts"),
                    "paths": list(ev.get("paths") or []),
                    "tool": ev.get("tool_name"),
                }
            )
    result = {"session_id": session_id, "sha": sha, "matches": matches}

    if not matches:
        stream.write(f"No post_tool events with SHA256 {sha}.\n")
    else:
        stream.write(f"Found {len(matches)} post_tool event(s) with SHA256 {sha}:\n")
        for m in matches:
            stream.write(
                f"  - event {m['event_idx']} [{short_time(m['ts'])}] "
                f"{m['tool']} paths={m['paths']}\n"
            )
    return result
