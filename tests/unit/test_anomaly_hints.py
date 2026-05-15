"""Unit tests for analyzer.anomaly_hints — DESIGN §11 Phase B-8 (7 patterns)."""

from __future__ import annotations

from analyzer.anomaly_hints import DEFAULT_CONFIG, detect_hints


def _ev(
    et="post_tool",
    tool_name="Read",
    paths=(),
    ts="2026-01-01T00:00:00.000+00:00",
    tool_input=None,
    command=None,
    result_bytes=0,
    user_prompt_text=None,
):
    return {
        "v": 1,
        "engine": "claude-code",
        "event_type": et,
        "session_id": "S",
        "ts": ts,
        "cwd": "/p",
        "user_prompt_text": user_prompt_text,
        "tool_name": tool_name,
        "tool_input": tool_input or {},
        "tool_response": None,
        "agent_response_text": None,
        "stop_reason": None,
        "paths": list(paths),
        "command": command,
        "result_bytes": result_bytes,
        "raw_event": {},
    }


# (a) Repeated file read
def test_repeated_read_flagged():
    events = [_ev(paths=["/p/foo.md"], ts=f"2026-01-01T00:00:0{i}.000+00:00") for i in range(3)]
    hints = detect_hints(events)
    repeats = [h for h in hints if h["pattern"] == "repeated_read"]
    assert len(repeats) >= 1
    assert "/p/foo.md" in repeats[0]["message"]


def test_repeated_read_below_threshold_not_flagged():
    events = [_ev(paths=["/p/foo.md"]), _ev(paths=["/p/foo.md"])]  # 2 < 3
    hints = detect_hints(events)
    assert not any(h["pattern"] == "repeated_read" for h in hints)


# (b) Routing config read
def test_routing_config_read_flagged():
    events = [_ev(paths=["/p/CLAUDE.md"], ts=f"2026-01-01T00:00:0{i}.000+00:00") for i in range(3)]
    hints = detect_hints(events)
    assert any(h["pattern"] == "routing_config_thrash" for h in hints)


# (c) Long-session outlier
def test_long_session_outlier_flagged():
    events = [_ev(et="pre_tool", paths=["/p/x"]) for _ in range(50)]
    metadata = {"tool_calls_total": 50}
    other_sessions = [{"tool_calls_total": n} for n in range(10, 30)]
    hints = detect_hints(events, metadata=metadata, all_sessions=other_sessions)
    assert any(h["pattern"] == "long_session_outlier" for h in hints)


def test_long_session_inlier_not_flagged():
    events = [_ev(et="pre_tool", paths=["/p/x"]) for _ in range(5)]
    metadata = {"tool_calls_total": 5}
    other_sessions = [{"tool_calls_total": n} for n in (50, 60, 70, 80, 90)]
    hints = detect_hints(events, metadata=metadata, all_sessions=other_sessions)
    assert not any(h["pattern"] == "long_session_outlier" for h in hints)


# (d) Wrapper / core drift sequence
def test_wrapper_core_drift_flagged():
    config = dict(DEFAULT_CONFIG)
    config["wrapper_path_substrings"] = [".claude/rules/"]
    config["core_path_substrings"] = ["knowledge/reusable-playbooks/"]
    events = [
        _ev(paths=["/p/.claude/rules/foo.md"], ts="2026-01-01T00:00:00.000+00:00"),
        _ev(
            paths=["/p/knowledge/reusable-playbooks/bar.md"], ts="2026-01-01T00:00:30.000+00:00"
        ),  # within 60s window
    ]
    hints = detect_hints(events, config=config)
    assert any(h["pattern"] == "config_drift" for h in hints)


def test_wrapper_core_drift_outside_window_not_flagged():
    config = dict(DEFAULT_CONFIG)
    config["wrapper_path_substrings"] = [".claude/rules/"]
    config["core_path_substrings"] = ["knowledge/reusable-playbooks/"]
    events = [
        _ev(paths=["/p/.claude/rules/foo.md"], ts="2026-01-01T00:00:00.000+00:00"),
        _ev(
            paths=["/p/knowledge/reusable-playbooks/bar.md"], ts="2026-01-01T00:05:00.000+00:00"
        ),  # 5 min > 60s
    ]
    hints = detect_hints(events, config=config)
    assert not any(h["pattern"] == "config_drift" for h in hints)


# (e) Namespace boundary bleed
def test_namespace_bleed_flagged():
    config = dict(DEFAULT_CONFIG)
    config["boundary_prefixes"] = ["/p/clients/alpha/", "/p/clients/beta/"]
    events = [
        _ev(paths=["/p/clients/alpha/a.md"]),
        _ev(paths=["/p/clients/beta/b.md"]),
    ]
    hints = detect_hints(events, config=config)
    assert any(h["pattern"] == "namespace_bleed" for h in hints)


def test_namespace_no_bleed_when_single_namespace():
    config = dict(DEFAULT_CONFIG)
    config["boundary_prefixes"] = ["/p/clients/alpha/", "/p/clients/beta/"]
    events = [
        _ev(paths=["/p/clients/alpha/a.md"]),
        _ev(paths=["/p/clients/alpha/b.md"]),
    ]
    hints = detect_hints(events, config=config)
    assert not any(h["pattern"] == "namespace_bleed" for h in hints)


# (f) Protected path Bash read
def test_protected_bash_read_flagged():
    config = dict(DEFAULT_CONFIG)
    config["protected_path_substrings"] = [".env", "secrets/"]
    events = [
        _ev(
            et="pre_tool",
            tool_name="Bash",
            tool_input={"command": "cat /p/secrets/key"},
            command="cat /p/secrets/key",
        ),
    ]
    hints = detect_hints(events, config=config)
    assert any(h["pattern"] == "protected_bash_read" for h in hints)


def test_unprotected_bash_read_not_flagged():
    config = dict(DEFAULT_CONFIG)
    config["protected_path_substrings"] = [".env", "secrets/"]
    events = [
        _ev(
            et="pre_tool",
            tool_name="Bash",
            tool_input={"command": "cat /p/README.md"},
            command="cat /p/README.md",
        ),
    ]
    hints = detect_hints(events, config=config)
    assert not any(h["pattern"] == "protected_bash_read" for h in hints)


# (g) Same-domain skill parallel
def test_same_domain_skill_parallel_flagged():
    config = dict(DEFAULT_CONFIG)
    config["skill_groups"] = [["serp-reverse-engineer", "search-console-interpreter"]]
    events = [
        _ev(
            et="pre_tool",
            tool_name="Task",
            tool_input={"subagent_type": "serp-reverse-engineer"},
            ts="2026-01-01T00:00:00.000+00:00",
        ),
        _ev(
            et="pre_tool",
            tool_name="Task",
            tool_input={"subagent_type": "search-console-interpreter"},
            ts="2026-01-01T00:00:30.000+00:00",
        ),
    ]
    hints = detect_hints(events, config=config)
    assert any(h["pattern"] == "skill_group_parallel" for h in hints)


def test_unrelated_skills_not_flagged():
    config = dict(DEFAULT_CONFIG)
    config["skill_groups"] = [["a", "b"]]
    events = [
        _ev(et="pre_tool", tool_name="Task", tool_input={"subagent_type": "a"}),
        _ev(et="pre_tool", tool_name="Task", tool_input={"subagent_type": "c"}),
    ]
    hints = detect_hints(events, config=config)
    assert not any(h["pattern"] == "skill_group_parallel" for h in hints)


# Smoke
def test_empty_session_no_hints():
    assert detect_hints([]) == []


def test_hint_has_required_fields():
    events = [_ev(paths=["/p/foo.md"]) for _ in range(3)]
    hints = detect_hints(events)
    h = hints[0]
    assert "pattern" in h and "message" in h
    assert "severity" in h
