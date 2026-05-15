"""Lightweight time formatting helpers used by the query surface.

Stays 3.9-compat so it can be loaded by hook scripts too.
"""

from __future__ import annotations

from datetime import datetime


def short_time(ts):
    """Render an ISO 8601 timestamp as `HH:MM:SS` (24h, no date).

    Returns the original string on parse failure so the caller still
    sees something useful.
    """
    if not isinstance(ts, str) or not ts:
        return ts or ""
    try:
        return datetime.fromisoformat(ts).strftime("%H:%M:%S")
    except ValueError:
        return ts


def long_time(ts):
    """Render an ISO 8601 timestamp as `YYYY-MM-DD HH:MM:SS` (no tz).

    Returns the original string on parse failure.
    """
    if not isinstance(ts, str) or not ts:
        return ts or ""
    try:
        return datetime.fromisoformat(ts).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return ts


def human_bytes(n):
    """Format a byte count as e.g. `5 B`, `12.3 KB`, `1.2 MB`."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return str(n)
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    if n < 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    return f"{n / (1024 * 1024 * 1024):.1f} GB"


def truncate(text, limit):
    """Truncate a string to `limit` chars, with a trailing ellipsis if cut."""
    if not isinstance(text, str):
        return text
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"
