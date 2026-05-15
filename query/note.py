"""`aot note` — human-attached annotation on a session.

DESIGN_FORENSIC_UX §7.3. notes are append-only at
`<session_dir>/notes.jsonl`; one line per note:

  {"id": "n-1", "ts": ISO, "by": user, "tag": str, "body": str,
   "links": {"event_idx": int?, "finding_idx": int?}}

Tags (default vocabulary, but freeform allowed via `custom:<...>`):
  root-cause / observation / question / false-positive / followup
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import IO

from core.recorder import session_dir

NOTES_FILENAME = "notes.jsonl"
DEFAULT_TAGS = {"root-cause", "observation", "question", "false-positive", "followup"}


class NoteError(RuntimeError):
    pass


def _notes_path(session_id: str, *, data_dir=None) -> Path:
    return session_dir(session_id, data_dir=data_dir) / NOTES_FILENAME


def _load_notes(session_id: str, *, data_dir=None) -> list[dict]:
    p = _notes_path(session_id, data_dir=data_dir)
    if not p.exists():
        return []
    out: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _validate_tag(tag: str) -> None:
    if tag in DEFAULT_TAGS:
        return
    if tag.startswith("custom:") and len(tag) > len("custom:"):
        return
    raise NoteError(
        f"unknown tag {tag!r}. Use one of {sorted(DEFAULT_TAGS)} or 'custom:<freeform>'"
    )


def note_add(
    session_id: str,
    body: str,
    *,
    tag: str = "observation",
    event_idx: int | None = None,
    finding_idx: int | None = None,
    by: str | None = None,
    data_dir=None,
    stream: IO[str] | None = None,
) -> dict:
    """Append a note to the session. `by` defaults to $USER / 'anon'."""
    _validate_tag(tag)
    if stream is None:
        stream = sys.stdout

    existing = _load_notes(session_id, data_dir=data_dir)
    note = {
        "id": f"n-{len(existing) + 1}",
        "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
        "by": by or os.environ.get("USER") or "anon",
        "tag": tag,
        "body": body,
        "links": {
            "event_idx": event_idx,
            "finding_idx": finding_idx,
        },
    }

    p = _notes_path(session_id, data_dir=data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(note, ensure_ascii=False) + "\n")

    _bump_metadata_notes_count(session_id, data_dir=data_dir)
    stream.write(f"note {note['id']} added (tag={tag}).\n")
    return note


def note_list(
    session_id: str,
    *,
    tag: str | None = None,
    data_dir=None,
    stream: IO[str] | None = None,
) -> list[dict]:
    if stream is None:
        stream = sys.stdout
    notes = _load_notes(session_id, data_dir=data_dir)
    if tag is not None:
        notes = [n for n in notes if n.get("tag") == tag]
    if not notes:
        stream.write("(no notes)\n")
    else:
        for n in notes:
            links = n.get("links") or {}
            link_str = ""
            if links.get("event_idx") is not None:
                link_str += f" event={links['event_idx']}"
            if links.get("finding_idx") is not None:
                link_str += f" finding={links['finding_idx']}"
            stream.write(
                f"  {n['id']} [{n['tag']}] {n['ts']} by={n['by']}{link_str}\n"
            )
            stream.write(f"      {n['body']}\n")
    return notes


def note_rm(
    session_id: str,
    note_id: str,
    *,
    data_dir=None,
    stream: IO[str] | None = None,
) -> bool:
    """Remove a note by id. Rewrites notes.jsonl (notes file is small)."""
    if stream is None:
        stream = sys.stdout
    notes = _load_notes(session_id, data_dir=data_dir)
    remaining = [n for n in notes if n.get("id") != note_id]
    if len(remaining) == len(notes):
        stream.write(f"note {note_id!r} not found.\n")
        return False
    p = _notes_path(session_id, data_dir=data_dir)
    with p.open("w", encoding="utf-8") as f:
        for n in remaining:
            f.write(json.dumps(n, ensure_ascii=False) + "\n")
    _bump_metadata_notes_count(session_id, data_dir=data_dir, override=len(remaining))
    stream.write(f"note {note_id} removed.\n")
    return True


# ----- metadata sync -----


def _bump_metadata_notes_count(
    session_id: str,
    *,
    data_dir=None,
    override: int | None = None,
) -> None:
    sdir = session_dir(session_id, data_dir=data_dir)
    meta_file = sdir / "metadata.json"
    if not meta_file.exists():
        return
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if override is not None:
        meta["notes_count"] = override
    else:
        meta["notes_count"] = int(meta.get("notes_count", 0)) + 1
    tmp = meta_file.with_suffix(meta_file.suffix + ".tmp")
    tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(meta_file)
