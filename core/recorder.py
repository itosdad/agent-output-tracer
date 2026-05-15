"""Session recorder: append events to JSONL + maintain per-session metadata.

This module is the third leg of the capture pipeline:

    stdin JSON → adapter.normalize_event() → recorder.append_event()
                                                     │
                                                     ├─ events.jsonl  (append-only)
                                                     └─ metadata.json (rewritten)

3.9-compat (loaded by hook scripts running under the user's `python3`).

Failure model: `append_event` raises `RecorderError` for configuration
problems (missing data dir, malformed session_id). Hook scripts swallow
these — the agent must never be blocked by an observation-only plugin.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.path_utils import (
    SESSIONS_SUBDIR,
    is_safe_session_id,
    resolve_data_dir,
)
from core.redactor import redact_event

METADATA_FILENAME = "metadata.json"
EVENTS_FILENAME = "events.jsonl"
METADATA_SCHEMA_VERSION = 1


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

    Args:
        event: normalized event dict (DESIGN §3.3 / §5.1).
        data_dir: explicit data dir; falls back to CLAUDE_PLUGIN_DATA.
        redact: when True (default), apply `core.redactor.redact_event`
            before writing. Counter metadata is computed against the
            redacted shape, so counts stay consistent with what's on
            disk.
        extra_redact_patterns: additional regex strings to add on top of
            the default secret patterns.

    Raises:
        RecorderError: missing session_id, unsafe session_id, missing
            data dir.
    """
    if not isinstance(event, dict):
        raise RecorderError("event must be a dict")
    session_id = event.get("session_id")
    if not session_id:
        raise RecorderError("event missing session_id")

    sdir = session_dir(session_id, data_dir=data_dir)
    sdir.mkdir(parents=True, exist_ok=True)

    to_write = redact_event(event, patterns=extra_redact_patterns) if redact else event

    events_file = sdir / EVENTS_FILENAME
    with events_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(to_write, ensure_ascii=False) + "\n")

    _update_metadata(sdir, to_write)


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
    return {
        "v": METADATA_SCHEMA_VERSION,
        "session_id": event["session_id"],
        "engine": event.get("engine"),
        "ts_start": ts,
        "ts_end": ts,
        "cwd": event.get("cwd"),
        "tool_calls_total": _initial_tool_call_count(event),
        "user_prompts_count": 1 if event.get("event_type") == "user_prompt" else 0,
        "agent_responses_count": (1 if event.get("event_type") == "agent_response" else 0),
        "unique_files_read": _initial_unique_files(event),
        "_unique_files_seen": _initial_unique_files_list(event),
        "total_bytes_read": _initial_bytes(event),
        "tags": [],
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


def _merge_event_into_metadata(meta: dict, event: dict) -> None:
    # ts_start = min, ts_end = max (lexicographic on ISO 8601 with the same
    # tz offset is correct; cross-tz comparison would need parsing, but the
    # plugin generates ts internally so the offset is consistent within a
    # session)
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

    # engine: keep first-seen (don't overwrite); cwd: keep first non-null
    if meta.get("engine") is None and event.get("engine") is not None:
        meta["engine"] = event["engine"]
    if meta.get("cwd") is None and event.get("cwd") is not None:
        meta["cwd"] = event["cwd"]

    meta.setdefault("v", METADATA_SCHEMA_VERSION)
    meta.setdefault("session_id", event.get("session_id"))
    meta.setdefault("tags", [])


def _write_metadata_atomic(meta_file: Path, meta: dict) -> None:
    """Write to a temp file and rename to avoid leaving truncated json on
    crash. metadata is small enough that we always rewrite the whole
    file."""
    tmp = meta_file.with_suffix(meta_file.suffix + ".tmp")
    tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(meta_file)
