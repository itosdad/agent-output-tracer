"""`agent-output-tracer list` — show recent sessions."""

from __future__ import annotations

import json
import sys
from typing import IO

from core.session_io import list_sessions
from core.time_utils import human_bytes, long_time


def list_command(
    *,
    data_dir=None,
    last: int | None = None,
    fmt: str = "text",
    stream: IO[str] | None = None,
) -> None:
    if stream is None:
        stream = sys.stdout

    sessions = list_sessions(data_dir=data_dir)
    if last is not None and last >= 0:
        sessions = sessions[:last]

    if fmt == "json":
        json.dump({"sessions": sessions}, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        return

    if not sessions:
        stream.write("(no sessions captured yet)\n")
        return

    # text table
    stream.write(f"{'session_id':<32}  {'started':<19}  {'events':>6}  {'reads':>5}  bytes\n")
    stream.write("-" * 76 + "\n")
    for s in sessions:
        sid = s.get("session_id", "?")
        ts = long_time(s.get("ts_start") or s.get("ts_end") or "")
        n_events = sum(
            int(s.get(k, 0))
            for k in (
                "tool_calls_total",
                "user_prompts_count",
                "agent_responses_count",
            )
        )
        n_reads = int(s.get("unique_files_read", 0))
        nbytes = human_bytes(s.get("total_bytes_read", 0))
        stream.write(f"{sid[:32]:<32}  {ts[:19]:<19}  {n_events:>6}  {n_reads:>5}  {nbytes}\n")
