"""Session recorder: append events to JSONL + maintain per-session metadata.

This module is the third leg of the capture pipeline:

    stdin JSON → adapter.normalize_event() → recorder.append_event()
                                                     │
                                                     ├─ events.jsonl  (append-only, schema v2)
                                                     └─ metadata.json (rewritten, schema v2)

Schema v2 (DESIGN_FORENSIC_UX §6) is additive: v1 readers ignore the
new fields; v2 readers tolerate v1 events with field defaults.

3.9-compat (loaded by hook scripts running under the user's `python3`).

Failure model: `append_event` raises `RecorderError` for configuration
problems (missing data dir, malformed session_id). Hook scripts swallow
these — the agent must never be blocked by an observation-only plugin.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path

from core.path_utils import (
    SESSIONS_SUBDIR,
    is_safe_session_id,
    resolve_data_dir,
)
from core.redactor import redact_event

METADATA_FILENAME = "metadata.json"
EVENTS_FILENAME = "events.jsonl"
EVENT_SCHEMA_VERSION = 2
METADATA_SCHEMA_VERSION = 2


class RecorderError(RuntimeError):
    """Raised when the recorder cannot fulfil a request.

    Hook scripts catch this and exit 0 silently.
    """


def session_dir(session_id, *, data_dir=None):
    """Return `<data_dir>/sessions/<session_id>` as a Path.

    Raises RecorderError if session_id is unsafe or data_dir cannot be
    resolved.
    """
    if not is_safe_session_id(session_id):
        raise RecorderError(f"unsafe session_id: {session_id!r}")
    base = resolve_data_dir(data_dir)
    if base is None:
        raise RecorderError("CLAUDE_PLUGIN_DATA not set and no data_dir parameter provided")
    return base / SESSIONS_SUBDIR / session_id


def append_event(event, *, data_dir=None, redact=True, extra_redact_patterns=None):
    """Append one normalized event to its session log and update metadata.

    Side effects beyond write:
      - Stamps `v=2` on every event so downstream readers know the
        schema generation.
      - Generates a fresh `correlation_id` (UUID) anchored on user_prompt
        events; reuses the active id for subsequent events until the next
        user_prompt (or until the session reset).
      - Computes `response_sha256` / `response_size_bytes` for post_tool
        events whose tool_response is a non-empty string.
      - Measures `hook_self_ms` (wallclock budget the recorder itself
        consumed for this event).
    """
    if not isinstance(event, dict):
        raise RecorderError("event must be a dict")
    session_id = event.get("session_id")
    if not session_id:
        raise RecorderError("event missing session_id")

    t0 = time.monotonic()

    sdir = session_dir(session_id, data_dir=data_dir)
    sdir.mkdir(parents=True, exist_ok=True)

    enriched = _enrich_v2(event, sdir)
    to_write = redact_event(enriched, patterns=extra_redact_patterns) if redact else enriched

    # hook_self_ms is best-effort — set after redaction so we capture the
    # whole recorder pipeline budget without doubling the dict write.
    to_write["hook_self_ms"] = int((time.monotonic() - t0) * 1000)

    events_file = sdir / EVENTS_FILENAME
    with events_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(to_write, ensure_ascii=False) + "\n")

    _update_metadata(sdir, to_write)


# ----------- v2 enrichment -----------


def _enrich_v2(event: dict, sdir: Path) -> dict:
    """Stamp the event with the schema-v2 fields the recorder owns.

    The adapter has already populated engine-supplied fields
    (`tokens` / `turn_id` / `engine_version` / `permission_mode` / etc.);
    here we add the AOT-generated bits and any derived hashes.
    """
    out = dict(event)
    out["v"] = EVENT_SCHEMA_VERSION

    out["correlation_id"] = _next_correlation_id(sdir, event)

    if event.get("event_type") == "post_tool":
        resp = event.get("tool_response")
        if isinstance(resp, str) and resp:
            out["response_sha256"] = hashlib.sha256(resp.encode("utf-8")).hexdigest()
        out["response_size_bytes"] = int(event.get("result_bytes") or 0)

    return out


def _next_correlation_id(sdir: Path, event: dict) -> str:
    """Return the correlation_id this event should carry.

    - Codex events with a `turn_id` reuse it (engine already partitions).
    - Otherwise: a new UUID is minted on user_prompt and stored in
      `correlation.json`; subsequent events read it back. If the file
      doesn't exist (very first event of a session, not a user_prompt),
      we still mint one so the event isn't naked.
    """
    turn_id = event.get("turn_id")
    if isinstance(turn_id, str) and turn_id:
        return turn_id

    corr_file = sdir / "correlation.json"
    et = event.get("event_type")

    if et == "user_prompt" or not corr_file.exists():
        new_id = uuid.uuid4().hex
        try:
            corr_file.write_text(
                json.dumps({"current": new_id}), encoding="utf-8"
            )
        except OSError:
            pass
        return new_id

    try:
        data = json.loads(corr_file.read_text(encoding="utf-8"))
        current = data.get("current")
        if isinstance(current, str) and current:
            return current
    except (OSError, ValueError):
        pass
    return uuid.uuid4().hex


# ----------- metadata -----------


def _update_metadata(sdir: Path, event: dict) -> None:
    meta_file = sdir / METADATA_FILENAME
    meta = _load_metadata_safely(meta_file)
    if meta is None:
        meta = _new_metadata(event)
    else:
        _merge_event_into_metadata(meta, event)

    _write_metadata_atomic(meta_file, meta)


def _load_metadata_safely(path: Path):
    """Return dict on success, None on missing-or-corrupt."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _new_metadata(event: dict) -> dict:
    ts = event.get("ts")
    cwd = event.get("cwd")
    return {
        "v": METADATA_SCHEMA_VERSION,
        "session_id": event["session_id"],
        "engine": event.get("engine"),
        "engine_version": event.get("engine_version"),
        "ts_start": ts,
        "ts_end": ts,
        "cwd": cwd,
        "cwd_hash": _sha256(cwd) if isinstance(cwd, str) else None,
        "tool_calls_total": _initial_tool_call_count(event),
        "user_prompts_count": 1 if event.get("event_type") == "user_prompt" else 0,
        "agent_responses_count": (1 if event.get("event_type") == "agent_response" else 0),
        "unique_files_read": _initial_unique_files(event),
        "_unique_files_seen": _initial_unique_files_list(event),
        "total_bytes_read": _initial_bytes(event),
        "tags": [],
        "notes_count": 0,
        "findings": [],
        "anomaly_counters": {
            "unmentioned_reads": 0,
            "repeated_reads": 0,
            "hallucination_candidates": 0,
            "glob_burst": 0,
            "routing_thrash": 0,
            "large_read": 0,
        },
        "tokens_total": _initial_tokens(event),
    }


def _initial_tool_call_count(event: dict) -> int:
    return 1 if event.get("event_type") == "pre_tool" else 0


def _initial_unique_files(event: dict) -> int:
    return len(_initial_unique_files_list(event))


def _initial_unique_files_list(event: dict) -> list:
    if event.get("event_type") == "post_tool" and event.get("tool_name") == "Read":
        return sorted({p for p in (event.get("paths") or []) if isinstance(p, str)})
    return []


def _initial_bytes(event: dict) -> int:
    if event.get("event_type") == "post_tool" and event.get("tool_name") == "Read":
        return int(event.get("result_bytes") or 0)
    return 0


def _initial_tokens(event: dict) -> dict:
    tokens = event.get("tokens")
    base = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}
    if isinstance(tokens, dict):
        for k in base:
            v = tokens.get(k)
            if isinstance(v, int):
                base[k] = v
    return base


def _merge_event_into_metadata(meta: dict, event: dict) -> None:
    # Migrate v1 metadata in-place to v2 on first touch.
    if meta.get("v", 1) < METADATA_SCHEMA_VERSION:
        meta.setdefault("notes_count", 0)
        meta.setdefault("findings", [])
        meta.setdefault("anomaly_counters", {
            "unmentioned_reads": 0,
            "repeated_reads": 0,
            "hallucination_candidates": 0,
            "glob_burst": 0,
            "routing_thrash": 0,
            "large_read": 0,
        })
        meta.setdefault("tokens_total", {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0})
        meta.setdefault("engine_version", None)
        cwd = meta.get("cwd")
        if isinstance(cwd, str) and not meta.get("cwd_hash"):
            meta["cwd_hash"] = _sha256(cwd)
        meta["v"] = METADATA_SCHEMA_VERSION

    ts = event.get("ts")
    if ts:
        if not meta.get("ts_start") or ts < meta["ts_start"]:
            meta["ts_start"] = ts
        if not meta.get("ts_end") or ts > meta["ts_end"]:
            meta["ts_end"] = ts

    event_type = event.get("event_type")
    if event_type == "pre_tool":
        meta["tool_calls_total"] = int(meta.get("tool_calls_total", 0)) + 1
    elif event_type == "user_prompt":
        meta["user_prompts_count"] = int(meta.get("user_prompts_count", 0)) + 1
    elif event_type == "agent_response":
        meta["agent_responses_count"] = int(meta.get("agent_responses_count", 0)) + 1
        _accumulate_tokens(meta, event.get("tokens"))
    elif event_type == "post_tool" and event.get("tool_name") == "Read":
        seen = set(meta.get("_unique_files_seen", []))
        for p in event.get("paths") or []:
            if isinstance(p, str):
                seen.add(p)
        meta["_unique_files_seen"] = sorted(seen)
        meta["unique_files_read"] = len(seen)
        meta["total_bytes_read"] = int(meta.get("total_bytes_read", 0)) + int(
            event.get("result_bytes") or 0
        )

    if meta.get("engine") is None and event.get("engine") is not None:
        meta["engine"] = event["engine"]
    if meta.get("engine_version") is None and event.get("engine_version") is not None:
        meta["engine_version"] = event["engine_version"]
    if meta.get("cwd") is None and event.get("cwd") is not None:
        meta["cwd"] = event["cwd"]
        if isinstance(event["cwd"], str) and not meta.get("cwd_hash"):
            meta["cwd_hash"] = _sha256(event["cwd"])

    meta.setdefault("v", METADATA_SCHEMA_VERSION)
    meta.setdefault("session_id", event.get("session_id"))
    meta.setdefault("tags", [])


def _accumulate_tokens(meta: dict, tokens) -> None:
    if not isinstance(tokens, dict):
        return
    total = meta.setdefault(
        "tokens_total",
        {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0},
    )
    for k in ("input", "output", "cache_read", "cache_creation"):
        v = tokens.get(k)
        if isinstance(v, int):
            total[k] = int(total.get(k, 0)) + v


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _write_metadata_atomic(meta_file: Path, meta: dict) -> None:
    """Write to a temp file and rename to avoid leaving truncated json on
    crash. metadata is small enough that we always rewrite the whole
    file."""
    tmp = meta_file.with_suffix(meta_file.suffix + ".tmp")
    tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(meta_file)
