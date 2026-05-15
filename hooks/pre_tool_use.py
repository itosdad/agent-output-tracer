#!/usr/bin/env python3
"""PreToolUse hook — Phase A-1 install-verify mode."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _install_verify import record  # noqa: E402


def main() -> None:
    try:
        record("PreToolUse")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
