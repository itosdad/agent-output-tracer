"""Engine-log overlay (DESIGN_FORENSIC_UX §8.2).

Reads Claude Code / Codex debug log files (when present) and produces
per-line annotations keyed by timestamp. The bridge is READ-ONLY: it
never writes to the engine's log directory, and it gracefully reports
"no overlay available" when the env / path isn't configured.

The Claude Code debug log lives at `~/.claude/debug/<session_id>.txt`
by default; the env `CLAUDE_CODE_DEBUG_LOGS_DIR` overrides the dir.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from pathlib import Path

_TS_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)"
)


def claude_debug_log_path(session_id: str) -> Path:
    base = os.environ.get("CLAUDE_CODE_DEBUG_LOGS_DIR")
    if base:
        return Path(base) / f"{session_id}.txt"
    return Path.home() / ".claude" / "debug" / f"{session_id}.txt"


def is_enabled() -> bool:
    """True iff at least one engine debug log dir resolves to something
    on disk. Used by `aot config list --diagnose` (later phase) and
    `aot doctor`."""
    base = os.environ.get("CLAUDE_CODE_DEBUG_LOGS_DIR")
    if base and Path(base).is_dir():
        return True
    default = Path.home() / ".claude" / "debug"
    return default.is_dir()


def load_overlay(session_id: str) -> list[dict]:
    """Read the debug log for `session_id` and return a list of
    `{ts, line}` dicts ordered by appearance. Empty list if the file
    doesn't exist or no lines parse with a timestamp."""
    log_file = claude_debug_log_path(session_id)
    if not log_file.exists():
        return []
    out: list[dict] = []
    try:
        text = log_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _TS_RE.search(line)
        ts = m.group(1) if m else None
        out.append({"ts": ts, "line": line})
    return out


def merge_with_events(
    events: list[dict],
    overlay: Iterable[dict],
) -> list[dict]:
    """Interleave overlay lines with normalized events, ordered by ts.

    Both inputs use ISO-8601 timestamps; the lexical order is correct
    for events from the same engine within a session. Overlay entries
    without a ts are emitted at the end."""
    annotated_events = [
        {**ev, "_source": "event"} for ev in events
    ]
    annotated_overlay = [
        {**ov, "_source": "engine_log"} for ov in overlay
    ]
    everything = annotated_events + annotated_overlay
    everything.sort(key=lambda x: x.get("ts") or "~")  # None → end
    return everything
