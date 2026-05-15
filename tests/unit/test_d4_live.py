"""D-4 Live UX tests: follower + tail."""

from __future__ import annotations

import io
import json
import threading
import time

from core.follower import follow_events
from core.recorder import append_event
from query.tail import tail


def _event(**over):
    base = {
        "v": 1,
        "engine": "claude-code",
        "event_type": "user_prompt",
        "session_id": "live1",
        "ts": "2026-05-15T10:00:00.000+00:00",
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
    }
    base.update(over)
    return base


def test_follow_events_from_start_picks_up_existing(plugin_data_dir):
    """Pre-populate events, then ensure follow_events(from_start=True)
    yields them before bailing on stop_after_seconds."""
    append_event(_event(), data_dir=plugin_data_dir)
    append_event(
        _event(user_prompt_text="second", ts="2026-05-15T10:00:01.000+00:00"),
        data_dir=plugin_data_dir,
    )
    collected = list(
        follow_events(
            "live1",
            data_dir=plugin_data_dir,
            from_start=True,
            poll_interval=0.05,
            stop_after_seconds=0.2,
        )
    )
    assert len(collected) == 2
    assert collected[0]["user_prompt_text"] == "hi"
    assert collected[1]["user_prompt_text"] == "second"


def test_follow_events_tail_only_skips_existing(plugin_data_dir):
    append_event(_event(user_prompt_text="old"), data_dir=plugin_data_dir)
    collected = list(
        follow_events(
            "live1",
            data_dir=plugin_data_dir,
            from_start=False,
            poll_interval=0.05,
            stop_after_seconds=0.2,
        )
    )
    assert collected == []


def test_follow_events_picks_up_appended_during_loop(plugin_data_dir):
    """Start following in a thread, append two events, verify they're
    surfaced."""
    append_event(_event(user_prompt_text="initial"), data_dir=plugin_data_dir)
    collected: list[dict] = []
    done = threading.Event()

    def follower():
        for ev in follow_events(
            "live1",
            data_dir=plugin_data_dir,
            from_start=False,
            poll_interval=0.05,
            stop_after_seconds=1.0,
        ):
            collected.append(ev)
        done.set()

    t = threading.Thread(target=follower)
    t.start()
    time.sleep(0.15)
    append_event(
        _event(user_prompt_text="late-1", ts="2026-05-15T10:01:00.000+00:00"),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(user_prompt_text="late-2", ts="2026-05-15T10:01:01.000+00:00"),
        data_dir=plugin_data_dir,
    )
    done.wait(timeout=2.0)
    bodies = [c["user_prompt_text"] for c in collected]
    assert "late-1" in bodies
    assert "late-2" in bodies


def test_tail_text_format(plugin_data_dir):
    append_event(_event(), data_dir=plugin_data_dir)
    buf = io.StringIO()
    tail(
        "live1",
        data_dir=plugin_data_dir,
        fmt="text",
        from_start=True,
        poll_interval=0.05,
        stop_after_seconds=0.2,
        stream=buf,
    )
    out = buf.getvalue()
    assert "user_prompt" in out


def test_tail_stream_json_format(plugin_data_dir):
    append_event(_event(), data_dir=plugin_data_dir)
    append_event(
        _event(
            event_type="agent_response",
            agent_response_text="done",
            ts="2026-05-15T10:00:02.000+00:00",
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    n = tail(
        "live1",
        data_dir=plugin_data_dir,
        fmt="stream-json",
        from_start=True,
        poll_interval=0.05,
        stop_after_seconds=0.2,
        stream=buf,
    )
    assert n == 2
    lines = [json.loads(line) for line in buf.getvalue().splitlines() if line]
    assert len(lines) == 2
    assert lines[0]["event_type"] == "user_prompt"
    assert lines[1]["event_type"] == "agent_response"


def test_follow_recovers_from_shrunken_file(plugin_data_dir):
    """If events.jsonl shrinks (file rotation / external truncate),
    follower resets position and starts re-reading. We verify the reset
    path by truncating to a known smaller-than-position state."""
    append_event(_event(user_prompt_text="x"), data_dir=plugin_data_dir)
    append_event(
        _event(user_prompt_text="y", ts="2026-05-15T10:00:01.000+00:00"),
        data_dir=plugin_data_dir,
    )
    events_file = plugin_data_dir / "sessions" / "live1" / "events.jsonl"
    # Snapshot the first line and truncate to just that line — the
    # follower's `position` (at end of two lines) becomes greater than
    # the file size, triggering the reset path.
    full = events_file.read_text()
    first_line = full.split("\n", 1)[0] + "\n"

    collected: list[dict] = []
    done = threading.Event()

    def follower():
        for ev in follow_events(
            "live1",
            data_dir=plugin_data_dir,
            from_start=False,
            poll_interval=0.05,
            stop_after_seconds=0.6,
        ):
            collected.append(ev)
        done.set()

    t = threading.Thread(target=follower)
    t.start()
    time.sleep(0.15)
    events_file.write_text(first_line)
    done.wait(timeout=1.5)
    # After shrink, follower re-reads from byte 0; it should at least
    # surface that first line again.
    assert any(c.get("user_prompt_text") == "x" for c in collected)
