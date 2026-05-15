"""Filesystem path helpers for the plugin data dir.

3.9-compat (loaded by hook scripts that run under the user's `python3`).
"""

from __future__ import annotations

import os
from pathlib import Path

SESSIONS_SUBDIR = "sessions"


def resolve_data_dir(explicit=None):
    """Return the plugin data directory as a Path.

    Lookup order (first hit wins):
      1. `explicit` argument (e.g. `--data-dir` from the CLI)
      2. `CLAUDE_PLUGIN_DATA` env (Claude Code, and Codex's
         Claude-compat layer per DESIGN §3.2.8)
      3. `CODEX_PLUGIN_DATA` env (forward-compatible — if a future Codex
         release introduces its own env var, just export this and the
         hook picks it up without code changes)
      4. `~/.codex/plugins/data/agent-output-tracer/` if it exists
         (matches Codex's documented install cache layout)
      5. None — caller must supply `--data-dir` explicitly
    """
    if explicit is not None:
        return Path(explicit)
    for var in ("CLAUDE_PLUGIN_DATA", "CODEX_PLUGIN_DATA"):
        env = os.environ.get(var)
        if env:
            return Path(env)
    codex_default = Path.home() / ".codex" / "plugins" / "data" / "agent-output-tracer"
    if codex_default.exists():
        return codex_default
    return None


def is_safe_session_id(session_id):
    """Cheap defense against path traversal in session_id values.

    Allows alphanumerics, hyphen, underscore, dot. Rejects empty, `.`,
    `..`, and anything containing a path separator.
    """
    if not isinstance(session_id, str) or not session_id:
        return False
    if session_id in (".", ".."):
        return False
    if "/" in session_id or "\\" in session_id:
        return False
    if os.sep in session_id:
        return False
    if os.altsep and os.altsep in session_id:
        return False
    # Allow URL-safe-ish charset; engines hand out UUID-like or opaque ids.
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
    return all(c in allowed for c in session_id)
