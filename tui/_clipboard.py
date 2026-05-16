"""Thin clipboard wrapper used by `y` yank bindings across the TUI.

Textual captures mouse events which means a normal click-drag in the
terminal no longer selects text. Two recovery paths:

  1. Explicit `y` yank — every list / detail screen exposes a yank
     binding that pipes the highlighted content through this helper
     to the platform clipboard.
  2. Native terminal selection — iTerm2 / Terminal.app / Kitty all
     respect Option-drag (macOS) or Shift-drag (Linux) to bypass
     Textual's mouse capture. Help overlay documents this.

We deliberately avoid `pyperclip` as a dependency — the platforms we
care about all ship a binary (`pbcopy` / `xclip` / `xsel` / `clip`)
and shelling out to it is one line of code.
"""

from __future__ import annotations

import shutil
import subprocess
import sys


def copy(text: str) -> bool:
    """Pipe `text` into the platform clipboard. Returns True on
    success, False if no clipboard tool is reachable.

    Failures are silent at this layer — callers decide whether to
    notify the user; we just report the outcome.
    """
    if not text:
        return False
    cmd = _platform_cmd()
    if cmd is None:
        return False
    try:
        proc = subprocess.run(
            cmd,
            input=text,
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def available() -> bool:
    """Whether *some* clipboard tool is reachable. Useful for skipping
    the `y` binding hint when we know yank would silently fail."""
    return _platform_cmd() is not None


def _platform_cmd() -> list[str] | None:
    """Return the argv for whichever clipboard tool is on PATH.

    Order of preference per platform:
      macOS   → pbcopy
      Linux   → xclip > xsel > wl-copy
      Windows → clip (cmd) — falls back to PowerShell Set-Clipboard
    """
    if sys.platform == "darwin":
        if shutil.which("pbcopy"):
            return ["pbcopy"]
        return None
    if sys.platform.startswith("linux"):
        if shutil.which("xclip"):
            return ["xclip", "-selection", "clipboard"]
        if shutil.which("xsel"):
            return ["xsel", "--clipboard", "--input"]
        if shutil.which("wl-copy"):
            return ["wl-copy"]
        return None
    if sys.platform.startswith("win"):
        if shutil.which("clip"):
            return ["clip"]
        if shutil.which("powershell"):
            return ["powershell", "-NoProfile", "-Command", "Set-Clipboard"]
        return None
    return None
