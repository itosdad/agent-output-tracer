"""Terminal color + symbol palette for the CLI (DESIGN_FORENSIC_UX §4.2).

ASCII symbols only (no emoji). Color is honored when:
  - stdout is a TTY, AND
  - `NO_COLOR` env is not set, AND
  - `--color never` was not passed.

`--color always` forces color even when piped.
"""

from __future__ import annotations

import os
import sys
from typing import IO

# 16-color ANSI escapes — the lowest common denominator.
_CODES = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "dim_cyan": "\033[2;36m",
}

# DESIGN_FORENSIC_UX §4.2 symbol/color table.
SYMBOLS: dict[str, tuple[str, str]] = {
    "user_prompt": (">>", "cyan"),
    "pre_tool": ("..", "dim"),
    "post_tool": ("↪", "reset"),
    "agent_response": ("<<", "green"),
    "session_end": ("==", "dim"),
    "session_start": ("==", "dim_cyan"),
    "compact_pre": ("..", "dim"),
    "compact_post": ("..", "dim"),
    "hint": ("!", "yellow"),
    "hallucination_candidate": ("?", "red"),
    "note": ("*", "magenta"),
    "engine_overlay": ("@", "dim_cyan"),
}


class Palette:
    """Decides whether to emit ANSI codes for a given stream.

    Construct one per CLI invocation. `enabled` is decided once at
    instantiation (TTY check + env + flag); callers don't need to
    re-check downstream.
    """

    def __init__(self, *, color_mode: str = "auto", stream: IO[str] | None = None):
        self.enabled = self._decide(color_mode, stream or sys.stdout)

    @staticmethod
    def _decide(color_mode: str, stream: IO[str]) -> bool:
        if color_mode == "never":
            return False
        if color_mode == "always":
            return True
        # auto:
        if "NO_COLOR" in os.environ:
            return False
        # ``sys.stdout.isatty`` is missing on some test streams (StringIO etc.).
        isatty = getattr(stream, "isatty", None)
        return bool(isatty and isatty())

    def paint(self, text: str, color: str) -> str:
        if not self.enabled or color not in _CODES:
            return text
        return f"{_CODES[color]}{text}{_CODES['reset']}"

    def symbol(self, kind: str) -> str:
        """Return the bare ASCII symbol for an event kind (no color)."""
        sym, _ = SYMBOLS.get(kind, ("·", "reset"))
        return sym

    def labeled(self, kind: str) -> str:
        """Return a colored symbol for an event kind."""
        sym, color = SYMBOLS.get(kind, ("·", "reset"))
        return self.paint(sym, color)
