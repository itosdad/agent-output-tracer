"""Common entry-point logic shared by every hook script.

Hook scripts call `run_hook("pre_tool")` (or whichever event_type) and
that's it. This module:

  1. Reads JSON from stdin (silently None on failure / empty).
  2. Detects which engine fired this hook by inspecting the payload
     shape (Codex emits `permission_mode` on every event; Claude Code
     does not).
  3. Dispatches to the matching adapter to produce a normalized event.
  4. Appends via the recorder.

Any exception is swallowed; the calling process always exits 0. The
agent must never be blocked by an observation-only plugin.

The `event_type` arg is the Claude-style plugin event_type the script
expects. For events that Claude Code doesn't subscribe to (SessionStart,
PreCompact, PostCompact), the script passes None and the adapter maps
from `hook_event_name` itself.

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


def _detect_engine(raw):
    """Return the engine id implied by the payload shape.

    Codex emits `permission_mode` and `model` on every hook event; Claude
    Code does not. The `hook_event_name` casing also differs (Codex is
    snake_case, Claude Code is CamelCase), which gives us a redundant
    second signal.
    """
    if not isinstance(raw, dict):
        return "claude-code"
    if "permission_mode" in raw:
        return "codex"
    name = raw.get("hook_event_name")
    if isinstance(name, str) and name and name == name.lower() and "_" in name:
        return "codex"
    return "claude-code"


def run_hook(event_type):
    """Execute the standard read → normalize → append cycle.

    `event_type` is the Claude-style plugin event_type the script
    expects. Pass None for events that Codex emits but Claude Code does
    not subscribe to (SessionStart, PreCompact, PostCompact) — the
    adapter will derive event_type from `hook_event_name` in that case.

    Silent on all failures. Returns None.
    """
    try:
        _ensure_plugin_root_on_path()

        raw = _read_stdin_json()
        if raw is None:
            return

        from core.recorder import append_event

        engine = _detect_engine(raw)
        if engine == "codex":
            from adapters.codex import normalize_event
        else:
            from adapters.claude_code import normalize_event

        normalized = normalize_event(raw, event_type=event_type)
        if normalized is None:
            return
        append_event(normalized)
    except Exception:
        pass
