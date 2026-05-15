"""Side-channel TUI (DESIGN_FORENSIC_UX §5).

This package is loaded lazily by `aot tui`. The dependencies it needs
(`textual`, `watchdog`) live in the `[tui]` optional extra. If those
aren't installed, `aot tui` prints a 3-line error pointing at the
install command and exits non-zero — the rest of the CLI keeps working.
"""

from __future__ import annotations


def is_available() -> bool:
    """True iff `textual` (the heavyweight TUI dep) can be imported.

    Used by `aot tui` to gate startup and by tests to skip cleanly when
    the optional dep is absent.
    """
    try:
        import textual  # noqa: F401
    except ImportError:
        return False
    return True
