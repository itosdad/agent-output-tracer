"""`aot stats --session SPEC` — DESIGN_FORENSIC_UX §7.5.

Session-level forensic statistics (NOT cost/billing — that's a sidecar
concern). Pulls from metadata.json where possible and re-walks events
for tool_mix.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from typing import IO

from core.session_io import load_events, load_metadata


def stats(
    session_id: str,
    *,
    data_dir=None,
    fmt: str = "text",
    stream: IO[str] | None = None,
) -> dict:
    if stream is None:
        stream = sys.stdout

    meta = load_metadata(session_id, data_dir=data_dir) or {}
    events = load_events(session_id, data_dir=data_dir)

    tool_mix: Counter = Counter()
    for ev in events:
        if ev.get("event_type") == "pre_tool":
            tool_mix[ev.get("tool_name") or "?"] += 1

    result = {
        "$schema": "aot/stats/v1",
        "session_id": session_id,
        "events_total": len(events),
        "tool_mix": dict(tool_mix),
        "unique_paths_read": int(meta.get("unique_files_read", 0)),
        "total_bytes_read": int(meta.get("total_bytes_read", 0)),
        "user_prompts": int(meta.get("user_prompts_count", 0)),
        "agent_responses": int(meta.get("agent_responses_count", 0)),
        "anomaly_counters": meta.get("anomaly_counters", {}),
        "tokens_total": meta.get("tokens_total", {}),
        "ts_start": meta.get("ts_start"),
        "ts_end": meta.get("ts_end"),
        "engine": meta.get("engine"),
        "engine_version": meta.get("engine_version"),
    }

    if fmt == "json":
        stream.write(json.dumps(result, ensure_ascii=False, indent=2))
        stream.write("\n")
    else:
        _render_text(result, stream)
    return result


def _render_text(result, stream):
    stream.write(f"Session: {result['session_id']}\n")
    stream.write(f"  engine: {result['engine'] or '?'} ({result['engine_version'] or '?'})\n")
    stream.write(f"  span: {result['ts_start']} → {result['ts_end']}\n")
    stream.write(f"  events: {result['events_total']}\n")
    stream.write(
        f"  prompts={result['user_prompts']}, "
        f"responses={result['agent_responses']}, "
        f"unique reads={result['unique_paths_read']}, "
        f"bytes={result['total_bytes_read']}\n"
    )
    tokens = result["tokens_total"] or {}
    if any(tokens.values()):
        stream.write(
            f"  tokens: input={tokens.get('input', 0)} "
            f"output={tokens.get('output', 0)} "
            f"cache_read={tokens.get('cache_read', 0)} "
            f"cache_creation={tokens.get('cache_creation', 0)}\n"
        )
    if result["tool_mix"]:
        stream.write("  tool mix:\n")
        for tool, n in sorted(result["tool_mix"].items(), key=lambda x: -x[1]):
            stream.write(f"    {tool}: {n}\n")
    anom = result["anomaly_counters"] or {}
    if any(anom.values()):
        stream.write("  anomaly counters:\n")
        for k, v in anom.items():
            if v:
                stream.write(f"    {k}: {v}\n")
