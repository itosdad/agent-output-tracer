"""Session retention / GC — DESIGN §9.4.

Two stages:
- after `archive_days` (default 30): strip content fields (tool_response,
  agent_response_text, user_prompt_text, command) from every event,
  preserve structure + metadata + paths for forensic skeleton
- after `delete_days` (default 365): remove the session dir entirely

3.11+ allowed (this module is only invoked from the CLI surface).
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core.path_utils import (
    SESSIONS_SUBDIR,
    is_safe_session_id,
    resolve_data_dir,
)
from core.recorder import EVENTS_FILENAME, METADATA_FILENAME

DEFAULT_ARCHIVE_DAYS = 30
DEFAULT_DELETE_DAYS = 365

# Fields whose content we strip during archive
_STRIP_FIELDS = (
    "user_prompt_text",
    "agent_response_text",
    "tool_response",
    "command",
)


def run_gc(
    *,
    data_dir=None,
    now: datetime | None = None,
    archive_days: int = DEFAULT_ARCHIVE_DAYS,
    delete_days: int = DEFAULT_DELETE_DAYS,
    dry_run: bool = False,
) -> dict[str, Any]:
    if now is None:
        now = datetime.now(timezone.utc)
    archive_cutoff = now - timedelta(days=archive_days)
    delete_cutoff = now - timedelta(days=delete_days)

    base = resolve_data_dir(data_dir)
    if base is None:
        return _empty_summary()
    sessions_root = base / SESSIONS_SUBDIR
    if not sessions_root.is_dir():
        return _empty_summary()

    stripped: list[str] = []
    deleted: list[str] = []
    untouched: list[str] = []
    skipped: list[str] = []

    for entry in sorted(sessions_root.iterdir()):
        if not entry.is_dir():
            continue
        sid = entry.name
        if not is_safe_session_id(sid):
            continue
        meta = _load_metadata(entry / METADATA_FILENAME)
        if meta is None:
            skipped.append(sid)
            continue
        ts_end = _parse_iso(meta.get("ts_end") or meta.get("ts_start") or "")
        if ts_end is None:
            skipped.append(sid)
            continue
        if ts_end < delete_cutoff:
            deleted.append(sid)
            if not dry_run:
                shutil.rmtree(entry, ignore_errors=True)
            continue
        if ts_end < archive_cutoff and not meta.get("stripped"):
            stripped.append(sid)
            if not dry_run:
                _strip_session(entry, meta)
            continue
        untouched.append(sid)

    return {
        "stripped": stripped,
        "deleted": deleted,
        "untouched": untouched,
        "skipped": skipped,
        "stripped_count": len(stripped),
        "deleted_count": len(deleted),
        "untouched_count": len(untouched),
        "skipped_count": len(skipped),
        "dry_run": dry_run,
    }


def _empty_summary():
    return {
        "stripped": [],
        "deleted": [],
        "untouched": [],
        "skipped": [],
        "stripped_count": 0,
        "deleted_count": 0,
        "untouched_count": 0,
        "skipped_count": 0,
        "dry_run": False,
    }


def _load_metadata(meta_path: Path):
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _parse_iso(ts):
    if not isinstance(ts, str) or not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def _strip_session(session_dir: Path, meta: dict) -> None:
    """Rewrite events.jsonl with content fields nulled out, mark metadata."""
    events_file = session_dir / EVENTS_FILENAME
    if events_file.exists():
        lines_out: list[str] = []
        with events_file.open("r", encoding="utf-8") as f:
            for raw_line in f:
                stripped = raw_line.strip()
                if not stripped:
                    continue
                try:
                    ev = json.loads(stripped)
                except ValueError:
                    continue
                for field in _STRIP_FIELDS:
                    if ev.get(field) is not None:
                        ev[field] = None
                if isinstance(ev.get("raw_event"), dict):
                    ev["raw_event"] = {}
                if ev.get("result_bytes"):
                    # Keep the byte count; it's an aggregate
                    pass
                lines_out.append(json.dumps(ev, ensure_ascii=False))
        tmp = events_file.with_suffix(events_file.suffix + ".tmp")
        tmp.write_text("\n".join(lines_out) + "\n" if lines_out else "", encoding="utf-8")
        tmp.replace(events_file)

    meta["stripped"] = True
    meta_file = session_dir / METADATA_FILENAME
    tmp = meta_file.with_suffix(meta_file.suffix + ".tmp")
    tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(meta_file)
