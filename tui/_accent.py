"""Shared helper for reading the active theme's accent colour.

Several render() methods need to colour their Rich Text in step with
the current Textual theme. Each previously duplicated a private
`_accent(app)` helper; this module is the one source of truth.

Returns a colour string Rich understands (hex `#RRGGBB` from the
Theme dataclass, or `"cyan"` as a defensive fallback if Textual
hasn't finished mounting yet).
"""

from __future__ import annotations


def accent(app) -> str:
    """Return the active theme's accent colour, or `"cyan"`."""
    try:
        return app.current_theme.accent or "cyan"
    except Exception:
        return "cyan"
