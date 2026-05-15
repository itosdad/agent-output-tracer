"""D-7 Safe-share export tests."""

from __future__ import annotations

import io
import json
import zipfile

from core.recorder import append_event
from core.sanitiser import render_safe_markdown, sanitise_session
from query.export import export_safe_share


def _event(**over):
    base = {
        "v": 1,
        "engine": "claude-code",
        "event_type": "user_prompt",
        "session_id": "share-1234567890",
        "ts": "2026-05-15T10:00:00.000+00:00",
        "cwd": "/Users/somebody/work/myproj",
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


def _seed(data_dir):
    append_event(
        _event(
            user_prompt_text="please email me at alice@example.com",
        ),
        data_dir=data_dir,
    )
    append_event(
        _event(
            event_type="post_tool",
            tool_name="Read",
            paths=["/Users/somebody/work/myproj/src/auth.py"],
            tool_response="def login(): return SECRET_BODY_DO_NOT_LEAK",
            ts="2026-05-15T10:00:01.000+00:00",
        ),
        data_dir=data_dir,
    )
    append_event(
        _event(
            event_type="agent_response",
            agent_response_text="I read /Users/somebody/work/myproj/src/auth.py",
            ts="2026-05-15T10:00:02.000+00:00",
        ),
        data_dir=data_dir,
    )


# --- sanitiser ---


def test_sanitiser_strips_cwd_and_email():
    events = [
        {
            "session_id": "abcdefghij",
            "event_type": "user_prompt",
            "user_prompt_text": "ping alice@example.com about /Users/x/work/myproj/notes.md",
            "cwd": "/Users/x/work/myproj",
            "paths": ["/Users/x/work/myproj/notes.md"],
            "tool_name": None,
            "tool_response": None,
            "raw_event": {},
        }
    ]
    out_events, meta = sanitise_session(events, {"cwd": "/Users/x/work/myproj", "session_id": "abcdefghij"})
    assert "<EMAIL>" in out_events[0]["user_prompt_text"]
    assert "<repo>" in out_events[0]["user_prompt_text"]
    assert out_events[0]["paths"] == ["<repo>/notes.md"]
    # cwd removed from metadata
    assert "cwd" not in meta
    # session_id shortened
    assert out_events[0]["session_id"] == "abcdefgh"


def test_sanitiser_strips_tool_response_by_default():
    events = [
        {
            "session_id": "x",
            "event_type": "post_tool",
            "tool_name": "Read",
            "paths": ["/p/x.md"],
            "tool_response": "SECRET_BODY",
            "response_sha256": "abc",
            "response_size_bytes": 11,
            "raw_event": {},
        }
    ]
    out_events, _ = sanitise_session(events, None)
    assert out_events[0]["tool_response"] == ""
    # sha + size still surface for forensic value
    assert out_events[0]["response_sha256"] == "abc"
    assert out_events[0]["response_size_bytes"] == 11


def test_sanitiser_keeps_excerpt_when_requested():
    events = [
        {
            "session_id": "x",
            "event_type": "post_tool",
            "tool_name": "Read",
            "paths": ["/p/x.md"],
            "tool_response": "hello world this is a long body",
            "raw_event": {},
        }
    ]
    out_events, _ = sanitise_session(events, None, keep_excerpt=11)
    assert out_events[0]["tool_response"] == "hello world"


def test_sanitiser_strips_long_hex_tokens():
    events = [
        {
            "session_id": "x",
            "event_type": "user_prompt",
            "user_prompt_text": "the hash is 0123456789abcdef0123456789abcdef",
            "raw_event": {},
        }
    ]
    out, _ = sanitise_session(events, None)
    assert "<HEX>" in out[0]["user_prompt_text"]


# --- render_safe_markdown ---


def test_render_safe_markdown_has_timeline_section():
    events = [
        {
            "ts": "2026-05-15T10:00:00.000+00:00",
            "event_type": "user_prompt",
            "user_prompt_text": "hello",
            "paths": [],
            "tool_name": None,
        }
    ]
    md = render_safe_markdown(events, {"session_id": "abcdefgh"})
    assert "## Timeline" in md
    assert "user" in md.lower()


# --- export_safe_share CLI integration shape ---


def test_export_safe_share_markdown(plugin_data_dir):
    _seed(plugin_data_dir)
    buf = io.StringIO()
    result = export_safe_share(
        "share-1234567890",
        data_dir=plugin_data_dir,
        fmt="markdown",
        stream=buf,
    )
    out = buf.getvalue()
    # cwd absolute path must be gone, replaced with abstracted form
    assert "/Users/somebody/work/myproj" not in out
    # email scrubbed
    assert "alice@example.com" not in out
    # secret body stripped
    assert "SECRET_BODY_DO_NOT_LEAK" not in out
    assert result["events"] == 3


def test_export_safe_share_json(plugin_data_dir):
    _seed(plugin_data_dir)
    buf = io.StringIO()
    export_safe_share(
        "share-1234567890",
        data_dir=plugin_data_dir,
        fmt="json",
        keep_excerpt=20,
        stream=buf,
    )
    payload = json.loads(buf.getvalue())
    assert "metadata" in payload
    assert "events" in payload
    # cwd metadata removed
    assert "cwd" not in payload["metadata"]
    # tool_response excerpt limited (and sanitised)
    post = [e for e in payload["events"] if e["event_type"] == "post_tool"][0]
    assert len(post["tool_response"]) <= 20
    assert "SECRET_BODY_DO_NOT_LEAK" not in post["tool_response"]


def test_export_safe_share_archive_writes_zip(plugin_data_dir, tmp_path):
    _seed(plugin_data_dir)
    out = tmp_path / "bundle.zip"
    result = export_safe_share(
        "share-1234567890",
        data_dir=plugin_data_dir,
        fmt="archive",
        output_path=out,
    )
    assert out.is_file()
    assert result["archive_path"] == str(out)
    with zipfile.ZipFile(out) as zf:
        names = set(zf.namelist())
        assert {"metadata.json", "events.jsonl", "REPORT.md"} <= names
        report = zf.read("REPORT.md").decode("utf-8")
        assert "/Users/somebody/work/myproj" not in report


def test_export_safe_share_archive_requires_output(plugin_data_dir):
    _seed(plugin_data_dir)
    import pytest

    with pytest.raises(ValueError):
        export_safe_share(
            "share-1234567890",
            data_dir=plugin_data_dir,
            fmt="archive",
            output_path=None,
        )
