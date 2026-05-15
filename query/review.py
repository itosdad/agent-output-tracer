"""`aot review --since DATE` — DESIGN_FORENSIC_UX §7.6.

User-explicit cross-session summary. Reads (or rebuilds) the global
index and reports: session count, per-engine breakdown, aggregated
anomaly counters, hallucination_candidate list, top paths, sessions
that carry notes.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from typing import IO

from core.global_index import build_or_refresh, load_global_index


def review(
    *,
    since: str | None = None,
    until: str | None = None,
    data_dir=None,
    fmt: str = "text",
    rebuild: bool = False,
    stream: IO[str] | None = None,
) -> dict:
    if stream is None:
        stream = sys.stdout

    if rebuild or load_global_index(data_dir=data_dir) is None:
        index = build_or_refresh(data_dir=data_dir)
    else:
        index = load_global_index(data_dir=data_dir)
        # Always do a fresh walk so the report reflects current state;
        # the "is it expensive?" optimisation is for later.
        index = build_or_refresh(data_dir=data_dir)

    sessions = index.get("sessions", [])
    if since:
        sessions = [s for s in sessions if (s.get("ts_end") or "") >= since]
    if until:
        sessions = [s for s in sessions if (s.get("ts_end") or "") <= until]

    engines = Counter(s.get("engine") or "?" for s in sessions)
    anomaly_total: Counter = Counter()
    for s in sessions:
        for k, v in (s.get("anomaly_counters") or {}).items():
            anomaly_total[k] += int(v or 0)
    path_count = Counter()
    for p, refs in (index.get("path_cross_index") or {}).items():
        path_count[p] = len({r["session_id"] for r in refs})

    result = {
        "$schema": "aot/review/v1",
        "since": since,
        "until": until,
        "sessions_count": len(sessions),
        "engines": dict(engines),
        "anomaly_counters_total": dict(anomaly_total),
        "top_paths": path_count.most_common(10),
        "sessions": sessions,
    }

    if fmt == "json":
        stream.write(json.dumps(result, ensure_ascii=False, indent=2))
        stream.write("\n")
    else:
        _render_text(result, stream)
    return result


def _render_text(result, stream):
    stream.write("Cross-session review\n")
    if result["since"] or result["until"]:
        stream.write(f"  window: since={result['since']} until={result['until']}\n")
    stream.write(f"  sessions: {result['sessions_count']}\n")
    if result["engines"]:
        stream.write("  engines:\n")
        for e, n in result["engines"].items():
            stream.write(f"    {e}: {n}\n")
    if any(result["anomaly_counters_total"].values()):
        stream.write("  anomaly counters (aggregate):\n")
        for k, v in result["anomaly_counters_total"].items():
            if v:
                stream.write(f"    {k}: {v}\n")
    if result["top_paths"]:
        stream.write("  top paths (by session count):\n")
        for path, n in result["top_paths"]:
            stream.write(f"    {n}x  {path}\n")
