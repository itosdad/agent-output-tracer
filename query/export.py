"""`agent-output-tracer export-trace --session <id> [--output <path>]` —
DESIGN §7.4. Compose every forensic surface into a single markdown report.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import IO

from core.session_io import load_metadata
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
