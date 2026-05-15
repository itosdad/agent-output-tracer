"""Unit tests for core.session_resolver — the DESIGN §8.3 spec parser.

- `latest` → most recent session
- `latest-N` → N-th most recent
- `<full_id>` → that session
- `<short_id>` (>= 4 chars, unique prefix) → that session
- `YYYY-MM-DD` → latest session whose ts_start has that date
"""

from __future__ import annotations

import pytest

from core.recorder import append_event
from core.session_resolver import (
    AmbiguousSessionSpec,
    SessionSpecNotFound,
    resolve_session_id,
)


def _make(plugin_data_dir, sid, ts):
    append_event(
        {
            "v": 1,
            "engine": "claude-code",
            "event_type": "user_prompt",
            "session_id": sid,
            "ts": ts,
            "cwd": "/p",
            "user_prompt_text": "x",
            "tool_name": None,
            "tool_input": None,
            "tool_response": None,
            "agent_response_text": None,
            "stop_reason": None,
            "paths": [],
            "command": None,
            "result_bytes": 0,
            "raw_event": {},
        },
        data_dir=plugin_data_dir,
    )


def test_resolve_full_session_id(plugin_data_dir):
    _make(plugin_data_dir, "abc12345", "2026-05-14T10:00:00.000+00:00")
    assert resolve_session_id("abc12345", data_dir=plugin_data_dir) == "abc12345"


def test_resolve_unknown_full_id(plugin_data_dir):
    _make(plugin_data_dir, "abc12345", "2026-05-14T10:00:00.000+00:00")
    with pytest.raises(SessionSpecNotFound):
        resolve_session_id("does-not-exist", data_dir=plugin_data_dir)


def test_resolve_latest(plugin_data_dir):
    _make(plugin_data_dir, "old1", "2025-01-01T00:00:00.000+00:00")
    _make(plugin_data_dir, "old2", "2026-01-01T00:00:00.000+00:00")
    _make(plugin_data_dir, "newest", "2026-12-31T00:00:00.000+00:00")
    assert resolve_session_id("latest", data_dir=plugin_data_dir) == "newest"


def test_resolve_latest_n(plugin_data_dir):
    _make(plugin_data_dir, "s1", "2026-01-01T00:00:00.000+00:00")
    _make(plugin_data_dir, "s2", "2026-02-01T00:00:00.000+00:00")
    _make(plugin_data_dir, "s3", "2026-03-01T00:00:00.000+00:00")
    # latest-0 == latest
    assert resolve_session_id("latest-0", data_dir=plugin_data_dir) == "s3"
    assert resolve_session_id("latest-1", data_dir=plugin_data_dir) == "s2"
    assert resolve_session_id("latest-2", data_dir=plugin_data_dir) == "s1"


def test_resolve_latest_n_out_of_range(plugin_data_dir):
    _make(plugin_data_dir, "s1", "2026-01-01T00:00:00.000+00:00")
    with pytest.raises(SessionSpecNotFound):
        resolve_session_id("latest-5", data_dir=plugin_data_dir)


def test_resolve_short_prefix(plugin_data_dir):
    _make(plugin_data_dir, "abcdef123456", "2026-01-01T00:00:00.000+00:00")
    _make(plugin_data_dir, "xyzabcabc", "2026-02-01T00:00:00.000+00:00")
    # 4+ char prefix, unique
    assert resolve_session_id("abcd", data_dir=plugin_data_dir) == "abcdef123456"


def test_resolve_short_prefix_ambiguous(plugin_data_dir):
    _make(plugin_data_dir, "abcdef123", "2026-01-01T00:00:00.000+00:00")
    _make(plugin_data_dir, "abcd0099", "2026-02-01T00:00:00.000+00:00")
    with pytest.raises(AmbiguousSessionSpec):
        resolve_session_id("abcd", data_dir=plugin_data_dir)


def test_resolve_short_prefix_too_short_treated_as_literal(plugin_data_dir):
    """Short specs (<4 chars) are not treated as prefix — they're either
    exact match or not found, so we don't accidentally trip the prefix
    path on common 1-2 char inputs."""
    _make(plugin_data_dir, "ab", "2026-01-01T00:00:00.000+00:00")
    _make(plugin_data_dir, "abc12345", "2026-02-01T00:00:00.000+00:00")
    # Exact match wins
    assert resolve_session_id("ab", data_dir=plugin_data_dir) == "ab"
    # Anything < 4 chars that isn't exact should raise not-found
    with pytest.raises(SessionSpecNotFound):
        resolve_session_id("xy", data_dir=plugin_data_dir)


def test_resolve_iso_date(plugin_data_dir):
    _make(plugin_data_dir, "morning", "2026-05-14T09:00:00.000+00:00")
    _make(plugin_data_dir, "afternoon", "2026-05-14T15:00:00.000+00:00")
    _make(plugin_data_dir, "other-day", "2026-05-13T10:00:00.000+00:00")
    # Latest of that day wins
    assert resolve_session_id("2026-05-14", data_dir=plugin_data_dir) == "afternoon"


def test_resolve_iso_date_no_match(plugin_data_dir):
    _make(plugin_data_dir, "s1", "2026-05-14T10:00:00.000+00:00")
    with pytest.raises(SessionSpecNotFound):
        resolve_session_id("2026-05-15", data_dir=plugin_data_dir)


def test_resolve_empty_data_dir(plugin_data_dir):
    with pytest.raises(SessionSpecNotFound):
        resolve_session_id("latest", data_dir=plugin_data_dir)


def test_resolve_priority_exact_beats_prefix(plugin_data_dir):
    """If an exact match exists, prefer it even when there are other
    longer ids with the same prefix."""
    _make(plugin_data_dir, "abcd", "2026-01-01T00:00:00.000+00:00")
    _make(plugin_data_dir, "abcdef9999", "2026-02-01T00:00:00.000+00:00")
    assert resolve_session_id("abcd", data_dir=plugin_data_dir) == "abcd"
