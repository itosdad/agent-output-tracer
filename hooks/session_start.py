#!/usr/bin/env python3
"""SessionStart hook entry point (Codex-only in our subscription).

Claude Code also fires SessionStart, but its adapter doesn't map this
event_type (design §3.1.2 — we only subscribe to the 5 Claude events).
For Claude Code the runner reads stdin, normalizes, the adapter returns
None, and nothing is recorded. Cost: one extra Python startup per
session, no data side-effect.

Failure-tolerant per DESIGN §9.1: any exception is swallowed and the
process exits 0 silently.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _runner import run_hook  # noqa: E402


def main():
    # event_type=None lets the adapter map from hook_event_name (codex
    # adapter understands "session_start"; claude_code adapter doesn't,
    # so it returns None and the event is dropped — intended).
    run_hook(None)


if __name__ == "__main__":
    try:
        main()
    finally:
        sys.exit(0)
