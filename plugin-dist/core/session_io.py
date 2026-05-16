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
    itself does not exist.

    `metadata.engine` is patched in-memory when it disagrees with the
    transcript-path hint (same correction as `list_sessions`)."""
    sdir = session_dir_path(session_id, data_dir=data_dir)
    meta_file = sdir / METADATA_FILENAME
    if not meta_file.exists():
        return None
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(meta, dict):
        hint = _engine_hint_from_first_event(sdir)
        if hint is not None and meta.get("engine") != hint:
            meta["engine"] = hint
    return meta


_ENGINE_FROM_TRANSCRIPT = (
    (".codex/", "codex"),
    (".codex\\", "codex"),
    (".claude/", "claude-code"),
    (".claude\\", "claude-code"),
)


def _engine_hint_from_first_event(session_dir):
    """Peek at the first event of `events.jsonl` and derive the engine
    from `raw_event.transcript_path`. Returns "codex" / "claude-code",
    or None when the file is missing / malformed / has no usable hint.

    This is a cheap O(1) read used to repair stale `metadata.engine`
    values written by older versions of the recorder whose engine
    detector misclassified the session (e.g. Codex events tagged
    `engine: claude-code` prior to v0.16.7). `transcript_path` is the
    only field whose value is forced by each engine's on-disk layout,
    so it survives runtime detector bugs.
    """
    events_file = session_dir / EVENTS_FILENAME
    if not events_file.exists():
        return None
    try:
        with events_file.open("r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    ev = json.loads(stripped)
                except (ValueError, TypeError):
                    return None
                raw = ev.get("raw_event") or {}
                tp = raw.get("transcript_path") if isinstance(raw, dict) else None
                if not isinstance(tp, str) or not tp:
                    return None
                lowered = tp.lower()
                for needle, engine in _ENGINE_FROM_TRANSCRIPT:
                    if needle in lowered:
                        return engine
                return None
    except OSError:
        return None
    return None


def list_sessions(*, data_dir=None):
    """List every session under `data_dir/sessions/`, newest first.

    Each entry is the metadata.json dict if present, otherwise a small
    stub `{session_id, ts_end: None}`. Returns an empty list when the
    sessions root does not yet exist.

    `metadata.engine` is patched in-memory when it disagrees with the
    transcript-path-derived hint from the session's first event. This
    repairs sessions written by pre-v0.16.7 recorders that misdetected
    Codex events as `claude-code` (the on-disk metadata stays
    untouched — the override happens at read time only).
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

        hint = _engine_hint_from_first_event(entry)
        if hint is not None and meta.get("engine") != hint:
            meta["engine"] = hint

        out.append(meta)

    # Sort by ts_end desc, falling back to ts_start, then session_id.
    def _key(m):
        return (
            m.get("ts_end") or m.get("ts_start") or "",
            m.get("session_id") or "",
        )

    out.sort(key=_key, reverse=True)
    return out
