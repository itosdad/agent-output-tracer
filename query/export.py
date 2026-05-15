"""`agent-output-tracer export-trace --session <id> [--output <path>]` —
DESIGN §7.4. Compose every forensic surface into a single markdown report.

Phase D-7 adds `export_safe_share(...)` — a sanitised counterpart that
strips PII / cwd / tool_response bodies via `core.sanitiser` so the
output is safe to paste into an incident report or external channel.
"""

from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path
from typing import IO

from core.sanitiser import render_safe_markdown, sanitise_session
from core.session_io import load_events, load_metadata
from query.causal_graph import causal_graph
from query.diff import diff
from query.mentioned_but_not_read import mentioned_but_not_read
from query.replay import replay


def export_trace(
    session_id: str,
    *,
    data_dir=None,
    output_path: Path | str | None = None,
    stream: IO[str] | None = None,
) -> dict:
    if stream is None:
        stream = sys.stdout

    metadata = load_metadata(session_id, data_dir=data_dir)

    parts: list[str] = []
    parts.append(f"# Forensic report: {session_id}\n")
    if metadata:
        parts.append(_metadata_block(metadata))

    timeline_buf = io.StringIO()
    replay(session_id, data_dir=data_dir, fmt="markdown", stream=timeline_buf)
    parts.append(_extract_timeline_section(timeline_buf.getvalue()))

    diff_buf = io.StringIO()
    diff(session_id, data_dir=data_dir, stream=diff_buf)
    parts.append("## User vs agent\n\n```text\n" + diff_buf.getvalue() + "```\n")

    mbnr_buf = io.StringIO()
    mentioned_but_not_read(session_id, data_dir=data_dir, stream=mbnr_buf)
    parts.append("## Hallucination candidates\n\n```text\n" + mbnr_buf.getvalue() + "```\n")

    cg_buf = io.StringIO()
    causal_graph(session_id, data_dir=data_dir, stream=cg_buf)
    parts.append("## Causal graph\n\n" + cg_buf.getvalue())

    report = "\n".join(parts)
    if output_path is not None:
        Path(output_path).write_text(report, encoding="utf-8")
    else:
        stream.write(report)

    return {
        "session_id": session_id,
        "sections": ["timeline", "diff", "mentioned", "causal"],
        "report": report,
    }


def _metadata_block(metadata) -> str:
    fields = (
        "ts_start",
        "ts_end",
        "engine",
        "cwd",
        "tool_calls_total",
        "user_prompts_count",
        "agent_responses_count",
        "unique_files_read",
        "total_bytes_read",
    )
    rows = []
    for f in fields:
        if metadata.get(f) is not None:
            rows.append(f"| {f} | {metadata[f]} |")
    if not rows:
        return ""
    return "## Session metadata\n\n| field | value |\n|---|---|\n" + "\n".join(rows) + "\n"


def _extract_timeline_section(replay_md: str) -> str:
    """Replace the `# Session ...` header from replay markdown with `## Timeline`."""
    lines = replay_md.splitlines()
    out_lines = ["## Timeline\n"]
    for line in lines:
        if line.startswith("# Session "):
            continue
        out_lines.append(line)
    return "\n".join(out_lines) + "\n"


# ----- Phase D-7: safe-share export -----


def export_safe_share(
    session_id: str,
    *,
    data_dir=None,
    fmt: str = "markdown",
    keep_excerpt: int = 0,
    output_path: Path | str | None = None,
    stream: IO[str] | None = None,
) -> dict:
    """Sanitise + emit a session in markdown / json / archive form.

    `fmt`:
      - `markdown` — human-readable, redacted timeline
      - `json` — `{metadata, events}` payload (also redacted)
      - `archive` — zip containing both, written to `output_path`

    `keep_excerpt`: how many leading characters of each tool_response
    to retain. 0 (default) strips them entirely.
    """
    if stream is None:
        stream = sys.stdout

    raw_events = load_events(session_id, data_dir=data_dir)
    raw_meta = load_metadata(session_id, data_dir=data_dir)
    events, meta = sanitise_session(raw_events, raw_meta, keep_excerpt=keep_excerpt)

    result: dict = {
        "$schema": "aot/export.safe-share/v1",
        "session_id_short": (raw_meta or {}).get("session_id", "")[:8],
        "events": len(events),
        "format": fmt,
    }

    if fmt == "archive":
        if not output_path:
            raise ValueError("--output is required for --format archive")
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("metadata.json", json.dumps(meta, ensure_ascii=False, indent=2))
            zf.writestr(
                "events.jsonl",
                "\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n",
            )
            zf.writestr("REPORT.md", render_safe_markdown(events, meta))
        result["archive_path"] = str(target)
        return result

    if fmt == "json":
        payload = {"metadata": meta, "events": events}
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    else:  # markdown
        text = render_safe_markdown(events, meta)

    if output_path is not None:
        Path(output_path).write_text(text, encoding="utf-8")
    else:
        stream.write(text)
    return result
