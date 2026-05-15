"""Engine-specific Textual themes.

Two custom themes, registered on the App at mount:

* `aot-codex` — cyan accent. Sourced from the openai/codex Rust TUI
  (`codex-rs/tui/src/style.rs:44` uses `Color::Cyan + BOLD` as the
  primary accent against the terminal default background). Cited in
  the v0.7.0 design notes.

* `aot-claude` — salmon/rust accent. β-flavored from Anthropic's
  publicly-visible brand colour (#CC785C is the warm tone used on
  the company's marketing surfaces). The Claude Code CLI itself
  ships without a documented colour spec, so this is an inspired
  approximation, not a one-for-one clone.

Both inherit the terminal's default background — the tracer's TUI
is borderless prose, the accent is what carries the engine identity.

Auto-detect rule: if the session metadata's `engine` field is
"claude-code", the app starts on `aot-claude`; "codex" → `aot-codex`;
unknown / missing → `aot-codex` (cyan is a safer default against
the variety of terminal palettes most people run).

`t` cycles between the two themes (Phase 3.A binding on AOTScreen).
"""

from __future__ import annotations

from textual.theme import Theme

CODEX_THEME = Theme(
    name="aot-codex",
    primary="#00aaaa",  # terminal cyan
    secondary="#5fafaf",
    accent="#00d7d7",
    foreground="#e0e0e0",
    background="#121212",
    surface="#1a1a1a",
    panel="#202020",
    success="#00ff00",
    warning="#ffaa00",
    error="#ff5555",
    dark=True,
)

CLAUDE_THEME = Theme(
    name="aot-claude",
    primary="#cc785c",  # Anthropic-flavoured salmon
    secondary="#a85a3f",
    accent="#e08a6a",
    foreground="#e6e0d8",
    background="#121212",
    surface="#1d1714",
    panel="#241c18",
    success="#9ec97e",
    warning="#e0b070",
    error="#e07060",
    dark=True,
)


def theme_for_engine(engine: str | None) -> str:
    """Return the Textual theme name that best matches `engine`."""
    if engine == "claude-code":
        return CLAUDE_THEME.name
    return CODEX_THEME.name


def next_theme(current: str) -> str:
    """Cycle between the two custom themes."""
    if current == CLAUDE_THEME.name:
        return CODEX_THEME.name
    return CLAUDE_THEME.name
