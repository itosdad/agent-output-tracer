"""Safe-share sanitiser (DESIGN_FORENSIC_UX §7.9).

Transforms an in-memory session (events + metadata) so it can be
pasted into an incident report, Slack thread, or bug ticket without
leaking PII / cwd / large tool_response payloads.

Transforms (default `--safe-share` profile):
  - Paths replaced: `$HOME/...` → `<HOME>/...`,
    `<cwd>/foo/bar` → `<repo>/foo/bar`
  - `cwd` removed; only `cwd_hash` survives
  - tool_response replaced with `{sha, size, excerpt[:N]}`
  - user_prompt text masked with the EXPORT-only secret pattern set
    (email / phone / generic hex tokens 32+ chars)
  - session_id shortened to its first 8 chars
"""

from __future__ import annotations

import copy
import os
import re
from typing import Iterable

from core.redactor import redact_event

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"\+?\d[\d\s().-]{8,}\d")
_LONG_HEX_RE = re.compile(r"\b[0-9a-fA-F]{32,}\b")


def sanitise_session(
    events: Iterable[dict],
    metadata: dict | None,
    *,
    keep_excerpt: int = 0,
) -> tuple[list[dict], dict]:
    """Return `(sanitised_events, sanitised_metadata)`.

    Does not mutate the inputs.
    """
    meta = dict(metadata or {})
    cwd = meta.get("cwd") or ""
    home = os.path.expanduser("~")

    def _scrub_path(s: str) -> str:
        if not isinstance(s, str):
            return s
        out = s
        if cwd and cwd in out:
            out = out.replace(cwd, "<repo>")
        if home and home in out:
            out = out.replace(home, "<HOME>")
        return out

    def _scrub_text(s: str) -> str:
        if not isinstance(s, str):
            return s
        s = _scrub_path(s)
        s = _EMAIL_RE.sub("<EMAIL>", s)
        # Hex first: long hex strings can look like a digit run and
        # collide with the phone regex.
        s = _LONG_HEX_RE.sub("<HEX>", s)
        s = _PHONE_RE.sub("<PHONE>", s)
        return s

    out_events: list[dict] = []
    for ev in events:
        clean = copy.deepcopy(ev)
        clean = redact_event(clean)  # also apply default secret patterns
        if isinstance(clean.get("session_id"), str):
            clean["session_id"] = clean["session_id"][:8]
        # paths abstraction
        clean["paths"] = [_scrub_path(p) for p in clean.get("paths") or []]
        for k in ("user_prompt_text", "agent_response_text", "command", "cwd"):
            if isinstance(clean.get(k), str):
                clean[k] = _scrub_text(clean[k])
        # tool_response → {sha, size, excerpt[:N]}
        if clean.get("event_type") == "post_tool":
            resp = clean.get("tool_response")
            if isinstance(resp, str):
                excerpt = _scrub_text(resp[:keep_excerpt]) if keep_excerpt > 0 else ""
                clean["tool_response"] = excerpt
                # response_sha256 / response_size_bytes already set in v2
        clean.pop("raw_event", None)
        out_events.append(clean)

    if "cwd" in meta:
        meta.pop("cwd")
    if isinstance(meta.get("session_id"), str):
        meta["session_id"] = meta["session_id"][:8]

    return out_events, meta


def render_safe_markdown(events: list[dict], metadata: dict) -> str:
    """Render a sanitised session as a human-readable markdown report.

    The bulky `tool_response` bodies have already been stripped; what
    remains is timeline + counters.
    """
    lines = [f"# Session report ({metadata.get('session_id', '?')[:8]})\n"]
    if metadata:
        lines.append("## Metadata\n")
        lines.append("| field | value |")
        lines.append("|---|---|")
        for k in (
            "engine",
            "engine_version",
            "ts_start",
            "ts_end",
            "tool_calls_total",
            "user_prompts_count",
            "agent_responses_count",
            "unique_files_read",
            "total_bytes_read",
            "cwd_hash",
        ):
            if metadata.get(k) is not None:
                lines.append(f"| {k} | {metadata[k]} |")
        lines.append("")
    lines.append("## Timeline\n")
    for ev in events:
        et = ev.get("event_type")
        ts = ev.get("ts")
        if et == "user_prompt":
            lines.append(f"- [{ts}] **user**: {ev.get('user_prompt_text', '')}")
        elif et == "pre_tool":
            paths = ", ".join(ev.get("paths") or [])
            lines.append(f"- [{ts}] **→ {ev.get('tool_name')}** {paths}")
        elif et == "post_tool":
            sha = ev.get("response_sha256") or "-"
            size = ev.get("response_size_bytes") or ev.get("result_bytes") or 0
            lines.append(
                f"- [{ts}] **↳ {ev.get('tool_name')}** sha={sha[:12]} size={size}B"
            )
        elif et == "agent_response":
            lines.append(f"- [{ts}] **agent**: {ev.get('agent_response_text', '')}")
        elif et == "session_end":
            lines.append(f"- [{ts}] _session_end_")
    return "\n".join(lines) + "\n"
