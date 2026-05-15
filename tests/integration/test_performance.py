"""Performance budget for the recorder write path.

Per DESIGN §9.5 the budgets are per-hook *in-process* costs (the cost
that happens after the Python interpreter has already started). Cold
subprocess startup is a separate, non-budgeted cost dominated by Python
itself.

We measure the steady-state cost of `append_event` (normalize → redact →
JSONL append → metadata update) over many iterations and assert a
generous-but-meaningful average.
"""

from __future__ import annotations

import time

from adapters.claude_code import normalize_event
from core.recorder import append_event


def _events_for_benchmark(n):
    out = []
    for i in range(n):
        out.append(
            normalize_event(
                {
                    "session_id": "bench",
                    "cwd": "/p",
                    "hook_event_name": "PostToolUse",
                    "tool_name": "Read",
                    "tool_input": {"file_path": f"/proj/file{i}.md"},
                    "tool_response": "x" * 500,  # 500-char excerpt-sized content
                },
                event_type="post_tool",
            )
        )
    return out


def test_append_event_average_under_15ms(plugin_data_dir):
    n = 200
    events = _events_for_benchmark(n)
    start = time.perf_counter()
    for ev in events:
        append_event(ev, data_dir=plugin_data_dir)
    elapsed_s = time.perf_counter() - start
    avg_ms = (elapsed_s / n) * 1000.0
    # DESIGN §9.5 PostToolUse budget: 15ms (includes excerpt + redaction).
    # On laptop CI hardware we expect well under that.
    assert avg_ms < 15.0, f"append_event averaged {avg_ms:.2f}ms over {n} writes"


def test_session_with_1000_events_finalizes_in_reasonable_time(plugin_data_dir):
    """Stress: 1000 events should fully serialize in under a few seconds.
    Mainly guards against accidental O(n^2) regressions."""
    events = _events_for_benchmark(1000)
    start = time.perf_counter()
    for ev in events:
        append_event(ev, data_dir=plugin_data_dir)
    elapsed_s = time.perf_counter() - start
    # 1000 writes × 15ms each = 15s upper bound; we want <5s to catch
    # regressions early.
    assert elapsed_s < 5.0, f"1000 events took {elapsed_s:.2f}s"
