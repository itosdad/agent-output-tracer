"""Unit tests for core.normalizer (engine dispatcher).

Contract: `core.normalizer.normalize(engine, raw, event_type=None, *, now=None)`
dispatches to the correct adapter. Unknown engine → None.
"""

from __future__ import annotations

from datetime import UTC, datetime

from core.normalizer import SUPPORTED_ENGINES, normalize


def test_dispatch_claude_code():
    raw = {
        "session_id": "s",
        "hook_event_name": "UserPromptSubmit",
        "user_prompt": "hi",
    }
    out = normalize(
        "claude-code",
        raw,
        now=lambda: datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert out is not None
    assert out["engine"] == "claude-code"
    assert out["event_type"] == "user_prompt"


def test_dispatch_unknown_engine_returns_none():
    raw = {"session_id": "s", "hook_event_name": "UserPromptSubmit"}
    assert normalize("unknown-engine", raw) is None


def test_supported_engines_contains_claude_code():
    assert "claude-code" in SUPPORTED_ENGINES
