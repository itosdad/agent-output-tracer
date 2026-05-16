"""Read-side complement to recorder.py.

Loads events.jsonl and metadata.json back into memory for the query
surface (replay / trace / why / grep / ...). The recorder is write-only;
this module is read-only.

Lives in `core/` so it stays 3.9-compatible and can also be used from
the hook process if needed (e.g. for self-tests).
"""

from __future__ import annotations

import json

from core.path_utils import (
    SESSIONS_SUBDIR,
    is_safe_session_id,
    resolve_data_dir,
)
from core.recorder import EVENTS_FILENAME, METADATA_FILENAME


class SessionNotFoundError(LookupError):
    """Raised when the requested session does not exist on disk."""


def _sessions_root(data_dir):
    base = resolve_data_dir(data_dir)
    if base is None:
        raise SessionNotFoundError("CLAUDE_PLUGIN_DATA not set and no data_dir parameter provided")
    return base / SESSIONS_SUBDIR


def session_dir_path(session_id, *, data_dir=None):
    if not is_safe_session_id(session_id):
        raise SessionNotFoundError(f"unsafe session_id: {session_id!r}")
    root = _sessions_root(data_dir)
    sdir = root / session_id
    if not sdir.is_dir():
        raise SessionNotFoundError(f"no session {session_id!r} under {root}")
    return sdir


def load_events(session_id, *, data_dir=None):
    """Load every event from the session's events.jsonl in append order.

    Corrupt JSON lines are silently skipped (rather than raising). The
    file is opened once and consumed sequentially.
    """
    sdir = session_dir_path(session_id, data_dir=data_dir)
    events_file = sdir / EVENTS_FILENAME
    if not events_file.exists():
        return []
    out = []
    with events_file.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                out.append(json.loads(stripped))
            except (ValueError, TypeError):
                continue
    return out


def load_metadata(session_id, *, data_dir=None):
    """Load metadata.json for the session. Returns None on missing /
    corrupt metadata. Raises SessionNotFoundError if the session dir
    itself does not exist."""
    sdir = session_dir_path(session_id, data_dir=data_dir)
    meta_file = sdir / METADATA_FILENAME
    if not meta_file.exists():
        return None
    try:
        return json.loads(meta_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def list_sessions(*, data_dir=None):
    """List every session under `data_dir/sessions/`, newest first.

    Each entry is the metadata.json dict if present, otherwise a small
    stub `{session_id, ts_end: None}`. Returns an empty list when the
    sessions root does not yet exist.
    """
    try:
        root = _sessions_root(data_dir)
    except SessionNotFoundError:
        return []
    if not root.is_dir():
        return []
    out = []
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        sid = entry.name
        if not is_safe_session_id(sid):
            continue
        meta_file = entry / METADATA_FILENAME
        meta = None
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                meta = None
        if meta is None:
            meta = {"session_id": sid, "ts_end": None, "ts_start": None}
        else:
            meta.setdefault("session_id", sid)
        out.append(meta)

    # Sort by ts_end desc, falling back to ts_start, then session_id.
    def _key(m):
        return (
            m.get("ts_end") or m.get("ts_start") or "",
            m.get("session_id") or "",
        )

    out.sort(key=_key, reverse=True)
    return out
