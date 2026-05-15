"""3-line error UX (DESIGN_FORENSIC_UX §4.3).

Every CLI failure surfaces:

  error: <short headline>
    cause: <root cause, including data when available>
    try:   <one or more next-action commands>

The `try` lines are aligned to the colon so they read like an ordered
recipe rather than a wall of text.

Callers use `print_error(...)` to render to stderr, then return the
correct exit code (DESIGN_FORENSIC_UX §3.3).
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from typing import IO

from cli.colors import Palette


def format_error_block(
    headline: str,
    *,
    cause: str | None = None,
    tries: Iterable[str] | None = None,
    palette: Palette | None = None,
) -> str:
    """Return the 3-line error text. Pure; no I/O."""
    p = palette or Palette(color_mode="never")
    lines: list[str] = []
    lines.append(f"{p.paint('error:', 'red')} {headline}")
    if cause:
        # Multi-line causes (e.g. ambiguous session listings) indent
        # consistently under the cause prefix.
        cause_lines = cause.splitlines() or [cause]
        first = cause_lines[0]
        lines.append(f"  {p.paint('cause:', 'dim')} {first}")
        for ln in cause_lines[1:]:
            lines.append(f"         {ln}")
    if tries:
        try_list = list(tries)
        if try_list:
            lines.append(f"  {p.paint('try:  ', 'dim')} {try_list[0]}")
            for cmd in try_list[1:]:
                lines.append(f"         {cmd}")
    return "\n".join(lines)


def print_error(
    headline: str,
    *,
    cause: str | None = None,
    tries: Iterable[str] | None = None,
    stream: IO[str] | None = None,
    palette: Palette | None = None,
) -> None:
    """Render `format_error_block(...)` to a stream (default stderr)."""
    if stream is None:
        stream = sys.stderr
    if palette is None:
        palette = Palette(color_mode="auto", stream=stream)
    stream.write(format_error_block(headline, cause=cause, tries=tries, palette=palette))
    stream.write("\n")
