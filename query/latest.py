"""`agent-output-tracer latest` — print the most-recent session id."""

from __future__ import annotations

import sys
from typing import IO

from core.session_resolver import resolve_session_id


def latest_command(*, data_dir=None, stream: IO[str] | None = None) -> None:
    if stream is None:
        stream = sys.stdout
    sid = resolve_session_id("latest", data_dir=data_dir)
    stream.write(sid + "\n")
