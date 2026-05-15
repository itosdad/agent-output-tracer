"""Anomaly hint patterns for `replay --show-hints` (DESIGN §11 Phase B-8).

Each pattern is a small function over the session's events (+ optional
metadata / cross-session stats / config) that returns zero or more hint
dicts. Patterns are intentionally proxies — they surface plausibly
suspicious sequences for human review, not "rot detected" claims.

3.11+ allowed (only the query / analyzer surface, not the hook runtime).
"""

from __future__ import annotations

import os
from collections import Counter, defaultdict
from datetime import datetime
from statistics import quantiles
from typing import Any

# ---------- defaults ----------


DEFAULT_CONFIG: dict[str, Any] = {
    # (a) repeated file read
    "repeated_read_threshold": 3,
    # (b) routing config thrash
    "routing_paths": ["CLAUDE.md", "AGENTS.md", ".cursor/rules"],
    # (c) long-session outlier
    "long_session_percentile": 90,
    "long_session_min_samples": 5,
    # (d) config drift between wrapper and core
    "config_drift_window_seconds": 60,
    "wrapper_path_substrings": [],
    "core_path_substrings": [],
    # (e) namespace boundary bleed
    "boundary_prefixes": [],
    # (f) protected path Bash read
    "protected_path_substrings": [],
    "bash_read_commands": [
        "cat",
        "less",
        "more",
        "head",
        "tail",
        "bat",
        "view",
        "od",
        "xxd",
        "nl",
        "strings",
    ],
    # (g) same-domain skill parallel
    "skill_groups": [],
    "skill_group_window_seconds": 60,
}


# ---------- public API ----------


def detect_hints(events, *, metadata=None, all_sessions=None, config=None):
    """Run every anomaly-hint pattern over the session.

    Returns a list of hint dicts. Order matches the discovery order of
    each pattern; callers may sort by ts if they want chronology.
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    if not events:
        return []
    hints: list[dict] = []
    hints.extend(_pattern_repeated_read(events, cfg))
    hints.extend(_pattern_routing_config(events, cfg))
    hints.extend(_pattern_long_session(events, metadata, all_sessions, cfg))
    hints.extend(_pattern_config_drift(events, cfg))
    hints.extend(_pattern_namespace_bleed(events, cfg))
    hints.extend(_pattern_protected_bash_read(events, cfg))
    hints.extend(_pattern_skill_parallel(events, cfg))
    return hints


# ---------- (a) repeated read ----------


def _pattern_repeated_read(events, cfg):
    counts = Counter()
    first_seen = {}
    for ev in events:
        if ev.get("event_type") != "post_tool":
            continue
        if ev.get("tool_name") != "Read":
            continue
        for p in ev.get("paths") or []:
            counts[p] += 1
            first_seen.setdefault(p, ev.get("ts"))
    threshold = cfg["repeated_read_threshold"]
    out = []
    for path, n in counts.items():
        if n >= threshold:
            out.append(
                {
                    "pattern": "repeated_read",
                    "severity": "info",
                    "ts": first_seen.get(path),
                    "message": f"{path!r} read {n}× in this session (threshold {threshold}).",
                    "details": {"path": path, "count": n, "threshold": threshold},
                }
            )
    return out


# ---------- (b) routing config thrash ----------


def _pattern_routing_config(events, cfg):
    routing = [s.lower() for s in cfg["routing_paths"] if s]
    threshold = cfg["repeated_read_threshold"]
    counts = Counter()
    first_seen = {}
    for ev in events:
        if ev.get("event_type") != "post_tool":
            continue
        if ev.get("tool_name") != "Read":
            continue
        for p in ev.get("paths") or []:
            p_lower = p.lower()
            base = os.path.basename(p_lower)
            if any(r in p_lower or r == base for r in routing):
                counts[p] += 1
                first_seen.setdefault(p, ev.get("ts"))
    out = []
    for path, n in counts.items():
        if n >= threshold:
            out.append(
                {
                    "pattern": "routing_config_thrash",
                    "severity": "warn",
                    "ts": first_seen.get(path),
                    "message": f"Routing config {path!r} re-read {n}× — "
                    f"agent may be losing its bearings.",
                    "details": {"path": path, "count": n, "threshold": threshold},
                }
            )
    return out


# ---------- (c) long-session outlier ----------


def _pattern_long_session(events, metadata, all_sessions, cfg):
    if not metadata or not all_sessions:
        return []
    samples = [
        int(s.get("tool_calls_total") or 0)
        for s in all_sessions
        if s.get("tool_calls_total") is not None
    ]
    if len(samples) < cfg["long_session_min_samples"]:
        return []
    pct = cfg["long_session_percentile"]
    # `quantiles` with n=100 gives percentile cuts; pick the one matching `pct`.
    try:
        threshold = quantiles(samples, n=100)[pct - 1]
    except Exception:
        return []
    current = int(metadata.get("tool_calls_total") or 0)
    if current > threshold:
        return [
            {
                "pattern": "long_session_outlier",
                "severity": "warn",
                "ts": metadata.get("ts_start"),
                "message": f"Session tool calls {current} exceed {pct}th "
                f"percentile {threshold:.0f} of recent sessions.",
                "details": {
                    "value": current,
                    "percentile": pct,
                    "threshold": threshold,
                    "samples": len(samples),
                },
            }
        ]
    return []


# ---------- (d) config drift wrapper ↔ core ----------


def _pattern_config_drift(events, cfg):
    wrappers = cfg["wrapper_path_substrings"]
    cores = cfg["core_path_substrings"]
    if not wrappers or not cores:
        return []
    window = float(cfg["config_drift_window_seconds"])

    def kind_of(path):
        if any(w in path for w in wrappers):
            return "wrapper"
        if any(c in path for c in cores):
            return "core"
        return None

    reads = []
    for ev in events:
        if ev.get("event_type") != "post_tool":
            continue
        if ev.get("tool_name") != "Read":
            continue
        for p in ev.get("paths") or []:
            k = kind_of(p)
            if k:
                reads.append((ev.get("ts"), k, p))

    out = []
    for i in range(1, len(reads)):
        ts_a, kind_a, path_a = reads[i - 1]
        ts_b, kind_b, path_b = reads[i]
        if kind_a == kind_b:
            continue
        if _delta_seconds(ts_a, ts_b) <= window:
            out.append(
                {
                    "pattern": "config_drift",
                    "severity": "warn",
                    "ts": ts_b,
                    "message": f"{kind_a} → {kind_b} read within "
                    f"{cfg['config_drift_window_seconds']}s: "
                    f"{path_a} → {path_b}.",
                    "details": {
                        "wrapper_path": path_a if kind_a == "wrapper" else path_b,
                        "core_path": path_b if kind_b == "core" else path_a,
                        "delta_seconds": _delta_seconds(ts_a, ts_b),
                    },
                }
            )
    return out


# ---------- (e) namespace boundary bleed ----------


def _pattern_namespace_bleed(events, cfg):
    prefixes = cfg["boundary_prefixes"]
    if not prefixes:
        return []
    seen = defaultdict(list)  # prefix -> sample paths
    for ev in events:
        if ev.get("event_type") not in ("pre_tool", "post_tool"):
            continue
        for p in ev.get("paths") or []:
            for pref in prefixes:
                if p.startswith(pref):
                    seen[pref].append(p)
                    break
    if len(seen) >= 2:
        return [
            {
                "pattern": "namespace_bleed",
                "severity": "warn",
                "ts": None,
                "message": f"Reads cross {len(seen)} configured namespaces: "
                + ", ".join(sorted(seen)),
                "details": dict(seen),
            }
        ]
    return []


# ---------- (f) protected path Bash read ----------


def _pattern_protected_bash_read(events, cfg):
    protected = cfg["protected_path_substrings"]
    if not protected:
        return []
    readlike = set(cfg["bash_read_commands"])
    out = []
    for ev in events:
        if ev.get("event_type") != "pre_tool":
            continue
        if ev.get("tool_name") != "Bash":
            continue
        cmd = ev.get("command") or (ev.get("tool_input") or {}).get("command") or ""
        if not cmd:
            continue
        tokens = cmd.split()
        if not tokens:
            continue
        first = os.path.basename(tokens[0])
        if first not in readlike:
            continue
        if any(p in cmd for p in protected):
            out.append(
                {
                    "pattern": "protected_bash_read",
                    "severity": "warn",
                    "ts": ev.get("ts"),
                    "message": f"Bash {first} touched a protected path: {cmd!r}.",
                    "details": {"command": cmd},
                }
            )
    return out


# ---------- (g) same-domain skill parallel ----------


def _pattern_skill_parallel(events, cfg):
    groups = [set(g) for g in cfg["skill_groups"] if g]
    if not groups:
        return []
    window = float(cfg["skill_group_window_seconds"])
    invocations = []  # (ts, subagent_type)
    for ev in events:
        if ev.get("event_type") != "pre_tool":
            continue
        if ev.get("tool_name") != "Task":
            continue
        sub = (ev.get("tool_input") or {}).get("subagent_type")
        if sub:
            invocations.append((ev.get("ts"), sub))

    out = []
    flagged_pairs = set()
    for i in range(len(invocations)):
        ts_i, sub_i = invocations[i]
        for j in range(i + 1, len(invocations)):
            ts_j, sub_j = invocations[j]
            if _delta_seconds(ts_i, ts_j) > window:
                break
            for g in groups:
                if sub_i in g and sub_j in g and sub_i != sub_j:
                    pair = tuple(sorted((sub_i, sub_j)))
                    if pair in flagged_pairs:
                        continue
                    flagged_pairs.add(pair)
                    out.append(
                        {
                            "pattern": "skill_group_parallel",
                            "severity": "warn",
                            "ts": ts_j,
                            "message": f"Same-group skills invoked in close succession: "
                            f"{sub_i} → {sub_j}.",
                            "details": {
                                "skills": list(pair),
                                "delta_seconds": _delta_seconds(ts_i, ts_j),
                            },
                        }
                    )
    return out


# ---------- helpers ----------


def _delta_seconds(ts_a, ts_b):
    if not (isinstance(ts_a, str) and isinstance(ts_b, str)):
        return float("inf")
    try:
        a = datetime.fromisoformat(ts_a)
        b = datetime.fromisoformat(ts_b)
    except ValueError:
        return float("inf")
    return abs((b - a).total_seconds())
