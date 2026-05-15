"""D-3 Causal Core tests: trace --missing / --by-sha, find vocab,
bisect, note, stats."""

from __future__ import annotations

import hashlib
import io
import json

import pytest

from core.recorder import append_event
from query.bisect import (
    BisectError,
    bisect_mark,
    bisect_start,
    bisect_status,
)
from query.find import VOCAB, find
from query.note import note_add, note_list, note_rm
from query.stats import stats
from query.trace import trace_by_sha, trace_missing


def _event(**over):
    base = {
        "v": 1,
        "engine": "claude-code",
        "event_type": "user_prompt",
        "session_id": "D3",
        "ts": "2026-05-15T10:00:00.000+00:00",
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
    base.update(over)
    return base


def _seed_basic(data_dir, sid="D3"):
    """user prompt → Read foo.md → agent response."""
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
            tool_response="content of foo",
            result_bytes=14,
            ts="2026-05-15T10:00:01.000+00:00",
        ),
        data_dir=data_dir,
    )
    append_event(
        _event(
            session_id=sid,
            event_type="agent_response",
            agent_response_text="foo.md has content of foo",
            ts="2026-05-15T10:00:02.000+00:00",
        ),
        data_dir=data_dir,
    )


# ---------- trace --missing ----------


def test_trace_missing_finds_unmentioned_content(plugin_data_dir):
    append_event(
        _event(event_type="user_prompt", user_prompt_text="explain X"), data_dir=plugin_data_dir
    )
    append_event(
        _event(
            event_type="post_tool",
            tool_name="Read",
            paths=["/p/file.md"],
            tool_response="this file mentions IMPORTANT_FACT explicitly",
            ts="2026-05-15T10:01:00.000+00:00",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="agent_response",
            agent_response_text="I read the file, looks fine.",
            ts="2026-05-15T10:02:00.000+00:00",
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = trace_missing("D3", "IMPORTANT_FACT", data_dir=plugin_data_dir, stream=buf)
    assert result["missing"] is True
    assert len(result["appearances"]) == 1
    assert result["appearances"][0]["paths"] == ["/p/file.md"]


def test_trace_missing_clears_when_agent_acknowledges(plugin_data_dir):
    append_event(
        _event(
            event_type="post_tool",
            tool_name="Read",
            paths=["/p/file.md"],
            tool_response="IMPORTANT_FACT here",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="agent_response",
            agent_response_text="Found IMPORTANT_FACT in the file",
            ts="2026-05-15T10:00:01.000+00:00",
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = trace_missing("D3", "IMPORTANT_FACT", data_dir=plugin_data_dir, stream=buf)
    assert result["missing"] is False
    assert result["downstream_agent_mention_idx"] == 1


def test_trace_missing_respects_reference_paths(plugin_data_dir):
    append_event(
        _event(
            event_type="post_tool",
            tool_name="Read",
            paths=["/p/wrong.md"],
            tool_response="FACT in wrong file",
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = trace_missing(
        "D3",
        "FACT",
        reference_paths=["/p/right.md"],
        data_dir=plugin_data_dir,
        stream=buf,
    )
    # Path filter excluded the only appearance
    assert result["appearances"] == []
    assert result["missing"] is False


# ---------- trace --by-sha ----------


def test_trace_by_sha_finds_matching_event(plugin_data_dir):
    body = "alpha beta gamma"
    sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    append_event(
        _event(
            event_type="post_tool",
            tool_name="Read",
            paths=["/p/a.md"],
            tool_response=body,
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = trace_by_sha("D3", sha, data_dir=plugin_data_dir, stream=buf)
    assert len(result["matches"]) == 1
    assert result["matches"][0]["paths"] == ["/p/a.md"]


def test_trace_by_sha_no_match(plugin_data_dir):
    _seed_basic(plugin_data_dir)
    buf = io.StringIO()
    result = trace_by_sha("D3", "0" * 64, data_dir=plugin_data_dir, stream=buf)
    assert result["matches"] == []


# ---------- find vocab ----------


def test_find_vocab_set_matches_design():
    assert set(VOCAB) == {
        "unmentioned-reads",
        "repeated-reads",
        "glob-burst",
        "routing-thrash",
        "large-read",
        "hallucinations",
        "empty-glob",
        "stale-cache",
        "silent-failure",
        "abandoned-write",
    }


def test_find_rejects_unknown_vocab(plugin_data_dir):
    _seed_basic(plugin_data_dir)
    with pytest.raises(ValueError):
        find("D3", "totally-fake", data_dir=plugin_data_dir, stream=io.StringIO())


def test_find_unmentioned_reads(plugin_data_dir):
    """User said 'explore' (no path). Agent Reads /p/secret.md without grounding."""
    append_event(
        _event(event_type="user_prompt", user_prompt_text="explore something"),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="post_tool",
            tool_name="Read",
            paths=["/p/secret.md"],
            tool_response="x",
            ts="2026-05-15T10:00:01.000+00:00",
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = find("D3", "unmentioned-reads", data_dir=plugin_data_dir, stream=buf)
    assert any(m["path"] == "/p/secret.md" for m in result["matches"])


def test_find_hallucinations_time_causality(plugin_data_dir):
    """B1 regression: a user_prompt that arrives AFTER the agent_response
    cannot retroactively ground a path token the agent already named."""
    append_event(
        _event(
            event_type="agent_response",
            ts="2026-05-15T10:00:00.000+00:00",
            agent_response_text="I'll look at /proj/ghost.md",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="user_prompt",
            ts="2026-05-15T10:00:01.000+00:00",
            user_prompt_text="ok then /proj/ghost.md it is",
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = find("D3", "hallucinations", data_dir=plugin_data_dir, stream=buf)
    tokens = [m["token"] for m in result["matches"]]
    assert "/proj/ghost.md" in tokens


def test_find_hallucinations_self_paste_resilience(plugin_data_dir):
    """B2 regression: pasting a prior `aot find` output back into a
    follow-up user_prompt must not silence the detector on the next run."""
    append_event(
        _event(
            event_type="agent_response",
            ts="2026-05-15T10:00:00.000+00:00",
            agent_response_text="I'll check /proj/ghost.md",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="user_prompt",
            ts="2026-05-15T10:00:01.000+00:00",
            user_prompt_text=(
                "find 'hallucinations': 1 match(es)\n"
                "  [10:00:00] event 0 token=/proj/ghost.md\n"
                "explain please"
            ),
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="agent_response",
            ts="2026-05-15T10:00:02.000+00:00",
            agent_response_text="re-reading /proj/ghost.md to recheck",
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = find("D3", "hallucinations", data_dir=plugin_data_dir, stream=buf)
    tokens = [m["token"] for m in result["matches"]]
    assert "/proj/ghost.md" in tokens


def test_find_unmentioned_reads_time_causality(plugin_data_dir):
    """B1 regression: a user_prompt that arrives AFTER the Read cannot
    retroactively ground it. A Read that happened first while the user
    had only said 'explore' must remain flagged."""
    append_event(
        _event(
            event_type="user_prompt",
            ts="2026-05-15T10:00:00.000+00:00",
            user_prompt_text="explore",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="post_tool",
            tool_name="Read",
            paths=["/p/secret.md"],
            tool_response="x",
            ts="2026-05-15T10:00:01.000+00:00",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="user_prompt",
            ts="2026-05-15T10:00:02.000+00:00",
            user_prompt_text="ah you read /p/secret.md, good",
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = find("D3", "unmentioned-reads", data_dir=plugin_data_dir, stream=buf)
    assert any(m["path"] == "/p/secret.md" for m in result["matches"])


def test_find_repeated_reads(plugin_data_dir):
    for i in range(3):
        append_event(
            _event(
                event_type="post_tool",
                tool_name="Read",
                paths=["/p/hot.md"],
                tool_response="x",
                ts=f"2026-05-15T10:00:0{i}.000+00:00",
            ),
            data_dir=plugin_data_dir,
        )
    buf = io.StringIO()
    result = find("D3", "repeated-reads", data_dir=plugin_data_dir, stream=buf)
    assert len(result["matches"]) == 1
    assert result["matches"][0]["count"] == 3


def test_find_large_read(plugin_data_dir):
    append_event(
        _event(
            event_type="post_tool",
            tool_name="Read",
            paths=["/p/huge.txt"],
            tool_response="x" * 60_000,
            result_bytes=60_000,
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = find("D3", "large-read", threshold=50, data_dir=plugin_data_dir, stream=buf)
    assert len(result["matches"]) == 1
    assert result["matches"][0]["size_bytes"] == 60_000


def test_find_stale_cache(plugin_data_dir):
    body = "same content twice"
    for i in range(2):
        append_event(
            _event(
                event_type="post_tool",
                tool_name="Read",
                paths=["/p/cached.md"],
                tool_response=body,
                ts=f"2026-05-15T10:00:0{i}.000+00:00",
            ),
            data_dir=plugin_data_dir,
        )
    buf = io.StringIO()
    result = find("D3", "stale-cache", data_dir=plugin_data_dir, stream=buf)
    assert len(result["matches"]) >= 2


def test_find_abandoned_write(plugin_data_dir):
    append_event(
        _event(
            event_type="pre_tool",
            tool_name="Write",
            paths=["/p/draft.md"],
            ts="2026-05-15T10:00:00.000+00:00",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="pre_tool",
            tool_name="Edit",
            paths=["/p/draft.md"],
            ts="2026-05-15T10:00:01.000+00:00",
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = find("D3", "abandoned-write", data_dir=plugin_data_dir, stream=buf)
    assert len(result["matches"]) == 1


def test_find_empty_glob_then_agent_claims_found(plugin_data_dir):
    append_event(
        _event(
            event_type="post_tool",
            tool_name="Glob",
            tool_input={"pattern": "*.foo"},
            tool_response="",
            ts="2026-05-15T10:00:00.000+00:00",
        ),
        data_dir=plugin_data_dir,
    )
    append_event(
        _event(
            event_type="agent_response",
            agent_response_text="I found the file you mentioned",
            ts="2026-05-15T10:00:01.000+00:00",
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = find("D3", "empty-glob", data_dir=plugin_data_dir, stream=buf)
    assert len(result["matches"]) == 1


# ---------- bisect ----------


def _seed_bisect(data_dir, sid="bsess", n=10):
    for i in range(n):
        append_event(
            _event(
                session_id=sid,
                event_type="user_prompt" if i == 0 else "pre_tool",
                tool_name=None if i == 0 else "Read",
                paths=[] if i == 0 else [f"/p/file{i}.md"],
                ts=f"2026-05-15T10:00:{i:02d}.000+00:00",
            ),
            data_dir=data_dir,
        )


def test_bisect_start_picks_midpoint(plugin_data_dir):
    _seed_bisect(plugin_data_dir, n=11)  # 0..10
    state = bisect_start("bsess", data_dir=plugin_data_dir, stream=io.StringIO())
    assert state["lo"] == 0
    assert state["hi"] == 10
    assert state["candidate"] == 5


def test_bisect_good_advances_lo(plugin_data_dir):
    _seed_bisect(plugin_data_dir, n=11)
    bisect_start("bsess", data_dir=plugin_data_dir, stream=io.StringIO())
    state = bisect_mark("bsess", "good", data_dir=plugin_data_dir, stream=io.StringIO())
    assert state["lo"] == 6


def test_bisect_bad_advances_hi(plugin_data_dir):
    _seed_bisect(plugin_data_dir, n=11)
    bisect_start("bsess", data_dir=plugin_data_dir, stream=io.StringIO())
    state = bisect_mark("bsess", "bad", data_dir=plugin_data_dir, stream=io.StringIO())
    assert state["hi"] == 5


def test_bisect_converges_and_records_finding(plugin_data_dir):
    _seed_bisect(plugin_data_dir, n=4)  # 0,1,2,3 — narrow range
    bisect_start("bsess", data_dir=plugin_data_dir, stream=io.StringIO())
    # Drive to convergence: every candidate is "bad" → hi narrows
    last = None
    for _ in range(5):
        last = bisect_mark("bsess", "bad", data_dir=plugin_data_dir, stream=io.StringIO())
        if last.get("converged"):
            break
    assert last and last.get("converged") is True
    # Finding recorded in metadata
    meta = json.loads((plugin_data_dir / "sessions" / "bsess" / "metadata.json").read_text())
    bisect_findings = [f for f in meta["findings"] if f["kind"] == "bisect_first_bad"]
    assert bisect_findings


def test_bisect_status_without_start(plugin_data_dir):
    _seed_bisect(plugin_data_dir)
    buf = io.StringIO()
    state = bisect_status("bsess", data_dir=plugin_data_dir, stream=buf)
    assert state is None
    assert "no bisect" in buf.getvalue()


def test_bisect_rejects_too_short_session(plugin_data_dir):
    append_event(_event(session_id="tiny"), data_dir=plugin_data_dir)
    with pytest.raises(BisectError):
        bisect_start("tiny", data_dir=plugin_data_dir, stream=io.StringIO())


# ---------- note ----------


def test_note_add_then_list(plugin_data_dir):
    _seed_basic(plugin_data_dir, sid="nsess")
    buf = io.StringIO()
    note_add("nsess", "the root cause is X", tag="root-cause", data_dir=plugin_data_dir, stream=buf)
    notes = note_list("nsess", data_dir=plugin_data_dir, stream=io.StringIO())
    assert len(notes) == 1
    assert notes[0]["body"] == "the root cause is X"
    assert notes[0]["tag"] == "root-cause"


def test_note_metadata_count_updated(plugin_data_dir):
    _seed_basic(plugin_data_dir, sid="nsess")
    note_add("nsess", "first", data_dir=plugin_data_dir, stream=io.StringIO())
    note_add("nsess", "second", data_dir=plugin_data_dir, stream=io.StringIO())
    meta = json.loads((plugin_data_dir / "sessions" / "nsess" / "metadata.json").read_text())
    assert meta["notes_count"] == 2


def test_note_custom_tag(plugin_data_dir):
    _seed_basic(plugin_data_dir, sid="nsess")
    note_add(
        "nsess",
        "x",
        tag="custom:investigation-2026-05-15",
        data_dir=plugin_data_dir,
        stream=io.StringIO(),
    )


def test_note_rejects_bare_unknown_tag(plugin_data_dir):
    _seed_basic(plugin_data_dir, sid="nsess")
    from query.note import NoteError

    with pytest.raises(NoteError):
        note_add("nsess", "x", tag="not-in-vocab", data_dir=plugin_data_dir, stream=io.StringIO())


def test_note_rm_removes(plugin_data_dir):
    _seed_basic(plugin_data_dir, sid="nsess")
    n = note_add("nsess", "x", data_dir=plugin_data_dir, stream=io.StringIO())
    ok = note_rm("nsess", n["id"], data_dir=plugin_data_dir, stream=io.StringIO())
    assert ok is True
    assert note_list("nsess", data_dir=plugin_data_dir, stream=io.StringIO()) == []


def test_note_filter_by_tag(plugin_data_dir):
    _seed_basic(plugin_data_dir, sid="nsess")
    note_add("nsess", "a", tag="root-cause", data_dir=plugin_data_dir, stream=io.StringIO())
    note_add("nsess", "b", tag="observation", data_dir=plugin_data_dir, stream=io.StringIO())
    filtered = note_list("nsess", tag="root-cause", data_dir=plugin_data_dir, stream=io.StringIO())
    assert len(filtered) == 1
    assert filtered[0]["body"] == "a"


# ---------- stats ----------


def test_stats_collects_tool_mix(plugin_data_dir):
    _seed_basic(plugin_data_dir, sid="ssess")
    append_event(
        _event(
            session_id="ssess",
            event_type="pre_tool",
            tool_name="Bash",
            command="ls",
            ts="2026-05-15T10:00:03.000+00:00",
        ),
        data_dir=plugin_data_dir,
    )
    buf = io.StringIO()
    result = stats("ssess", data_dir=plugin_data_dir, stream=buf)
    assert result["events_total"] >= 4
    assert result["tool_mix"].get("Bash") == 1


def test_stats_json_output(plugin_data_dir):
    _seed_basic(plugin_data_dir, sid="ssess")
    buf = io.StringIO()
    stats("ssess", fmt="json", data_dir=plugin_data_dir, stream=buf)
    parsed = json.loads(buf.getvalue())
    assert parsed["$schema"] == "aot/stats/v1"
    assert "anomaly_counters" in parsed
