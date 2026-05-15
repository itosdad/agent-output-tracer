"""`agent-output-tracer causal-graph --session <id> [--output <path>]` —
DESIGN §7.3.7. Render a session as a mermaid graph: one node per event,
linear edges between consecutive events, plus dashed causal arrows
from each prior Glob to a Read whose path appeared in the Glob's result.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import IO

from core.session_io import load_events
from core.time_utils import short_time, truncate

LABEL_MAX = 80


def causal_graph(
    session_id: str,
    *,
    data_dir=None,
    output_path: Path | str | None = None,
    stream: IO[str] | None = None,
) -> dict:
    if stream is None:
        stream = sys.stdout

    events = load_events(session_id, data_dir=data_dir)

    lines: list[str] = ["```mermaid", "graph TD"]
    for i, ev in enumerate(events):
        lines.append(f'  E{i}["{_label(ev)}"]')

    edge_count = 0
    dashed_count = 0
    for i in range(1, len(events)):
        lines.append(f"  E{i - 1} --> E{i}")
        edge_count += 1
        cur = events[i]
        if cur.get("event_type") == "pre_tool" and cur.get("tool_name") == "Read":
            target_path = (cur.get("paths") or [""])[0]
            if target_path:
                glob_idx = _glob_idx_returning(events[:i], target_path)
                if glob_idx is not None:
                    lines.append(f"  E{glob_idx} -.->|returned this path| E{i}")
                    dashed_count += 1

    lines.append("```")
    mermaid = "\n".join(lines)

    if output_path is not None:
        Path(output_path).write_text(mermaid + "\n", encoding="utf-8")
    else:
        stream.write(mermaid + "\n")

    return {
        "session_id": session_id,
        "node_count": len(events),
        "edge_count": edge_count,
        "dashed_edge_count": dashed_count,
        "mermaid": mermaid,
    }


def _label(ev) -> str:
    """Build a short, mermaid-safe label for an event node."""
    ts = short_time(ev.get("ts"))
    et = ev.get("event_type") or "?"
    if et == "user_prompt":
        text = ev.get("user_prompt_text") or ""
        body = f"user: {text}"
    elif et == "pre_tool":
        body = f"→ {ev.get('tool_name') or '?'} {_target_summary(ev)}"
    elif et == "post_tool":
        body = f"↳ {ev.get('tool_name') or '?'} result"
    elif et == "agent_response":
        text = ev.get("agent_response_text") or ""
        body = f"agent: {text}"
    elif et == "session_end":
        body = "session_end"
    else:
        body = et
    body = truncate(body, LABEL_MAX)
    # Mermaid label safety: drop newlines, escape double quotes via #quot;
    body = body.replace("\n", " ").replace('"', "#quot;")
    return f"[{ts}] {body}"


def _target_summary(ev) -> str:
    paths = ev.get("paths") or []
    if paths:
        return paths[0]
    cmd = ev.get("command")
    if cmd:
        return cmd[:40]
    pattern = (ev.get("tool_input") or {}).get("pattern")
    return pattern or ""


def _glob_idx_returning(prior_events, target_path):
    for i, ev in enumerate(prior_events):
        if ev.get("event_type") != "post_tool":
            continue
        if ev.get("tool_name") != "Glob":
            continue
        response = ev.get("tool_response") or ""
        if target_path in response:
            return i
    return None
