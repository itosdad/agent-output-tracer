"""Unit tests for core.retention — DESIGN §9.4 (GC: archive at 30d, delete at 365d)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from core.recorder import append_event
from core.retention import run_gc


def _ts(days_ago, now):
    return (now - timedelta(days=days_ago)).isoformat(timespec="milliseconds")


def _seed_session(plugin_data_dir, sid, *, ts_end_days_ago, now):
    ts = _ts(ts_end_days_ago, now)
    for et, kw in [
        ("user_prompt", {"user_prompt_text": "hello"}),
        ("pre_tool", {"tool_name": "Read", "tool_input": {"file_path": "/p/x"}, "paths": ["/p/x"]}),
        (
            "post_tool",
            {
                "tool_name": "Read",
                "tool_input": {"file_path": "/p/x"},
                "paths": ["/p/x"],
                "tool_response": "secret content here",
                "result_bytes": 19,
            },
        ),
        ("agent_response", {"agent_response_text": "verbose agent reply"}),
    ]:
        e = {
            "v": 1,
            "engine": "claude-code",
            "event_type": et,
            "session_id": sid,
            "ts": ts,
            "cwd": "/p",
            "user_prompt_text": None,
            "tool_name": None,
            "tool_input": None,
            "tool_response": None,
            "agent_response_text": None,
            "stop_reason": None,
            "paths": [],
            "command": None,
            "result_bytes": 0,
            "raw_event": {},
        }
        e.update(kw)
        append_event(e, data_dir=plugin_data_dir)


def test_recent_session_untouched(plugin_data_dir):
    now = datetime(2026, 6, 1, tzinfo=UTC)
    _seed_session(plugin_data_dir, "recent", ts_end_days_ago=5, now=now)
    result = run_gc(data_dir=plugin_data_dir, now=now)
    assert "recent" not in result["stripped"]
    assert "recent" not in result["deleted"]
    text = (plugin_data_dir / "sessions" / "recent" / "events.jsonl").read_text()
    assert "secret content here" in text


def test_session_in_archive_band_is_stripped(plugin_data_dir):
    now = datetime(2026, 6, 1, tzinfo=UTC)
    _seed_session(plugin_data_dir, "stripme", ts_end_days_ago=60, now=now)
    result = run_gc(data_dir=plugin_data_dir, now=now)
    assert "stripme" in result["stripped"]
    text = (plugin_data_dir / "sessions" / "stripme" / "events.jsonl").read_text()
    assert "secret content here" not in text
    assert "verbose agent reply" not in text
    # Structure preserved: each line still parses as JSON
    for line in text.splitlines():
        if line.strip():
            json.loads(line)


def test_strip_preserves_metadata(plugin_data_dir):
    now = datetime(2026, 6, 1, tzinfo=UTC)
    _seed_session(plugin_data_dir, "keep-meta", ts_end_days_ago=60, now=now)
    run_gc(data_dir=plugin_data_dir, now=now)
    meta = json.loads((plugin_data_dir / "sessions" / "keep-meta" / "metadata.json").read_text())
    assert meta["session_id"] == "keep-meta"
    assert meta.get("stripped") is True
    # Counters still meaningful even after content strip
    assert meta["tool_calls_total"] >= 1


def test_session_past_delete_threshold_removed(plugin_data_dir):
    now = datetime(2026, 6, 1, tzinfo=UTC)
    _seed_session(plugin_data_dir, "gone", ts_end_days_ago=400, now=now)
    result = run_gc(data_dir=plugin_data_dir, now=now)
    assert "gone" in result["deleted"]
    assert not (plugin_data_dir / "sessions" / "gone").exists()


def test_dry_run_modifies_nothing(plugin_data_dir):
    now = datetime(2026, 6, 1, tzinfo=UTC)
    _seed_session(plugin_data_dir, "old1", ts_end_days_ago=60, now=now)
    _seed_session(plugin_data_dir, "old2", ts_end_days_ago=400, now=now)
    result = run_gc(data_dir=plugin_data_dir, now=now, dry_run=True)
    # Dry-run reports the same actions but the filesystem is unchanged
    assert "old1" in result["stripped"]
    assert "old2" in result["deleted"]
    # but content untouched
    text = (plugin_data_dir / "sessions" / "old1" / "events.jsonl").read_text()
    assert "secret content here" in text
    assert (plugin_data_dir / "sessions" / "old2").exists()


def test_already_stripped_session_skipped(plugin_data_dir):
    now = datetime(2026, 6, 1, tzinfo=UTC)
    _seed_session(plugin_data_dir, "twice", ts_end_days_ago=60, now=now)
    run_gc(data_dir=plugin_data_dir, now=now)
    # First strip succeeds; second pass should be a no-op
    result2 = run_gc(data_dir=plugin_data_dir, now=now)
    assert "twice" not in result2["stripped"]


def test_custom_thresholds(plugin_data_dir):
    now = datetime(2026, 6, 1, tzinfo=UTC)
    _seed_session(plugin_data_dir, "borderline", ts_end_days_ago=10, now=now)
    # Override: archive at 5 days, delete at 100
    result = run_gc(data_dir=plugin_data_dir, now=now, archive_days=5, delete_days=100)
    assert "borderline" in result["stripped"]


def test_corrupt_metadata_session_skipped(plugin_data_dir):
    sdir = plugin_data_dir / "sessions" / "bad"
    sdir.mkdir(parents=True)
    (sdir / "metadata.json").write_text("not json")
    (sdir / "events.jsonl").write_text("")
    now = datetime(2026, 6, 1, tzinfo=UTC)
    result = run_gc(data_dir=plugin_data_dir, now=now)
    assert "bad" not in result["stripped"]
    assert "bad" not in result["deleted"]
    # session dir survives, since we can't know its age
    assert sdir.exists()


def test_missing_data_dir_returns_empty(tmp_path):
    """No data_dir contents at all — should return empty summary, not raise."""
    result = run_gc(data_dir=tmp_path, now=datetime.now(UTC))
    assert result["stripped"] == [] and result["deleted"] == []


def test_summary_has_counts(plugin_data_dir):
    now = datetime(2026, 6, 1, tzinfo=UTC)
    _seed_session(plugin_data_dir, "a", ts_end_days_ago=60, now=now)
    _seed_session(plugin_data_dir, "b", ts_end_days_ago=400, now=now)
    _seed_session(plugin_data_dir, "c", ts_end_days_ago=5, now=now)
    result = run_gc(data_dir=plugin_data_dir, now=now)
    assert result["stripped_count"] == 1
    assert result["deleted_count"] == 1
    assert result["untouched_count"] == 1
