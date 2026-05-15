#!/usr/bin/env python3
"""PostCompact hook entry point (Codex 0.129+).

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
