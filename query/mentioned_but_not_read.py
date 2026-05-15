"""`agent-output-tracer mentioned-but-not-read --session <id>` —
DESIGN §7.3.8.

Session-level hallucination candidate extractor. Walks every
agent_response, pulls out path-like tokens, and reports those that
don't appear in any user_prompt text or any tool_response **earlier
in the session**. Basename-aware (so the user saying `foo.md` grounds
an agent's later `/proj/foo.md`).

Two correctness invariants (mirrored in `query/find.py::_hallucinations`):

1. **Time-causality.** Only prior events contribute to the grounding
   corpus — a user prompt or tool response that appears AFTER the
   agent_response cannot retroactively ground a claim the agent
   already made.
2. **Self-paste resilience.** Pasted-back tracer output is stripped
   from user prompts before they enter the corpus, so running the
   detector twice in a row produces consistent results.
"""

from __future__ import annotations

import sys
from typing import IO

from core.references import extract_path_tokens, is_grounded, strip_tracer_output
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

    candidates = []
    seen_tokens: set = set()
    user_parts: list[str] = []
    tool_parts: list[str] = []
    for ev in events:
        et = ev.get("event_type")
        if et == "user_prompt":
            user_parts.append(strip_tracer_output(ev.get("user_prompt_text") or ""))
            continue
        if et == "post_tool":
            resp = ev.get("tool_response")
            if isinstance(resp, str):
                tool_parts.append(resp)
            continue
        if et != "agent_response":
            continue
        user_text = " ".join(user_parts)
        tool_text = " ".join(tool_parts)
        text = ev.get("agent_response_text") or ""
        for token in extract_path_tokens(text):
            if token in seen_tokens:
                continue
            if is_grounded(token, user_text, tool_text):
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

    result = {"session_id": session_id, "candidates": candidates}
    _render_text(result, stream)
    return result


def _render_text(result, stream):
    stream.write(f"Session: {result['session_id']}\n\n")
    stream.write("Hallucination candidates (mentioned in agent response, no visible source):\n")
    if not result["candidates"]:
        stream.write("  (none — every path-like mention is grounded)\n")
        return
    for c in result["candidates"]:
        ts = c.get("first_seen_ts") or ""
        stream.write(f"  - {c['token']}    [first seen at {ts}]\n")
