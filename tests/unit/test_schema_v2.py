"""Schema v2 contract tests (DESIGN_FORENSIC_UX §6).

Covers:
  - events.jsonl carries v2 fields when present, omits them when not
  - metadata.json migrates v1→v2 on first append
  - reader continues to handle v1 events without v2 fields
  - core/indexer builds and reloads
"""

from __future__ import annotations

import hashlib
import json

from core.indexer import build_index, get_or_build, index_path, load_index
from core.recorder import EVENT_SCHEMA_VERSION, METADATA_SCHEMA_VERSION, append_event
from core.session_io import load_events


def _event(**over):
    base = {
        "v": 1,
        "engine": "claude-code",
        "event_type": "user_prompt",
        "session_id": "Sv2",
        "ts": "2026-05-15T10:00:00.000+00:00",
        "cwd": "/proj",
        "user_prompt_text": "hello v2",
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


def test_event_carries_v2_stamp(plugin_data_dir):
    append_event(_event())
    events = load_events("Sv2", data_dir=plugin_data_dir)
    assert events[0]["v"] == EVENT_SCHEMA_VERSION == 2


def test_correlation_id_anchors_on_user_prompt(plugin_data_dir):
    """A user_prompt mints a fresh correlation id; the next non-prompt
    event reuses it; a second user_prompt rotates it."""
    append_event(_event(event_type="user_prompt", ts="2026-05-15T10:00:00.000+00:00"))
    append_event(
        _event(
            event_type="pre_tool",
            ts="2026-05-15T10:00:01.000+00:00",
            tool_name="Read",
        )
    )
    append_event(_event(event_type="user_prompt", ts="2026-05-15T10:00:02.000+00:00"))
    events = load_events("Sv2", data_dir=plugin_data_dir)
    c0, c1, c2 = (e["correlation_id"] for e in events[:3])
    assert c0 == c1
    assert c2 != c0


def test_codex_turn_id_takes_precedence(plugin_data_dir):
    """If the event carries a turn_id (Codex), correlation_id mirrors it."""
    append_event(
        _event(
            engine="codex",
            event_type="user_prompt",
            session_id="Sv2",
            turn_id="codex-turn-7",
        )
    )
    events = load_events("Sv2", data_dir=plugin_data_dir)
    assert events[0]["correlation_id"] == "codex-turn-7"


def test_post_tool_response_sha_and_size(plugin_data_dir):
    body = "the response body"
    expected = hashlib.sha256(body.encode("utf-8")).hexdigest()
    append_event(
        _event(
            event_type="post_tool",
            tool_name="Read",
            tool_response=body,
            result_bytes=len(body.encode("utf-8")),
        )
    )
    events = load_events("Sv2", data_dir=plugin_data_dir)
    assert events[0]["response_sha256"] == expected
    assert events[0]["response_size_bytes"] == len(body.encode("utf-8"))


def test_metadata_v2_anomaly_counters_initialised(plugin_data_dir):
    append_event(_event())
    meta = json.loads(
        (plugin_data_dir / "sessions" / "Sv2" / "metadata.json").read_text()
    )
    assert meta["v"] == METADATA_SCHEMA_VERSION == 2
    assert meta["anomaly_counters"] == {
        "unmentioned_reads": 0,
        "repeated_reads": 0,
        "hallucination_candidates": 0,
        "glob_burst": 0,
        "routing_thrash": 0,
        "large_read": 0,
    }
    assert meta["notes_count"] == 0
    assert meta["findings"] == []
    assert meta["tokens_total"] == {
        "input": 0,
        "output": 0,
        "cache_read": 0,
        "cache_creation": 0,
    }
    # cwd_hash is set from cwd on first event
    assert meta["cwd_hash"] == hashlib.sha256(b"/proj").hexdigest()


def test_metadata_accumulates_tokens(plugin_data_dir):
    append_event(
        _event(
            event_type="agent_response",
            tokens={"input": 100, "output": 50, "cache_read": 20, "cache_creation": 0},
        )
    )
    append_event(
        _event(
            event_type="agent_response",
            tokens={"input": 7, "output": 3, "cache_read": 1, "cache_creation": 0},
        )
    )
    meta = json.loads(
        (plugin_data_dir / "sessions" / "Sv2" / "metadata.json").read_text()
    )
    assert meta["tokens_total"] == {
        "input": 107,
        "output": 53,
        "cache_read": 21,
        "cache_creation": 0,
    }


def test_v1_metadata_migrated_in_place(plugin_data_dir, monkeypatch):
    # Seed with a v1-shaped metadata.json by hand and let recorder upgrade it.
    sdir = plugin_data_dir / "sessions" / "Sv2"
    sdir.mkdir(parents=True)
    (sdir / "metadata.json").write_text(
        json.dumps(
            {
                "v": 1,
                "session_id": "Sv2",
                "engine": "claude-code",
                "ts_start": "2026-05-14T10:00:00.000+00:00",
                "ts_end": "2026-05-14T10:00:00.000+00:00",
                "cwd": "/proj",
                "tool_calls_total": 0,
                "user_prompts_count": 0,
                "agent_responses_count": 0,
                "unique_files_read": 0,
                "total_bytes_read": 0,
                "tags": [],
            }
        )
    )
    append_event(_event())
    meta = json.loads((sdir / "metadata.json").read_text())
    assert meta["v"] == 2
    assert "anomaly_counters" in meta
    assert meta["cwd_hash"] == hashlib.sha256(b"/proj").hexdigest()


def test_hook_self_ms_recorded(plugin_data_dir):
    append_event(_event())
    events = load_events("Sv2", data_dir=plugin_data_dir)
    assert "hook_self_ms" in events[0]
    assert events[0]["hook_self_ms"] >= 0


# --- adapter pass-through ---


def test_claude_adapter_surfaces_v2_fields():
    from adapters.claude_code import normalize_event

    raw = {
        "session_id": "abc",
        "hook_event_name": "Stop",
        "last_assistant_message": "done",
        "engine_version": "claude-code/2.0.42",
        "permission_mode": "default",
        "tool_use_id": "toolu_01abc",
        "usage": {"input_tokens": 1234, "output_tokens": 200},
        "parent_session_id": "parent-uuid",
        "duration_ms": 4200,
    }
    out = normalize_event(raw)
    assert out is not None
    assert out["engine_version"] == "claude-code/2.0.42"
    assert out["permission_mode"] == "default"
    assert out["tool_use_id"] == "toolu_01abc"
    assert out["tokens"]["input"] == 1234
    assert out["tokens"]["output"] == 200
    assert out["parent_session_id"] == "parent-uuid"
    assert out["duration_ms"] == 4200


def test_codex_adapter_surfaces_v2_fields():
    from adapters.codex import normalize_event

    raw = {
        "session_id": "cdx-99",
        "hook_event_name": "stop",
        "cwd": "/p",
        "model": "gpt-5",
        "permission_mode": "acceptEdits",
        "transcript_path": "/tmp/c.jsonl",
        "engine_version": "codex/0.129",
        "tool_use_id": "tu-1",
        "last_assistant_message": "done",
        "turn_id": "t-9",
        "tokens": {"input": 5, "output": 6},
    }
    out = normalize_event(raw)
    assert out is not None
    assert out["engine_version"] == "codex/0.129"
    assert out["permission_mode"] == "acceptEdits"
    assert out["tool_use_id"] == "tu-1"
    assert out["tokens"]["input"] == 5
    assert out["turn_id"] == "t-9"


# --- indexer ---


def _seed_session(data_dir, sid="idxsess"):
    append_event(
        _event(session_id=sid, event_type="user_prompt", user_prompt_text="explore foo.md"),
        data_dir=data_dir,
    )
    append_event(
        _event(
            session_id=sid,
            event_type="post_tool",
            tool_name="Read",
            paths=["/p/foo.md"],
            tool_response="lorem ipsum hello world",
            result_bytes=23,
            ts="2026-05-15T10:01:00.000+00:00",
        ),
        data_dir=data_dir,
    )
    append_event(
        _event(
            session_id=sid,
            event_type="agent_response",
            agent_response_text="I read lorem ipsum hello world from foo.md",
            ts="2026-05-15T10:02:00.000+00:00",
        ),
        data_dir=data_dir,
    )


def test_indexer_builds_and_persists(plugin_data_dir):
    _seed_session(plugin_data_dir)
    idx = build_index("idxsess", data_dir=plugin_data_dir)
    assert idx["v"] == 2
    assert idx["session_id"] == "idxsess"
    # The Read's tool_response is content-addressed
    sha = hashlib.sha256(b"lorem ipsum hello world").hexdigest()
    assert sha in idx["content_hash_to_events"]
    # path_first_seen points at the post_tool event (index 1)
    assert idx["path_first_seen"]["/p/foo.md"] == 1
    # phrase_to_first_agent_event indexes the agent_response (index 2)
    assert "lorem ipsum hello" in idx["phrase_to_first_agent_event"]
    assert idx["phrase_to_first_agent_event"]["lorem ipsum hello"] == 2
    # bigram_inverted is non-empty
    assert len(idx["bigram_inverted"]) > 0


def test_indexer_caches_and_reloads(plugin_data_dir):
    _seed_session(plugin_data_dir)
    first = build_index("idxsess", data_dir=plugin_data_dir)
    cached = load_index("idxsess", data_dir=plugin_data_dir)
    assert cached == first
    # get_or_build returns the cached structure without re-walking
    same = get_or_build("idxsess", data_dir=plugin_data_dir)
    assert same["session_id"] == first["session_id"]


def test_index_path_rejects_unsafe_session_id(plugin_data_dir):
    import pytest

    with pytest.raises(ValueError):
        index_path("../escape", data_dir=plugin_data_dir)
