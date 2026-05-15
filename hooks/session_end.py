#!/usr/bin/env python3
"""SessionEnd hook entry point. Silent / failure-tolerant."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _runner import run_hook  # noqa: E402


def main():
    run_hook("session_end")


if __name__ == "__main__":
    try:
        main()
    finally:
        sys.exit(0)
