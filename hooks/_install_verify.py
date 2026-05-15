"""Install-verify helper used by the Phase A-1 hook scripts.

In install-verify mode each hook reads its event JSON from stdin and appends
a single line to `${CLAUDE_PLUGIN_DATA}/_install_verify.jsonl`. This lets the
operator confirm that:

  - `${CLAUDE_PLUGIN_ROOT}` resolved (the hook script was found and executed)
  - `${CLAUDE_PLUGIN_DATA}` resolved (we could write to disk)
  - The event JSON arrived on stdin with the fields we expect

After Phase A-3 lands the real recorder, these scripts are rewritten and
this helper is removed.

Contract: always exit 0, never raise, never write to stderr — the agent must
not be blocked or alarmed by an observation-only plugin.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def _data_dir() -> Path | None:
    data = os.environ.get("CLAUDE_PLUGIN_DATA")
    if not data:
        return None
    return Path(data)


def record(event_name: str) -> None:
    """Append one install-verify line for the given hook event name.

    Silent on any failure (read stdin, JSON parse, write disk). The hook
    process always exits 0 regardless.
    """
    try:
        raw = sys.stdin.read()
    except Exception:  # noqa: BLE001
        raw = ""

    parsed: dict | None
    try:
        parsed = json.loads(raw) if raw.strip() else None
    except Exception:  # noqa: BLE001
        parsed = None

    data_dir = _data_dir()
    if data_dir is None:
        return

    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        out = data_dir / "_install_verify.jsonl"
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "hook": event_name,
            "stdin_len": len(raw),
            "stdin_parsed_ok": parsed is not None,
            "session_id": (parsed or {}).get("session_id"),
            "hook_event_name": (parsed or {}).get("hook_event_name"),
            "tool_name": (parsed or {}).get("tool_name"),
            "cwd": (parsed or {}).get("cwd"),
            "plugin_root_env": os.environ.get("CLAUDE_PLUGIN_ROOT"),
            "plugin_data_env": os.environ.get("CLAUDE_PLUGIN_DATA"),
        }
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass
