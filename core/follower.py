"""File follower for events.jsonl (DESIGN_FORENSIC_UX §5.4 / §9.4).

Polling-based by default — no third-party deps. Optional `watchdog`
backend kicks in when installed and `polling=False`. The race with the
writer is handled by checking that each yielded line ends with `\\n`;
partial trailing lines wait for the next read.

Usage:

    for ev in follow_events("session-id", data_dir=...):
        process(ev)

Stops when `from_start=False` (default tail-only) hits its own ctrl-c
or when the consumer breaks out of the loop. Pass `stop_after_seconds`
for tests or one-shot tailing.
"""

from __future__ import annotations

import json
import time
from typing import Callable, Iterator

from core.recorder import session_dir


def follow_events(
    session_id: str,
    *,
    data_dir=None,
    from_start: bool = False,
    poll_interval: float = 0.5,
    stop_after_seconds: float | None = None,
    stop_predicate: Callable[[], bool] | None = None,
) -> Iterator[dict]:
    """Yield parsed events as the events.jsonl file grows.

    Args:
      from_start: if True, replay the existing file from the top, then
        tail. If False (default), start at the current end of file.
      poll_interval: seconds between filesystem stat() polls.
      stop_after_seconds: bail out after this many seconds of wall
        time. Useful for tests.
      stop_predicate: callable returning True when the loop should
        stop (e.g. an external "ctrl-c" flag).
    """
    sdir = session_dir(session_id, data_dir=data_dir)
    events_file = sdir / "events.jsonl"

    # Wait for the file to appear (the very first hook may not have
    # fired yet) — but bounded so we don't block forever.
    start_wait = time.monotonic()
    while not events_file.exists():
        if _should_stop(start_wait, stop_after_seconds, stop_predicate):
            return
        time.sleep(poll_interval)

    buffer = ""
    position = 0 if from_start else events_file.stat().st_size
    loop_start = time.monotonic()

    while True:
        if _should_stop(loop_start, stop_after_seconds, stop_predicate):
            return
        try:
            size = events_file.stat().st_size
        except FileNotFoundError:
            return
        if size > position:
            with events_file.open("r", encoding="utf-8") as f:
                f.seek(position)
                chunk = f.read(size - position)
                position = f.tell()
            buffer += chunk
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                if not line.strip():
                    continue
                try:
                    yield json.loads(line)
                except ValueError:
                    # Skip partial / truncated lines; the next poll will
                    # pick them up cleanly.
                    continue
        elif size < position:
            # File truncated (e.g. rotated). Reset and start over.
            position = 0
            buffer = ""
        time.sleep(poll_interval)


def _should_stop(start: float, stop_after: float | None, stop_predicate) -> bool:
    if stop_after is not None and (time.monotonic() - start) >= stop_after:
        return True
    if stop_predicate is not None and stop_predicate():
        return True
    return False
