#!/usr/bin/env python3
"""PreToolUse hook entry point.

Reads the Claude Code hook event from stdin, normalizes it, and appends
to the session log via `core.recorder.append_event`.

Failure-tolerant per DESIGN §9.1: any exception is swallowed and the
process exits 0 silently. The agent must never be blocked by a
observation-only plugin.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Make sibling packages (adapters, core) importable when this file is
# executed directly via `python3 path/to/pre_tool_use.py`.
_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))


def _read_event_stdin():
    try:
        raw = sys.stdin.read()
    except Exception:
        return None
    if not raw or not raw.strip():
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def main():
    try:
        raw = _read_event_stdin()
        if raw is None:
            return

        # Local import keeps a failed adapter load from poisoning the
        # earlier swallow path.
        from adapters.claude_code import normalize_event
        from core.recorder import append_event

        normalized = normalize_event(raw, event_type="pre_tool")
        if normalized is None:
            return
        append_event(normalized)
    except Exception:
        # Silent fail — never block the agent.
        pass


if __name__ == "__main__":
    try:
        main()
    finally:
        sys.exit(0)
