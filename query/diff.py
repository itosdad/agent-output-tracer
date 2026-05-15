"""`agent-output-tracer diff --session <id>` — DESIGN §7.3.4.

Two-way asymmetric report:
- paths the user *mentioned* in any prompt but the agent never touched
- paths the agent touched without any user mention (full path or basename)
"""

from __future__ import annotations

import os
import re
import sys
from typing import IO

from core.session_io import load_events

# Path-like tokens in free-form user prompt text.
# - absolute: /foo/bar.md
# - home: ~/foo/bar
# - relative-explicit: ./foo, ../bar
# - basename-with-ext: foo.tsx, README.md
# Stops at whitespace, commas, parens, quotes, brackets.
_PATH_TOKEN = re.compile(
    r"(?:[/~][^\s,()\[\]\'\"`]+"
    r"|\.{1,2}/[^\s,()\[\]\'\"`]+"
    r"|\b[\w\-.]+\.[A-Za-z0-9]{1,5}\b)"
)


def diff(
    session_id: str,
    *,
    data_dir=None,
    stream: IO[str] | None = None,
) -> dict:
    if stream is None:
        stream = sys.stdout

    events = load_events(session_id, data_dir=data_dir)

    user_text_joined = " ".join(
        ev.get("user_prompt_text") or "" for ev in events if ev.get("event_type") == "user_prompt"
    )

    touched_paths: set[str] = set()
    for ev in events:
        if ev.get("event_type") != "pre_tool":
            continue
        for p in ev.get("paths") or []:
            if isinstance(p, str) and p:
                touched_paths.add(p)
    touched_basenames = {os.path.basename(p) for p in touched_paths if p}

    mentioned_raw = set(_PATH_TOKEN.findall(user_text_joined))
    mentioned_raw = {m.rstrip(".,;:!?") for m in mentioned_raw if m}

    # User mentions not served by any touch.
    user_unserved: set[str] = set()
    for m in mentioned_raw:
        if m in touched_paths:
            continue
        base = os.path.basename(m) or m
        if base in touched_basenames:
            continue
        user_unserved.add(m)

    # Agent touches without any user mention.
    agent_unprompted: set[str] = set()
    for p in touched_paths:
        base = os.path.basename(p)
        if p in user_text_joined or (base and base in user_text_joined):
            continue
        agent_unprompted.add(p)

    result = {
        "session_id": session_id,
        "user_mentioned_not_touched": sorted(user_unserved),
        "agent_touched_no_mention": sorted(agent_unprompted),
    }
    _render_text(result, stream)
    return result


def _render_text(result, stream):
    stream.write(f"Session: {result['session_id']}\n\n")

    stream.write("User mentioned but agent did NOT access:\n")
    if result["user_mentioned_not_touched"]:
        for m in result["user_mentioned_not_touched"]:
            stream.write(f"  - {m}\n")
    else:
        stream.write("  (none)\n")

    stream.write("\nAgent accessed without user mention:\n")
    if result["agent_touched_no_mention"]:
        for p in result["agent_touched_no_mention"]:
            stream.write(f"  - {p}\n")
    else:
        stream.write("  (none)\n")

    if result["user_mentioned_not_touched"] or result["agent_touched_no_mention"]:
        stream.write(
            "\n(Note: agent may have legitimate reasons to read additional "
            "files, but each should be reviewable.)\n"
        )
