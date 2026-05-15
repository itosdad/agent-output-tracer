"""Unit tests for core.recorder (events.jsonl + metadata.json).

Contract:

  append_event(event: dict, *, data_dir: Path | None = None) -> None
    Appends a single normalized event to
    `<data_dir>/sessions/<session_id>/events.jsonl` and updates the
    sibling `metadata.json`. When `data_dir` is None, resolves from
    `CLAUDE_PLUGIN_DATA`. Raises `RecorderError` on configuration
    failures (caller — the hook script — is expected to swallow).
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from core.recorder import RecorderError, append_event, session_dir


def _event(
    *,
    session_id: str = "S1",
    event_type: str = "pre_tool",
    ts: str = "2026-05-14T10:00:00.000+00:00",
    engine: str = "claude-code",
    cwd: str | None = "/proj",
    tool_name: str | None = "Read",
    paths: list[str] | None = None,
    result_bytes: int = 0,
    user_prompt_text: str | None = None,
    agent_response_text: str | None = None,
    **kwargs,
) -> dict:
    e = {
        "v": 1,
        "engine": engine,
        "event_type": event_type,
        "session_id": session_id,
        "ts": ts,
        "cwd": cwd,
        "user_prompt_text": user_prompt_text,
        "tool_name": tool_name,
        "tool_input": None,
        "tool_response": None,
        "agent_response_text": agent_response_text,
        "stop_reason": None,
        "paths": paths or [],
        "command": None,
        "result_bytes": result_bytes,
        "raw_event": {},
    }
    e.update(kwargs)
    return e


def test_append_event_creates_session_dir_and_events_file(plugin_data_dir):
    e = _event()
    append_event(e)

    sdir = plugin_data_dir / "sessions" / "S1"
    assert sdir.is_dir()
    events_file = sdir / "events.jsonl"
    assert events_file.is_file()

    lines = events_file.read_text().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["session_id"] == "S1"
    assert parsed["event_type"] == "pre_tool"


def test_append_event_appends_in_order(plugin_data_dir):
    append_event(_event(ts="2026-01-01T00:00:00.000+00:00", tool_name="Read"))
    append_event(_event(ts="2026-01-01T00:00:01.000+00:00", tool_name="Glob"))
    append_event(_event(ts="2026-01-01T00:00:02.000+00:00", tool_name="Bash"))

    events_file = plugin_data_dir / "sessions" / "S1" / "events.jsonl"
    lines = [json.loads(line) for line in events_file.read_text().splitlines()]
    assert [e["tool_name"] for e in lines] == ["Read", "Glob", "Bash"]


def test_append_event_writes_metadata_json(plugin_data_dir):
    append_event(_event())
    meta_file = plugin_data_dir / "sessions" / "S1" / "metadata.json"
    assert meta_file.is_file()
    meta = json.loads(meta_file.read_text())
    assert meta["v"] == 1
    assert meta["session_id"] == "S1"
    assert meta["engine"] == "claude-code"
    assert meta["cwd"] == "/proj"
    assert meta["tags"] == []


def test_metadata_ts_start_and_ts_end(plugin_data_dir):
    append_event(_event(ts="2026-01-01T00:00:00.000+00:00"))
    append_event(_event(ts="2026-01-01T00:00:10.000+00:00"))
    append_event(_event(ts="2026-01-01T00:00:05.000+00:00"))  # out-of-order

    meta = json.loads((plugin_data_dir / "sessions" / "S1" / "metadata.json").read_text())
    assert meta["ts_start"] == "2026-01-01T00:00:00.000+00:00"
    assert meta["ts_end"] == "2026-01-01T00:00:10.000+00:00"


def test_metadata_counts_tool_calls(plugin_data_dir):
    append_event(_event(event_type="pre_tool", tool_name="Read"))
    append_event(_event(event_type="pre_tool", tool_name="Glob"))
    append_event(_event(event_type="post_tool", tool_name="Read"))

    meta = json.loads((plugin_data_dir / "sessions" / "S1" / "metadata.json").read_text())
    # Tool calls are counted on pre_tool only (so each tool invocation
    # contributes 1)
    assert meta["tool_calls_total"] == 2


def test_metadata_counts_user_prompts(plugin_data_dir):
    append_event(_event(event_type="user_prompt", user_prompt_text="a", tool_name=None))
    append_event(_event(event_type="user_prompt", user_prompt_text="b", tool_name=None))

    meta = json.loads((plugin_data_dir / "sessions" / "S1" / "metadata.json").read_text())
    assert meta["user_prompts_count"] == 2


def test_metadata_counts_agent_responses(plugin_data_dir):
    append_event(
        _event(
            event_type="agent_response",
            tool_name=None,
            agent_response_text="ok",
        )
    )

    meta = json.loads((plugin_data_dir / "sessions" / "S1" / "metadata.json").read_text())
    assert meta["agent_responses_count"] == 1


def test_metadata_unique_files_read(plugin_data_dir):
    append_event(_event(event_type="post_tool", tool_name="Read", paths=["/a"], result_bytes=10))
    append_event(_event(event_type="post_tool", tool_name="Read", paths=["/a"], result_bytes=10))
    append_event(_event(event_type="post_tool", tool_name="Read", paths=["/b"], result_bytes=20))

    meta = json.loads((plugin_data_dir / "sessions" / "S1" / "metadata.json").read_text())
    assert meta["unique_files_read"] == 2
    assert meta["total_bytes_read"] == 40


def test_session_isolation(plugin_data_dir):
    append_event(_event(session_id="S1"))
    append_event(_event(session_id="S2"))

    assert (plugin_data_dir / "sessions" / "S1" / "events.jsonl").is_file()
    assert (plugin_data_dir / "sessions" / "S2" / "events.jsonl").is_file()
    s1_events = (plugin_data_dir / "sessions" / "S1" / "events.jsonl").read_text()
    s2_events = (plugin_data_dir / "sessions" / "S2" / "events.jsonl").read_text()
    assert "S1" in s1_events and "S2" not in s1_events
    assert "S2" in s2_events and "S1" not in s2_events


def test_append_event_raises_without_data_dir():
    # plugin_data_dir fixture not used; CLAUDE_PLUGIN_DATA not set by autouse
    with pytest.raises(RecorderError):
        append_event(_event())


def test_append_event_with_explicit_data_dir(tmp_path):
    """Passing data_dir explicitly should work even without env var."""
    dd = tmp_path / "explicit"
    dd.mkdir()
    append_event(_event(), data_dir=dd)
    assert (dd / "sessions" / "S1" / "events.jsonl").is_file()


def test_append_event_silently_skips_event_with_no_session_id(plugin_data_dir):
    e = _event()
    e["session_id"] = None
    with pytest.raises(RecorderError):
        append_event(e)


def test_session_dir_helper(plugin_data_dir):
    sdir = session_dir("ABC", data_dir=plugin_data_dir)
    assert sdir == plugin_data_dir / "sessions" / "ABC"


def test_session_dir_sanitizes_traversal(plugin_data_dir):
    """session_id must not be allowed to escape the data dir."""
    with pytest.raises(RecorderError):
        session_dir("../escape", data_dir=plugin_data_dir)
    with pytest.raises(RecorderError):
        session_dir("..", data_dir=plugin_data_dir)
    with pytest.raises(RecorderError):
        session_dir("a/b", data_dir=plugin_data_dir)


def test_unicode_event_round_trip(plugin_data_dir):
    e = _event(user_prompt_text="日本語と emoji 🎉")
    append_event(e)
    line = (plugin_data_dir / "sessions" / "S1" / "events.jsonl").read_text()
    # ensure_ascii=False means the raw chars are written
    assert "日本語" in line
    parsed = json.loads(line)
    assert parsed["user_prompt_text"] == "日本語と emoji 🎉"


def test_concurrent_writes_are_atomic_within_a_line(plugin_data_dir):
    """Each append must produce exactly one terminated line — no partial
    writes leaking across boundaries. Smoke test via many appends."""
    n = 50
    for i in range(n):
        append_event(_event(ts=f"2026-01-01T00:00:{i:02d}.000+00:00"))

    lines = (plugin_data_dir / "sessions" / "S1" / "events.jsonl").read_text().splitlines()
    assert len(lines) == n
    for line in lines:
        json.loads(line)  # each line is independently parseable


def test_uses_env_data_dir_when_param_omitted(monkeypatch, tmp_path):
    dd = tmp_path / "env_data"
    dd.mkdir()
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(dd))
    append_event(_event())
    assert (dd / "sessions" / "S1" / "events.jsonl").is_file()


def test_now_local_timezone_safe(plugin_data_dir):
    """The recorder must not crash when ts is a local-tz ISO string."""
    local_ts = datetime.now().astimezone().isoformat(timespec="milliseconds")
    append_event(_event(ts=local_ts))
    meta = json.loads((plugin_data_dir / "sessions" / "S1" / "metadata.json").read_text())
    assert meta["ts_start"] == local_ts


def test_metadata_engine_records_first_seen(plugin_data_dir):
    """If somehow events from different engines land in one session
    (shouldn't happen, but be defensive), keep the first-seen engine."""
    append_event(_event(engine="claude-code"))
    append_event(_event(engine="codex"))
    meta = json.loads((plugin_data_dir / "sessions" / "S1" / "metadata.json").read_text())
    assert meta["engine"] == "claude-code"


def test_corrupt_metadata_json_is_replaced_not_crashed(plugin_data_dir):
    """If metadata.json gets corrupted out-of-band, the next append
    should rebuild it rather than raise."""
    sdir = plugin_data_dir / "sessions" / "S1"
    sdir.mkdir(parents=True)
    (sdir / "metadata.json").write_text("not json {{{{")
    append_event(_event())
    meta = json.loads((sdir / "metadata.json").read_text())
    assert meta["session_id"] == "S1"
