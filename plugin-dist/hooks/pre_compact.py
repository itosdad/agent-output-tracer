#!/usr/bin/env python3
"""PreCompact hook entry point (Codex 0.129+).

Claude Code also has PreCompact (manual + auto), but we don't currently
subscribe to it. Cost is the same as session_start.py — one extra
Python startup per fire with no recorded data on Claude Code.

Failure-tolerant per DESIGN §9.1: any exception is swallowed.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _runner import run_hook  # noqa: E402


def main():
    run_hook(None)


if __name__ == "__main__":
    try:
        main()
    finally:
        sys.exit(0)
