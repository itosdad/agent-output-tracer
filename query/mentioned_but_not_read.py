"""`agent-output-tracer mentioned-but-not-read --session <id>` —
DESIGN §7.3.8.

Session-level hallucination candidate extractor. Walks every
agent_response, pulls out path-like tokens, and reports those that
don't appear in any user_prompt text or any tool_response in the
session. Basename-aware (so the user saying `foo.md` grounds an agent's
later `/proj/foo.md`).
"""

from __future__ import annotations

import os
import sys
from typing import IO

from core.references import extract_path_tokens
from core.session_io import load_events


def mentioned_but_not_read(
    session_id: str,
    *,
    data_dir=None,
    stream: IO[str] | None = None,
) -> dict:
    if stream is None:
        stream = sys.stdout

    events = load_events(session_id, data_dir=data_dir)

    user_text = " ".join(
        ev.get("user_prompt_text") or "" for ev in events if ev.get("event_type") == "user_prompt"
    )
    tool_response_text = " ".join(
        ev.get("tool_response") or "" for ev in events if ev.get("event_type") == "post_tool"
    )

    candidates = []
    seen_tokens = set()
    for ev in events:
        if ev.get("event_type") != "agent_response":
            continue
        text = ev.get("agent_response_text") or ""
        for token in extract_path_tokens(text):
            if token in seen_tokens:
                continue
            if _is_grounded(token, user_text, tool_response_text):
                seen_tokens.add(token)
                continue
            seen_tokens.add(token)
            candidates.append(
                {
                    "token": token,
                    "first_seen_ts": ev.get("ts"),
                    "first_seen_event": ev,
                }
            )

    # Stable order: chronological by first_seen_ts (events were already
    # appended in order; we walked in that order, so the list is already
    # chronological)

    result = {"session_id": session_id, "candidates": candidates}
    _render_text(result, stream)
    return result


def _is_grounded(token, user_text, tool_response_text):
    """A token is grounded if its full string, its trailing-slash-stripped
    form, or its basename appears in user prompts or tool responses."""
    stripped = token.rstrip("/")
    base = os.path.basename(stripped) or stripped
    for haystack in (user_text, tool_response_text):
        if token in haystack or stripped in haystack:
            return True
        if base and base in haystack:
            return True
    return False


def _render_text(result, stream):
    stream.write(f"Session: {result['session_id']}\n\n")
    stream.write("Hallucination candidates (mentioned in agent response, no visible source):\n")
    if not result["candidates"]:
        stream.write("  (none — every path-like mention is grounded)\n")
        return
    for c in result["candidates"]:
        ts = c.get("first_seen_ts") or ""
        stream.write(f"  - {c['token']}    [first seen at {ts}]\n")
