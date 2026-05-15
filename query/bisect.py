"""`aot bisect` — git-bisect-flavoured binary search across a session.

DESIGN_FORENSIC_UX §7.2.

Interactive flow:

  aot bisect start --session SPEC [--from EVENT_IDX] [--to EVENT_IDX]
  aot bisect view             # show the current candidate event
  aot bisect good             # mark candidate as good (= before-the-break)
  aot bisect bad              # mark candidate as bad (= after-the-break)
  aot bisect skip             # candidate is inconclusive
  aot bisect status           # current range + progress
  aot bisect log              # decision history
  aot bisect quit             # abort, persist nothing

State is kept in `<session_dir>/bisect.json`. Conclusions ("first-bad
event at idx K") are appended to `metadata.findings[]` — append-only,
not overwritten on re-bisect.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import IO

from core.recorder import session_dir
from core.session_io import load_events

BISECT_FILENAME = "bisect.json"


class BisectError(RuntimeError):
    pass


# ----- state load / save -----


def _state_path(session_id: str, *, data_dir=None) -> Path:
    return session_dir(session_id, data_dir=data_dir) / BISECT_FILENAME


def _load_state(session_id: str, *, data_dir=None) -> dict | None:
    p = _state_path(session_id, data_dir=data_dir)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _save_state(session_id: str, state: dict, *, data_dir=None) -> None:
    p = _state_path(session_id, data_dir=data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _clear_state(session_id: str, *, data_dir=None) -> None:
    p = _state_path(session_id, data_dir=data_dir)
    if p.exists():
        p.unlink()


# ----- commands -----


def bisect_start(
    session_id: str,
    *,
    lo: int | None = None,
    hi: int | None = None,
    data_dir=None,
    stream: IO[str] | None = None,
) -> dict:
    if stream is None:
        stream = sys.stdout
    events = load_events(session_id, data_dir=data_dir)
    if len(events) < 2:
        raise BisectError("session has fewer than 2 events; nothing to bisect")
    lo = 0 if lo is None else max(0, lo)
    hi = len(events) - 1 if hi is None else min(len(events) - 1, hi)
    if lo >= hi:
        raise BisectError(f"empty bisect range: lo={lo} hi={hi}")
    state = {
        "session_id": session_id,
        "lo": lo,
        "hi": hi,
        "candidate": (lo + hi) // 2,
        "decisions": [],
        "started_at": datetime.now(UTC).isoformat(timespec="milliseconds"),
    }
    _save_state(session_id, state, data_dir=data_dir)
    _render_state(state, events, stream, prefix="bisect started: ")
    return state


def bisect_view(
    session_id: str,
    *,
    data_dir=None,
    stream: IO[str] | None = None,
) -> dict:
    if stream is None:
        stream = sys.stdout
    state = _load_state(session_id, data_dir=data_dir)
    if state is None:
        raise BisectError("no bisect in progress for this session")
    events = load_events(session_id, data_dir=data_dir)
    _render_state(state, events, stream)
    return state


def bisect_mark(
    session_id: str,
    verdict: str,
    *,
    data_dir=None,
    stream: IO[str] | None = None,
) -> dict:
    """`good` / `bad` / `skip` the current candidate."""
    if verdict not in ("good", "bad", "skip"):
        raise BisectError(f"verdict must be good/bad/skip, got {verdict!r}")
    if stream is None:
        stream = sys.stdout
    state = _load_state(session_id, data_dir=data_dir)
    if state is None:
        raise BisectError("no bisect in progress for this session")

    events = load_events(session_id, data_dir=data_dir)
    candidate = int(state["candidate"])
    state["decisions"].append(
        {
            "candidate": candidate,
            "verdict": verdict,
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
        }
    )

    if verdict == "good":
        state["lo"] = candidate + 1
    elif verdict == "bad":
        state["hi"] = candidate
    # skip: nudge candidate forward; if no room, treat as bad
    if verdict == "skip":
        if candidate + 1 < state["hi"]:
            state["candidate"] = candidate + 1
            _save_state(session_id, state, data_dir=data_dir)
            _render_state(state, events, stream, prefix="skipped, advancing: ")
            return state
        state["hi"] = candidate  # treat as bad

    if state["lo"] >= state["hi"]:
        # Converged: hi is the first-bad event index.
        first_bad = state["hi"]
        _record_finding(session_id, first_bad, state["decisions"], data_dir=data_dir)
        _clear_state(session_id, data_dir=data_dir)
        ev = events[first_bad]
        stream.write(
            f"bisect converged: first-bad event index = {first_bad} "
            f"(ts={ev.get('ts')}, type={ev.get('event_type')})\n"
        )
        return {**state, "converged": True, "first_bad": first_bad}

    state["candidate"] = (state["lo"] + state["hi"]) // 2
    _save_state(session_id, state, data_dir=data_dir)
    _render_state(state, events, stream)
    return state


def bisect_status(
    session_id: str,
    *,
    data_dir=None,
    stream: IO[str] | None = None,
) -> dict | None:
    if stream is None:
        stream = sys.stdout
    state = _load_state(session_id, data_dir=data_dir)
    if state is None:
        stream.write("no bisect in progress for this session.\n")
        return None
    events = load_events(session_id, data_dir=data_dir)
    _render_state(state, events, stream, prefix="status: ")
    return state


def bisect_log(
    session_id: str,
    *,
    data_dir=None,
    stream: IO[str] | None = None,
) -> list:
    if stream is None:
        stream = sys.stdout
    state = _load_state(session_id, data_dir=data_dir)
    if state is None:
        stream.write("no bisect in progress for this session.\n")
        return []
    for d in state.get("decisions", []):
        stream.write(f"  - {d['ts']} candidate={d['candidate']} verdict={d['verdict']}\n")
    return state.get("decisions", [])


def bisect_quit(
    session_id: str,
    *,
    data_dir=None,
    stream: IO[str] | None = None,
) -> None:
    if stream is None:
        stream = sys.stdout
    _clear_state(session_id, data_dir=data_dir)
    stream.write("bisect aborted; no finding recorded.\n")


# ----- helpers -----


def _record_finding(session_id: str, first_bad: int, decisions: list, *, data_dir=None) -> None:
    """Append a `findings` entry to metadata.json (append-only)."""
    sdir = session_dir(session_id, data_dir=data_dir)
    meta_file = sdir / "metadata.json"
    if not meta_file.exists():
        return
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    findings = meta.setdefault("findings", [])
    findings.append(
        {
            "kind": "bisect_first_bad",
            "event_idx": first_bad,
            "steps": len(decisions),
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
        }
    )
    tmp = meta_file.with_suffix(meta_file.suffix + ".tmp")
    tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(meta_file)


def _render_state(state, events, stream, *, prefix: str = "") -> None:
    cand = int(state["candidate"])
    ev = events[cand]
    stream.write(f"{prefix}range [{state['lo']}, {state['hi']}], candidate=event {cand}\n")
    stream.write(f"  ts={ev.get('ts')} type={ev.get('event_type')} tool={ev.get('tool_name')}\n")
    paths = ev.get("paths") or []
    if paths:
        stream.write(f"  paths={paths}\n")
    body = ev.get("user_prompt_text") or ev.get("agent_response_text") or ev.get("command") or ""
    if body:
        stream.write(f"  preview: {body[:120]!r}\n")
