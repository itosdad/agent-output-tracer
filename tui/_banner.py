"""Home-screen banner + canonical display name.

OhMyZsh-style ASCII art splash that shows the project's formal name
the moment the operator opens the TUI. Two reasons it lives here
rather than inlined in the HomeScreen:

1. Centralised `APP_NAME` constant — every breadcrumb root, every
   toast title, the App window title all import this string. Renaming
   the product later is a one-line change.
2. The banner art and tagline are static; testing them with the
   `home-banner` Static widget keeps `home.py` focused on layout
   and routing instead of ASCII bookkeeping.

The art is the figlet `slant` font rendering of "AOT" (3 chars *
5-line) so it fits comfortably inside a 72-col half-desktop layout,
with the full product name on the tagline beside it.
"""

from __future__ import annotations

from rich.text import Text

APP_NAME = "agent-output-tracer"
TAGLINE = "forensic debugger for AI agent sessions"

# Lines of the slant-font "AOT" rendering. Kept as a tuple so callers
# can compute widths or zip with side text without re-parsing newlines.
_ART_LINES: tuple[str, ...] = (
    "    ___    ____  ______",
    "   /   |  / __ \\/_  __/",
    "  / /| | / / / / / /   ",
    " / ___ |/ /_/ / / /    ",
    "/_/  |_|\\____/ /_/     ",
)


def _version() -> str:
    """Best-effort version string. Reads from installed package
    metadata; falls back to "?" so a development checkout without
    an installed dist doesn't crash the banner."""
    try:
        from importlib.metadata import version

        return version("agent-output-tracer")
    except Exception:
        return "?"


def render_banner(app) -> Text:
    """Return a Rich Text styled with the active theme's accent.

    Layout:
        ASCII art on the left, two-line tagline on the right of the
        last two art rows. Total height = 5 rows + 1 blank + 1
        version/help line = 7 rows.
    """
    from tui._accent import accent

    col = accent(app)
    text = Text()
    # Right-side annotations align with art rows 2 and 3 (counting
    # from 0) so the eye reads `AOT  agent-output-tracer` as one unit.
    annotations = [
        "",
        "",
        f"  {APP_NAME}",
        f"  {TAGLINE}",
        "",
    ]
    for line, annotation in zip(_ART_LINES, annotations, strict=True):
        text.append(line, style=f"bold {col}")
        if annotation:
            text.append(annotation, style="dim")
        text.append("\n")
    text.append("\n")
    text.append(f"v{_version()}  ·  ", style="dim")
    text.append("?", style=f"bold {col}")
    text.append(" help  ·  ", style="dim")
    text.append(":", style=f"bold {col}")
    text.append(" palette  ·  ", style="dim")
    text.append("t", style=f"bold {col}")
    text.append(" cycle theme", style="dim")
    return text
