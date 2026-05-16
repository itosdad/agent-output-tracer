"""Shared helpers for reading the active theme's palette colours.

Render paths across the TUI need to tint Rich Text in step with the
active Textual theme. Each helper reads one slot off
`app.current_theme` and falls back to a sensible terminal default
when Textual hasn't mounted yet.

Accent + the three semantic slots (success / warning / error) are
exposed here so that every coloured glyph in the app picks up the
engine-specific palette — Codex's bright cyan/green/yellow/red vs
Claude's warmer salmon-leaning equivalents.
"""

from __future__ import annotations


def _slot(app, name: str, fallback: str) -> str:
    try:
        value = getattr(app.current_theme, name, None)
        return value or fallback
    except Exception:
        return fallback


def accent(app) -> str:
    """Engine accent — the colour that carries identity (cyan/salmon)."""
    return _slot(app, "accent", "cyan")


def success(app) -> str:
    """Active theme's success colour (Codex bright green / Claude warm green)."""
    return _slot(app, "success", "green")


def warning(app) -> str:
    """Active theme's warning colour (Codex amber / Claude warm tan)."""
    return _slot(app, "warning", "yellow")


def error(app) -> str:
    """Active theme's error colour (Codex bright red / Claude warm red)."""
    return _slot(app, "error", "red")


def severity(app, name: str) -> str:
    """Map a CLI-style status word to the theme's matching colour.

    Accepts the values `query.doctor` already uses (`ok` / `warn` /
    `fail`) plus the more verbose `success` / `warning` / `error` so
    callers can pass whichever fits the call site without translation.
    """
    name = (name or "").lower()
    if name in ("ok", "success", "good", "pass"):
        return success(app)
    if name in ("warn", "warning", "stale"):
        return warning(app)
    if name in ("fail", "error", "bad"):
        return error(app)
    return _slot(app, "foreground", "white")
