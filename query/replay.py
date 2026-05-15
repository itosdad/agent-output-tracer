"""`agent-output-tracer replay --session <id>` — the timeline renderer.

Phase A's most important user-facing command. Reads events.jsonl back
and prints a human-friendly chronological view per DESIGN §7.3.1.
"""

from __future__ import annotations

import json
import sys
from typing import IO

from core.session_io import list_sessions, load_events, load_metadata
from core.time_utils import human_bytes, short_time, truncate

DEFAULT_TEXT_PROMPT_LIMIT = 200
DEFAULT_TEXT_RESPONSE_LIMIT = 200


def replay(
    session_id: str,
    *,
    data_dir=None,
    fmt: str = "text",
    show_hints: bool = False,
    stream: IO[str] | None = None,
) -> None:
    """Render the session timeline to `stream` (defaults to stdout)."""
    if stream is None:
        stream = sys.stdout

    events = load_events(session_id, data_dir=data_dir)
    metadata = load_metadata(session_id, data_dir=data_dir)

    hints = []
    if show_hints:
        from analyzer.anomaly_hints import detect_hints

        all_sessions = list_sessions(data_dir=data_dir)
        hints = detect_hints(events, metadata=metadata, all_sessions=all_sessions)

    if fmt == "json":
        _render_json(session_id, metadata, events, stream, hints=hints)
    elif fmt == "markdown":
        _render_markdown(session_id, metadata, events, stream, hints=hints)
    else:
        _render_text(session_id, metadata, events, stream, hints=hints)


# --------- text ----------


def _render_text(session_id, metadata, events, stream, *, hints=None):
    stream.write(f"Session: {session_id}\n")
    if metadata:
        if metadata.get("ts_start"):
            stream.write(f"Started: {metadata['ts_start']}\n")
        if metadata.get("ts_end") and metadata.get("ts_end") != metadata.get("ts_start"):
            stream.write(f"Ended:   {metadata['ts_end']}\n")
        if metadata.get("cwd"):
            stream.write(f"Cwd:     {metadata['cwd']}\n")
        stream.write(f"Events:  {len(events)}\n")
        stream.write(
            "Counts:  "
            f"tools={metadata.get('tool_calls_total', 0)} "
            f"user_prompts={metadata.get('user_prompts_count', 0)} "
            f"agent_responses={metadata.get('agent_responses_count', 0)} "
            f"unique_reads={metadata.get('unique_files_read', 0)} "
            f"({human_bytes(metadata.get('total_bytes_read', 0))})\n"
        )
    else:
        stream.write(f"Events:  {len(events)}\n")
    stream.write("\n")

    for ev in events:
        line = _format_event_line(ev)
        if line:
            stream.write(line + "\n")

    if not events:
        stream.write("(no events captured for this session)\n")

    if hints:
        stream.write("\nAnomaly hints:\n")
        for h in hints:
            sev = h.get("severity", "info").upper()
            ts = short_time(h.get("ts")) if h.get("ts") else "--:--:--"
            stream.write(f"  [{sev}] [{ts}] {h.get('pattern')}: {h.get('message')}\n")


def _format_event_line(ev):
    ts = short_time(ev.get("ts"))
    et = ev.get("event_type")
    if et == "user_prompt":
        text = truncate(ev.get("user_prompt_text") or "", DEFAULT_TEXT_PROMPT_LIMIT)
        return f"[{ts}] [user] {text}"
    if et == "pre_tool":
        return f"[{ts}] [tool] {_format_tool_call(ev)}"
    if et == "post_tool":
        bytes_str = human_bytes(ev.get("result_bytes", 0))
        return f"[{ts}]   ↳ result: {bytes_str}"
    if et == "agent_response":
        text = truncate(ev.get("agent_response_text") or "", DEFAULT_TEXT_RESPONSE_LIMIT)
        reason = ev.get("stop_reason")
        suffix = f" ({reason})" if reason else ""
        return f"[{ts}] [agent]{suffix} {text}"
    if et == "session_end":
        return f"[{ts}] [session_end]"
    return None


def _format_tool_call(ev):
    name = ev.get("tool_name") or "?"
    if name == "Bash":
        cmd = ev.get("command") or (ev.get("tool_input") or {}).get("command") or ""
        cmd = truncate(cmd, 120)
        return f"{name} `{cmd}`"
    paths = ev.get("paths") or []
    if paths:
        if len(paths) == 1:
            return f"{name} {paths[0]}"
        return f"{name} {paths[0]} (+{len(paths) - 1} more)"
    tinp = ev.get("tool_input") or {}
    # Glob / Grep pattern
    pattern = tinp.get("pattern")
    if pattern:
        return f"{name} pattern={pattern!r}"
    return name


# --------- json ----------


def _render_json(session_id, metadata, events, stream, *, hints=None):
    payload = {
        "session_id": session_id,
        "metadata": metadata,
        "events": events,
    }
    if hints:
        payload["anomaly_hints"] = hints
    json.dump(payload, stream, ensure_ascii=False, indent=2)
    stream.write("\n")


# --------- markdown ----------


def _render_markdown(session_id, metadata, events, stream, *, hints=None):
    stream.write(f"# Session {session_id}\n\n")
    if metadata:
        stream.write("| field | value |\n")
        stream.write("|---|---|\n")
        for key in (
            "ts_start",
            "ts_end",
            "engine",
            "cwd",
            "tool_calls_total",
            "user_prompts_count",
            "agent_responses_count",
            "unique_files_read",
            "total_bytes_read",
        ):
            if key in metadata and metadata[key] is not None:
                value = metadata[key]
                if key == "total_bytes_read":
                    value = human_bytes(value)
                stream.write(f"| {key} | {value} |\n")
        stream.write("\n")

    stream.write("## Timeline\n\n")
    for ev in events:
        line = _format_event_line(ev)
        if line:
            stream.write(f"- `{line}` <!-- event_type={ev.get('event_type')} -->\n")
    if not events:
        stream.write("_(no events captured)_\n")

    if hints:
        stream.write("\n## Anomaly hints\n\n")
        for h in hints:
            sev = h.get("severity", "info").upper()
            ts = short_time(h.get("ts")) if h.get("ts") else "--:--:--"
            stream.write(f"- **[{sev}]** `[{ts}]` `{h.get('pattern')}`: {h.get('message')}\n")
