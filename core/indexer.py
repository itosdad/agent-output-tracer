"""Per-session search index (DESIGN_FORENSIC_UX §6.4).

Builds `<session>/index.json` lazily — touch only when a query that
needs it asks. Contents (schema v2):

  - `v`: 2
  - `bigram_inverted`: 2-char bigram → list of event indexes that
    mention it anywhere (case-insensitive). Used by future grep
    prefix acceleration; harmless if unused.
  - `content_hash_to_events`: SHA256(tool_response) → list of event
    indexes. Underpins `trace --by-sha`.
  - `path_first_seen`: path → first event index that touched it.
  - `phrase_to_first_agent_event`: 3..5-gram → first agent_response
    event index that contains it (case-insensitive). Underpins
    `trace --output` acceleration.

This is a *forensic-time* index, not a runtime structure: it is
re-buildable from events.jsonl alone, so we don't fret about durability
or transactional correctness. If anything looks stale, delete the file
and the next query rebuilds it.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Iterable

from core.path_utils import (
    SESSIONS_SUBDIR,
    is_safe_session_id,
    resolve_data_dir,
)
from core.session_io import load_events

INDEX_FILENAME = "index.json"
INDEX_SCHEMA_VERSION = 2

# Phrase n-gram bounds for phrase_to_first_agent_event.
PHRASE_MIN = 3
PHRASE_MAX = 5

# Bigram regex: alphanumeric pairs only — punctuation explodes the index.
_BIGRAM_RE = re.compile(r"(?=([A-Za-z0-9]{2}))")
_WORD_RE = re.compile(r"[A-Za-z0-9_./-]{2,}")


def index_path(session_id: str, *, data_dir=None) -> Path:
    if not is_safe_session_id(session_id):
        raise ValueError(f"unsafe session_id: {session_id!r}")
    base = resolve_data_dir(data_dir)
    if base is None:
        raise RuntimeError("data dir not resolvable")
    return base / SESSIONS_SUBDIR / session_id / INDEX_FILENAME


def load_index(session_id: str, *, data_dir=None) -> dict | None:
    p = index_path(session_id, data_dir=data_dir)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def build_index(session_id: str, *, data_dir=None) -> dict:
    """Walk events.jsonl and write a fresh `index.json`."""
    events = load_events(session_id, data_dir=data_dir)

    bigram_inverted: dict[str, list[int]] = {}
    content_hash_to_events: dict[str, list[int]] = {}
    path_first_seen: dict[str, int] = {}
    phrase_to_first_agent_event: dict[str, int] = {}

    for i, ev in enumerate(events):
        for token in _gather_strings(ev):
            for bg in _bigrams(token):
                _append_unique(bigram_inverted, bg, i)

        if ev.get("event_type") == "post_tool":
            sha = ev.get("response_sha256")
            if not sha:
                resp = ev.get("tool_response")
                if isinstance(resp, str) and resp:
                    sha = hashlib.sha256(resp.encode("utf-8")).hexdigest()
            if sha:
                content_hash_to_events.setdefault(sha, []).append(i)

        for p in ev.get("paths") or []:
            if isinstance(p, str) and p not in path_first_seen:
                path_first_seen[p] = i

        if ev.get("event_type") == "agent_response":
            text = ev.get("agent_response_text") or ""
            for phrase in _phrase_grams(text):
                if phrase not in phrase_to_first_agent_event:
                    phrase_to_first_agent_event[phrase] = i

    out = {
        "v": INDEX_SCHEMA_VERSION,
        "session_id": session_id,
        "bigram_inverted": bigram_inverted,
        "content_hash_to_events": content_hash_to_events,
        "path_first_seen": path_first_seen,
        "phrase_to_first_agent_event": phrase_to_first_agent_event,
    }
    p = index_path(session_id, data_dir=data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def get_or_build(session_id: str, *, data_dir=None) -> dict:
    cached = load_index(session_id, data_dir=data_dir)
    if cached is not None and cached.get("v") == INDEX_SCHEMA_VERSION:
        return cached
    return build_index(session_id, data_dir=data_dir)


def _gather_strings(event: dict) -> Iterable[str]:
    """Pull every searchable string out of an event for bigram indexing."""
    for key in ("user_prompt_text", "agent_response_text", "tool_response", "command", "tool_name"):
        v = event.get(key)
        if isinstance(v, str) and v:
            yield v
    for p in event.get("paths") or []:
        if isinstance(p, str):
            yield p


def _bigrams(text: str) -> Iterable[str]:
    """Yield distinct lowercase 2-char tokens for indexing."""
    text = text.lower()
    seen: set[str] = set()
    for m in _BIGRAM_RE.finditer(text):
        bg = m.group(1)
        if bg not in seen:
            seen.add(bg)
            yield bg


def _phrase_grams(text: str) -> Iterable[str]:
    """Yield distinct lowercase word n-grams (PHRASE_MIN..PHRASE_MAX)."""
    words = [w.lower() for w in _WORD_RE.findall(text)]
    seen: set[str] = set()
    for n in range(PHRASE_MIN, PHRASE_MAX + 1):
        for i in range(len(words) - n + 1):
            gram = " ".join(words[i : i + n])
            if gram not in seen:
                seen.add(gram)
                yield gram


def _append_unique(d: dict[str, list[int]], key: str, value: int) -> None:
    bucket = d.setdefault(key, [])
    if not bucket or bucket[-1] != value:
        bucket.append(value)


__all__ = [
    "INDEX_FILENAME",
    "INDEX_SCHEMA_VERSION",
    "PHRASE_MIN",
    "PHRASE_MAX",
    "build_index",
    "get_or_build",
    "index_path",
    "load_index",
]
