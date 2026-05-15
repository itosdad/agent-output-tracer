"""Common entry-point logic shared by every hook script.

Hook scripts call `run_hook("pre_tool")` (or whichever event_type) and
that's it. This module:

  1. Reads JSON from stdin (silently None on failure / empty).
  2. Normalizes via the Claude Code adapter.
  3. Appends via the recorder.

Any exception is swallowed; the calling process always exits 0. The agent
must never be blocked by an observation-only plugin.

3.9-compat (loaded by hook scripts running under the user's `python3`).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _ensure_plugin_root_on_path():
    """Make `adapters` and `core` importable when the script is invoked
    directly via `python3 path/to/hooks/foo.py`."""
    plugin_root = Path(__file__).resolve().parent.parent
    if str(plugin_root) not in sys.path:
        sys.path.insert(0, str(plugin_root))


def _read_stdin_json():
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


def run_hook(event_type):
    """Execute the standard read → normalize → append cycle.

    Silent on all failures. Returns None.
    """
    try:
        _ensure_plugin_root_on_path()

        raw = _read_stdin_json()
        if raw is None:
            return

        from adapters.claude_code import normalize_event
        from core.recorder import append_event

        normalized = normalize_event(raw, event_type=event_type)
        if normalized is None:
            return
        append_event(normalized)
    except Exception:
        pass
