"""`aot find VOCAB --session SPEC` — DESIGN_FORENSIC_UX §7.4.

Anomaly vocabulary detector. Each vocab term is a precise definition
that returns matching events. Unlike `replay --show-hints` (inline
heuristic display), `find` is query-shaped: pipe it, filter on it,
write CI assertions against it.

Vocab (default thresholds, configurable via `--threshold`):

  unmentioned-reads   Path was Read but no prior user_prompt mentioned it
                      (full path or basename) and no Glob/Grep result
                      introduced it.
  repeated-reads N    Same path read >= N times (N=3).
  glob-burst K        K consecutive Reads whose path came from a prior
                      Glob's response (K=2).
  routing-thrash M    Routing config (CLAUDE.md / AGENTS.md / .cursor/rules)
                      read >= M times (M=2).
  large-read N        Single Read whose result_bytes >= N*1024 (N=50 KB).
  hallucinations      agent_response events flagged by `trace` as
                      hallucination_candidate, executed batch-wise via
                      the session's `mentioned_but_not_read` candidates.
  empty-glob          Glob / Grep returned 0 paths AND a subsequent
                      agent_response uses language implying it found
                      something (heuristic: "found", "located", "matched").
  stale-cache         Same path Read >=2 times with the same SHA256
                      (or same byte size when SHA absent).
  silent-failure      post_tool that has tool_response "" or contains
                      "error:" but the next agent_response doesn't
                      mention that path or the word "error".
  abandoned-write     Write/Edit of a path followed by another Write/Edit
                      of the same path with no intervening Read.

`denied-permission` (engine-log overlay) is deferred to D-6.
"""

from __future__ import annotations

import os
import re
import sys
from collections import Counter
from typing import IO

from core.references import extract_path_tokens, is_grounded, strip_tracer_output
from core.session_io import load_events
from core.time_utils import short_time

ROUTING_DEFAULT = ("CLAUDE.md", "AGENTS.md", ".cursor/rules")
FOUND_RE = re.compile(r"\b(found|located|matched|discovered)\b", re.I)


VOCAB = (
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
)


def find(
    session_id: str,
    vocab: str,
    *,
    threshold: int | None = None,
    data_dir=None,
    stream: IO[str] | None = None,
) -> dict:
    if vocab not in VOCAB:
        raise ValueError(f"unknown vocab {vocab!r}. Valid: {', '.join(VOCAB)}")

    if stream is None:
        stream = sys.stdout
    events = load_events(session_id, data_dir=data_dir)

    dispatch = {
        "unmentioned-reads": lambda: _unmentioned_reads(events),
        "repeated-reads": lambda: _repeated_reads(events, threshold or 3),
        "glob-burst": lambda: _glob_burst(events, threshold or 2),
        "routing-thrash": lambda: _routing_thrash(events, threshold or 2),
        "large-read": lambda: _large_read(events, threshold or 50),
        "hallucinations": lambda: _hallucinations(events),
        "empty-glob": lambda: _empty_glob(events),
        "stale-cache": lambda: _stale_cache(events),
        "silent-failure": lambda: _silent_failure(events),
        "abandoned-write": lambda: _abandoned_write(events),
    }
    matches = dispatch[vocab]()
    result = {
        "session_id": session_id,
        "vocab": vocab,
        "threshold": threshold,
        "matches": matches,
    }
    _render(result, stream)
    return result


# ----- patterns -----


def _unmentioned_reads(events):
    """Path was Read but no prior user_prompt named it and no prior
    Glob/Grep surfaced it.

    Time-causality matters here: a user prompt that comes AFTER the
    Read cannot retroactively "ground" the Read, so we walk the events
    chronologically and only consult the corpus that existed at the
    moment the Read fired.
    """
    out = []
    user_parts: list[str] = []
    glob_parts: list[str] = []
    for i, ev in enumerate(events):
        et = ev.get("event_type")
        if et == "user_prompt":
            user_parts.append(strip_tracer_output(ev.get("user_prompt_text") or ""))
            continue
        if et != "post_tool":
            continue
        tool = ev.get("tool_name")
        if tool in ("Glob", "Grep"):
            resp = ev.get("tool_response")
            if isinstance(resp, str):
                glob_parts.append(resp)
            continue
        if tool != "Read":
            continue
        user_text = " ".join(user_parts)
        glob_text = " ".join(glob_parts)
        for p in ev.get("paths") or []:
            if not isinstance(p, str):
                continue
            if is_grounded(p, user_text, glob_text):
                continue
            out.append({"event_idx": i, "ts": ev.get("ts"), "path": p, "kind": "unmentioned-reads"})
    return out


def _repeated_reads(events, n: int):
    counts = Counter()
    first_idx = {}
    for i, ev in enumerate(events):
        if ev.get("event_type") != "post_tool" or ev.get("tool_name") != "Read":
            continue
        for p in ev.get("paths") or []:
            if isinstance(p, str):
                counts[p] += 1
                first_idx.setdefault(p, i)
    return [
        {
            "event_idx": first_idx[p],
            "ts": events[first_idx[p]].get("ts"),
            "path": p,
            "count": c,
            "kind": "repeated-reads",
        }
        for p, c in counts.items()
        if c >= n
    ]


def _glob_burst(events, k: int):
    """K consecutive Reads whose paths came from a prior Glob's response."""
    glob_paths: set[str] = set()
    out = []
    streak: list[dict] = []
    for i, ev in enumerate(events):
        et = ev.get("event_type")
        if et == "post_tool" and ev.get("tool_name") == "Glob":
            for p in re.split(r"\s+", ev.get("tool_response") or ""):
                if p:
                    glob_paths.add(p)
            streak = []
        elif et == "pre_tool" and ev.get("tool_name") == "Read":
            target = (ev.get("paths") or [None])[0]
            if target and target in glob_paths:
                streak.append(
                    {"event_idx": i, "ts": ev.get("ts"), "path": target, "kind": "glob-burst"}
                )
                if len(streak) >= k:
                    out.extend(streak)
                    streak = []
            else:
                streak = []
        elif et in ("agent_response", "user_prompt"):
            streak = []
    return out


def _routing_thrash(events, m: int):
    counts = Counter()
    first_idx = {}
    for i, ev in enumerate(events):
        if ev.get("event_type") != "post_tool" or ev.get("tool_name") != "Read":
            continue
        for p in ev.get("paths") or []:
            if any(p.endswith(r) or r in p for r in ROUTING_DEFAULT):
                counts[p] += 1
                first_idx.setdefault(p, i)
    return [
        {
            "event_idx": first_idx[p],
            "ts": events[first_idx[p]].get("ts"),
            "path": p,
            "count": c,
            "kind": "routing-thrash",
        }
        for p, c in counts.items()
        if c >= m
    ]


def _large_read(events, kb: int):
    threshold = kb * 1024
    out = []
    for i, ev in enumerate(events):
        if ev.get("event_type") != "post_tool" or ev.get("tool_name") != "Read":
            continue
        size = int(ev.get("response_size_bytes") or ev.get("result_bytes") or 0)
        if size >= threshold:
            out.append(
                {
                    "event_idx": i,
                    "ts": ev.get("ts"),
                    "path": (ev.get("paths") or [None])[0],
                    "size_bytes": size,
                    "kind": "large-read",
                }
            )
    return out


def _hallucinations(events):
    """Agent_response events where the path tokens it mentions aren't
    grounded in any **prior** user_prompt or tool_response.

    Two correctness rules the older bag-of-events version got wrong:

    1. **Time-causality.** A user prompt or tool response that appears
       AFTER the agent_response cannot retroactively ground a claim
       the agent already made. We accumulate the corpus chronologically
       and freeze it at each agent_response event.

    2. **Self-paste resilience.** When the operator pastes a prior
       `aot find` output into the next user prompt, every flagged token
       would otherwise appear in user_text and silently disqualify
       itself. `strip_tracer_output` excises those pasted blocks before
       the corpus is consulted, so the detector stays consistent across
       repeated runs.
    """
    out = []
    user_parts: list[str] = []
    tool_parts: list[str] = []
    for i, ev in enumerate(events):
        et = ev.get("event_type")
        if et == "user_prompt":
            user_parts.append(strip_tracer_output(ev.get("user_prompt_text") or ""))
            continue
        if et == "post_tool":
            resp = ev.get("tool_response")
            if isinstance(resp, str):
                tool_parts.append(resp)
            continue
        if et != "agent_response":
            continue
        user_text = " ".join(user_parts)
        tool_text = " ".join(tool_parts)
        text = ev.get("agent_response_text") or ""
        for tok in extract_path_tokens(text):
            if is_grounded(tok, user_text, tool_text):
                continue
            out.append(
                {
                    "event_idx": i,
                    "ts": ev.get("ts"),
                    "token": tok,
                    "kind": "hallucinations",
                }
            )
    return out


def _empty_glob(events):
    out = []
    for i, ev in enumerate(events):
        et = ev.get("event_type")
        if et != "post_tool":
            continue
        if ev.get("tool_name") not in ("Glob", "Grep"):
            continue
        resp = (ev.get("tool_response") or "").strip()
        # "empty" means no path-shaped lines
        if resp and any(line.strip().startswith("/") for line in resp.splitlines()):
            continue
        # Find next agent_response
        for j in range(i + 1, len(events)):
            if events[j].get("event_type") != "agent_response":
                continue
            text = events[j].get("agent_response_text") or ""
            if FOUND_RE.search(text):
                out.append(
                    {
                        "event_idx": i,
                        "ts": ev.get("ts"),
                        "agent_event_idx": j,
                        "pattern": (ev.get("tool_input") or {}).get("pattern"),
                        "kind": "empty-glob",
                    }
                )
            break
    return out


def _stale_cache(events):
    """Same path read >=2 times with the same SHA256 (or same size when
    SHA absent)."""
    by_path: dict[str, list[tuple[int, str, int]]] = {}
    for i, ev in enumerate(events):
        if ev.get("event_type") != "post_tool" or ev.get("tool_name") != "Read":
            continue
        sha = (
            ev.get("response_sha256")
            or f"size:{ev.get('response_size_bytes') or ev.get('result_bytes') or 0}"
        )
        for p in ev.get("paths") or []:
            if isinstance(p, str):
                by_path.setdefault(p, []).append((i, sha, int(ev.get("ts") and 1 or 0)))
    out = []
    for path, hits in by_path.items():
        if len(hits) < 2:
            continue
        seen_shas: dict[str, list[int]] = {}
        for idx, sha, _ in hits:
            seen_shas.setdefault(sha, []).append(idx)
        for sha, idxs in seen_shas.items():
            if len(idxs) >= 2:
                for idx in idxs:
                    out.append(
                        {
                            "event_idx": idx,
                            "ts": events[idx].get("ts"),
                            "path": path,
                            "sha": sha,
                            "kind": "stale-cache",
                        }
                    )
    return out


def _silent_failure(events):
    out = []
    for i, ev in enumerate(events):
        if ev.get("event_type") != "post_tool":
            continue
        resp = (ev.get("tool_response") or "").strip()
        is_failure = not resp or "error" in resp.lower()[:200]
        if not is_failure:
            continue
        # Next agent_response — does it mention this path or the word "error"?
        target_paths = [p for p in ev.get("paths") or [] if isinstance(p, str)]
        for j in range(i + 1, len(events)):
            if events[j].get("event_type") != "agent_response":
                continue
            text = (events[j].get("agent_response_text") or "").lower()
            mentioned = any(
                (p.lower() in text) or (os.path.basename(p).lower() in text) for p in target_paths
            )
            if not mentioned and "error" not in text and "fail" not in text:
                out.append(
                    {
                        "event_idx": i,
                        "ts": ev.get("ts"),
                        "tool": ev.get("tool_name"),
                        "kind": "silent-failure",
                    }
                )
            break
    return out


def _abandoned_write(events):
    """Write/Edit then re-Write/Edit same path with no intervening Read."""
    last_write_idx: dict[str, int] = {}
    intervening_read: dict[str, bool] = {}
    out = []
    for i, ev in enumerate(events):
        if ev.get("event_type") != "pre_tool":
            continue
        tool = ev.get("tool_name")
        for p in ev.get("paths") or []:
            if not isinstance(p, str):
                continue
            if tool in ("Write", "Edit", "MultiEdit"):
                if p in last_write_idx and not intervening_read.get(p, False):
                    out.append(
                        {
                            "event_idx": i,
                            "ts": ev.get("ts"),
                            "path": p,
                            "first_write_idx": last_write_idx[p],
                            "kind": "abandoned-write",
                        }
                    )
                last_write_idx[p] = i
                intervening_read[p] = False
            elif tool == "Read":
                if p in last_write_idx:
                    intervening_read[p] = True
    return out


# ----- rendering -----


def _render(result, stream):
    matches = result["matches"]
    vocab = result["vocab"]
    if not matches:
        stream.write(f"No matches for find vocab {vocab!r}.\n")
        return
    stream.write(f"find {vocab!r}: {len(matches)} match(es)\n")
    for m in matches:
        ts = short_time(m.get("ts"))
        extra = []
        for k in ("path", "token", "count", "size_bytes", "tool", "pattern"):
            if k in m and m[k] is not None:
                extra.append(f"{k}={m[k]}")
        stream.write(f"  [{ts}] event {m.get('event_idx', '?')} " + " ".join(extra) + "\n")
