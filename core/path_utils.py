"""Filesystem path helpers for the plugin data dir.

3.9-compat (loaded by hook scripts that run under the user's `python3`).
"""

from __future__ import annotations

import os
from pathlib import Path

SESSIONS_SUBDIR = "sessions"


def resolve_data_dir(explicit=None):
    """Return the plugin data directory as a Path.

    Order: explicit param → `CLAUDE_PLUGIN_DATA` env → None.
    """
    if explicit is not None:
        return Path(explicit)
    env = os.environ.get("CLAUDE_PLUGIN_DATA")
    if env:
        return Path(env)
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
