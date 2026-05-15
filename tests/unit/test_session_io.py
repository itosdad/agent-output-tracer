"""Unit tests for core.session_io — read-side complement to recorder.py."""

from __future__ import annotations

import pytest

from core.recorder import append_event
from core.session_io import (
    SessionNotFoundError,
    list_sessions,
    load_events,
    load_metadata,
)


def _seed(plugin_data_dir, sid="S1", n_events=3):
    for i in range(n_events):
        append_event(
            {
                "v": 1,
                "engine": "claude-code",
                "event_type": "pre_tool",
                "session_id": sid,
                "ts": f"2026-01-01T00:00:{i:02d}.000+00:00",
                "cwd": "/proj",
                "user_prompt_text": None,
                "tool_name": "Read",
                "tool_input": {"file_path": f"/p/{i}.md"},
                "tool_response": None,
                "agent_response_text": None,
                "stop_reason": None,
                "paths": [f"/p/{i}.md"],
                "command": None,
                "result_bytes": 0,
                "raw_event": {},
            }
        )


def test_load_events_reads_jsonl_back_in_order(plugin_data_dir):
    _seed(plugin_data_dir, n_events=3)
    events = load_events("S1", data_dir=plugin_data_dir)
    assert len(events) == 3
    assert [e["ts"] for e in events] == [
        "2026-01-01T00:00:00.000+00:00",
        "2026-01-01T00:00:01.000+00:00",
        "2026-01-01T00:00:02.000+00:00",
    ]


def test_load_events_missing_session(plugin_data_dir):
    with pytest.raises(SessionNotFoundError):
        load_events("nope", data_dir=plugin_data_dir)


def test_load_events_skips_corrupt_lines(plugin_data_dir):
    """A partial / corrupt line in events.jsonl must not crash the
    loader. The loader skips invalid lines and returns the rest."""
    _seed(plugin_data_dir, n_events=2)
    events_file = plugin_data_dir / "sessions" / "S1" / "events.jsonl"
    with events_file.open("a") as f:
        f.write("this is not json\n")
        f.write('{"valid": true, "ts": "2026-01-01T00:00:99.000+00:00"}\n')
    events = load_events("S1", data_dir=plugin_data_dir)
    # 2 original + 1 valid extra
    assert len(events) == 3


def test_load_metadata(plugin_data_dir):
    _seed(plugin_data_dir, n_events=2)
    meta = load_metadata("S1", data_dir=plugin_data_dir)
    assert meta["session_id"] == "S1"
    assert meta["tool_calls_total"] == 2


def test_load_metadata_missing_session(plugin_data_dir):
    with pytest.raises(SessionNotFoundError):
        load_metadata("nope", data_dir=plugin_data_dir)


def test_load_metadata_missing_file_in_session_dir(plugin_data_dir):
    """events.jsonl present but metadata.json removed → return None
    rather than raise (this is a degraded but recoverable state)."""
    _seed(plugin_data_dir, n_events=1)
    (plugin_data_dir / "sessions" / "S1" / "metadata.json").unlink()
    assert load_metadata("S1", data_dir=plugin_data_dir) is None


def test_list_sessions_empty(plugin_data_dir):
    assert list_sessions(data_dir=plugin_data_dir) == []


def test_list_sessions_returns_metadata(plugin_data_dir):
    _seed(plugin_data_dir, sid="alpha", n_events=1)
    _seed(plugin_data_dir, sid="beta", n_events=2)
    sessions = list_sessions(data_dir=plugin_data_dir)
    by_id = {s["session_id"]: s for s in sessions}
    assert set(by_id) == {"alpha", "beta"}
    assert by_id["beta"]["tool_calls_total"] == 2


def test_list_sessions_sorted_by_recency(plugin_data_dir):
    """list_sessions returns most-recent first. Recency = ts_end (or
    ts_start fallback)."""
    # Older
    append_event(
        {
            "v": 1,
            "engine": "claude-code",
            "event_type": "user_prompt",
            "session_id": "old",
            "ts": "2025-01-01T00:00:00.000+00:00",
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
    # Newer
    append_event(
        {
            "v": 1,
            "engine": "claude-code",
            "event_type": "user_prompt",
            "session_id": "new",
            "ts": "2026-12-01T00:00:00.000+00:00",
            "cwd": "/p",
            "user_prompt_text": "y",
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
    sessions = list_sessions(data_dir=plugin_data_dir)
    assert [s["session_id"] for s in sessions] == ["new", "old"]


def test_list_sessions_handles_corrupt_metadata(plugin_data_dir):
    _seed(plugin_data_dir, sid="ok", n_events=1)
    bad = plugin_data_dir / "sessions" / "bad"
    bad.mkdir(parents=True)
    (bad / "metadata.json").write_text("not json")
    (bad / "events.jsonl").write_text("")
    sessions = list_sessions(data_dir=plugin_data_dir)
    ids = [s["session_id"] for s in sessions]
    # The valid session is present; the corrupt one is either skipped
    # or yields a minimal stub but never crashes.
    assert "ok" in ids


def test_load_events_explicit_data_dir(tmp_path):
    """No env var — pass data_dir explicitly."""
    sid = "explicit-data"
    append_event(
        {
            "v": 1,
            "engine": "claude-code",
            "event_type": "user_prompt",
            "session_id": sid,
            "ts": "2026-01-01T00:00:00.000+00:00",
            "cwd": "/p",
            "user_prompt_text": "hi",
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
        data_dir=tmp_path,
    )
    events = load_events(sid, data_dir=tmp_path)
    assert len(events) == 1
    assert load_metadata(sid, data_dir=tmp_path)["session_id"] == sid


def test_load_events_unsafe_session_id_rejected(plugin_data_dir):
    with pytest.raises(SessionNotFoundError):
        load_events("../escape", data_dir=plugin_data_dir)
