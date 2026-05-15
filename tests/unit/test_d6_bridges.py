"""D-6 Bridges tests: engine_log overlay, otel_export span model,
global_index build, review command."""

from __future__ import annotations

import hashlib
import io
import json

from bridges.engine_log import (
    claude_debug_log_path,
    load_overlay,
    merge_with_events,
)
from bridges.otel_export import build_spans, is_available
from core.global_index import build_or_refresh, load_global_index
from core.recorder import append_event
from query.review import review

# --- engine_log ---


def test_claude_debug_log_path_honors_env(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_CODE_DEBUG_LOGS_DIR", str(tmp_path))
    p = claude_debug_log_path("abc-123")
    assert p == tmp_path / "abc-123.txt"


def test_claude_debug_log_path_default(monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_DEBUG_LOGS_DIR", raising=False)
    p = claude_debug_log_path("abc-123")
    assert str(p).endswith(".claude/debug/abc-123.txt")


def test_load_overlay_returns_empty_when_file_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_CODE_DEBUG_LOGS_DIR", str(tmp_path))
    assert load_overlay("does-not-exist") == []


def test_load_overlay_extracts_timestamps(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_CODE_DEBUG_LOGS_DIR", str(tmp_path))
    (tmp_path / "sX.txt").write_text(
        "2026-05-15T10:00:00.000+00:00 first line\n"
        "no-timestamp line\n"
        "2026-05-15T10:00:02.500+00:00 third line\n"
    )
    overlay = load_overlay("sX")
    assert overlay[0]["ts"] == "2026-05-15T10:00:00.000+00:00"
    assert overlay[1]["ts"] is None
    assert overlay[2]["ts"] == "2026-05-15T10:00:02.500+00:00"


def test_merge_orders_by_ts():
    events = [
        {"ts": "2026-05-15T10:00:01.000+00:00", "event_type": "user_prompt"},
        {"ts": "2026-05-15T10:00:03.000+00:00", "event_type": "agent_response"},
    ]
    overlay = [
        {"ts": "2026-05-15T10:00:00.000+00:00", "line": "engine startup"},
        {"ts": "2026-05-15T10:00:02.000+00:00", "line": "permission check"},
    ]
    merged = merge_with_events(events, overlay)
    assert [m.get("_source") for m in merged] == [
        "engine_log",
        "event",
        "engine_log",
        "event",
    ]


# --- otel_export model (no SDK required) ---


def test_build_spans_default_redacts_prompts_and_responses():
    events = [
        {
            "ts": "2026-05-15T10:00:00.000+00:00",
            "event_type": "user_prompt",
            "user_prompt_text": "SECRET_PROMPT",
            "correlation_id": "c1",
        },
        {
            "ts": "2026-05-15T10:00:01.000+00:00",
            "event_type": "pre_tool",
            "tool_name": "Read",
            "paths": ["/p/a.md"],
            "correlation_id": "c1",
        },
        {
            "ts": "2026-05-15T10:00:02.000+00:00",
            "event_type": "post_tool",
            "tool_name": "Read",
            "paths": ["/p/a.md"],
            "tool_response": "SECRET_BODY",
            "response_sha256": "abc",
            "response_size_bytes": 11,
            "correlation_id": "c1",
        },
        {
            "ts": "2026-05-15T10:00:03.000+00:00",
            "event_type": "agent_response",
            "agent_response_text": "done",
            "correlation_id": "c1",
        },
    ]
    spans = build_spans(events, {"session_id": "sX", "engine": "claude-code"})
    serialized = json.dumps(spans)
    assert "SECRET_PROMPT" not in serialized
    assert "SECRET_BODY" not in serialized
    names = [s["name"] for s in spans]
    assert names[0] == "aot.session"
    assert "aot.turn" in names
    assert names.count("aot.tool") == 2


def test_build_spans_can_opt_in_to_prompt_logging():
    events = [
        {
            "ts": "2026-05-15T10:00:00.000+00:00",
            "event_type": "user_prompt",
            "user_prompt_text": "VISIBLE_BY_OPT_IN",
            "correlation_id": "c1",
        }
    ]
    spans = build_spans(events, {"session_id": "s"}, log_user_prompt=True)
    serialized = json.dumps(spans)
    assert "VISIBLE_BY_OPT_IN" in serialized


def test_build_spans_includes_findings():
    spans = build_spans(
        events=[],
        metadata={
            "session_id": "s",
            "findings": [
                {"kind": "bisect_first_bad", "event_idx": 7, "steps": 3, "ts": "x"}
            ],
        },
    )
    finding_spans = [s for s in spans if s["name"] == "aot.finding"]
    assert len(finding_spans) == 1
    assert finding_spans[0]["attributes"]["kind"] == "bisect_first_bad"


def test_otel_is_available_matches_import():
    try:
        import opentelemetry  # noqa: F401
        from opentelemetry.sdk.trace import TracerProvider  # noqa: F401
    except ImportError:
        assert is_available() is False
    else:
        assert is_available() is True


# --- global_index ---


def _event(**over):
    base = {
        "v": 1,
        "engine": "claude-code",
        "event_type": "user_prompt",
        "session_id": "g1",
        "ts": "2026-05-15T10:00:00.000+00:00",
        "cwd": "/p",
        "user_prompt_text": "explore",
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


def test_global_index_aggregates_paths_and_shas(plugin_data_dir):
    for sid in ("sA", "sB"):
        append_event(_event(session_id=sid), data_dir=plugin_data_dir)
        append_event(
            _event(
                session_id=sid,
                event_type="post_tool",
                tool_name="Read",
                paths=["/p/shared.md"],
                tool_response="same body for both sessions",
                ts="2026-05-15T10:00:01.000+00:00",
            ),
            data_dir=plugin_data_dir,
        )
    idx = build_or_refresh(data_dir=plugin_data_dir)
    sha = hashlib.sha256(b"same body for both sessions").hexdigest()
    assert "/p/shared.md" in idx["path_cross_index"]
    assert {r["session_id"] for r in idx["path_cross_index"]["/p/shared.md"]} == {"sA", "sB"}
    assert sha in idx["sha_cross_index"]


def test_load_global_index_returns_none_when_missing(plugin_data_dir):
    assert load_global_index(data_dir=plugin_data_dir) is None


# --- review ---


def test_review_summarises_sessions(plugin_data_dir):
    append_event(_event(session_id="r1"), data_dir=plugin_data_dir)
    append_event(_event(session_id="r2", engine="codex"), data_dir=plugin_data_dir)
    buf = io.StringIO()
    result = review(data_dir=plugin_data_dir, stream=buf)
    assert result["$schema"] == "aot/review/v1"
    assert result["sessions_count"] == 2
    assert "claude-code" in result["engines"]
    assert "codex" in result["engines"]


def test_review_filters_by_since(plugin_data_dir):
    append_event(
        _event(
            session_id="old",
            ts="2025-01-01T00:00:00.000+00:00",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            session_id="new",
            ts="2026-05-15T10:00:00.000+00:00",
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = review(
        since="2026-01-01",
        data_dir=plugin_data_dir,
        stream=buf,
    )
    # Only "new" should make it in
    sids = {s["session_id"] for s in result["sessions"]}
    assert "new" in sids
    assert "old" not in sids
