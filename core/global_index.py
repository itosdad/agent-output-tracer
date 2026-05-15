"""Cross-session global index (DESIGN_FORENSIC_UX §6.5 / §8.4).

Maintained at `<data_dir>/global_index.json`. Built incrementally:
each `aot review` / `find --since` / `trace --by-sha --since` call
folds in any sessions that have changed since `built_at`.

retention_days defaults to 30; older sessions are excluded from the
aggregated indexes (but their per-session files are untouched —
that's `aot gc`'s job).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.path_utils import resolve_data_dir
from core.session_io import list_sessions, load_events

GLOBAL_INDEX_FILENAME = "global_index.json"
GLOBAL_INDEX_SCHEMA_VERSION = 1
DEFAULT_RETENTION_DAYS = 30


def _path(*, data_dir=None) -> Path:
    base = resolve_data_dir(data_dir)
    if base is None:
        raise RuntimeError("data dir not resolvable")
    return base / GLOBAL_INDEX_FILENAME


def load_global_index(*, data_dir=None) -> dict | None:
    p = _path(data_dir=data_dir)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def build_or_refresh(
    *,
    data_dir=None,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> dict:
    """Walk every recent session and rebuild the cross-session index.

    The "incremental" promise of the design is mostly a runtime perf
    nicety; the on-disk format is fully rewritten each call so
    correctness is straightforward.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat(
        timespec="milliseconds"
    )

    sessions_summary: list[dict] = []
    phrase_cross: dict[str, list[dict]] = {}
    path_cross: dict[str, list[dict]] = {}
    sha_cross: dict[str, list[dict]] = {}

    for meta in list_sessions(data_dir=data_dir):
        ts_end = meta.get("ts_end")
        if ts_end and ts_end < cutoff:
            continue
        sid = meta.get("session_id")
        if not sid:
            continue
        sessions_summary.append(
            {
                "session_id": sid,
                "engine": meta.get("engine"),
                "ts_start": meta.get("ts_start"),
                "ts_end": ts_end,
                "anomaly_counters": meta.get("anomaly_counters") or {},
                "notes_tags": [],  # populated below
            }
        )
        try:
            events = load_events(sid, data_dir=data_dir)
        except Exception:
            continue
        for i, ev in enumerate(events):
            for p in ev.get("paths") or []:
                if isinstance(p, str):
                    path_cross.setdefault(p, []).append(
                        {"session_id": sid, "event_idx": i}
                    )
            if ev.get("event_type") == "post_tool":
                sha = ev.get("response_sha256")
                if not sha:
                    resp = ev.get("tool_response")
                    if isinstance(resp, str) and resp:
                        sha = hashlib.sha256(resp.encode("utf-8")).hexdigest()
                if sha:
                    sha_cross.setdefault(sha, []).append(
                        {"session_id": sid, "event_idx": i, "ts": ev.get("ts")}
                    )
            if ev.get("event_type") == "agent_response":
                text = (ev.get("agent_response_text") or "").lower()
                # cheap phrase capture: first 50 lowercase words → 5-grams
                words = text.split()
                for n in (3, 4, 5):
                    for k in range(len(words) - n + 1):
                        gram = " ".join(words[k : k + n])
                        if len(gram) < 8:
                            continue
                        phrase_cross.setdefault(gram, []).append(
                            {"session_id": sid, "event_idx": i}
                        )

    index = {
        "v": GLOBAL_INDEX_SCHEMA_VERSION,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "retention_days": retention_days,
        "sessions": sessions_summary,
        "phrase_cross_index": phrase_cross,
        "path_cross_index": path_cross,
        "sha_cross_index": sha_cross,
    }
    p = _path(data_dir=data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    return index
