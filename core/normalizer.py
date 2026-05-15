"""Engine dispatcher for event normalization.

Hook scripts know which engine they live under (they import a specific
adapter). This module is for callers that want to dispatch dynamically
(e.g. tests, future multi-engine code paths).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from adapters import claude_code as _claude_code

SUPPORTED_ENGINES: dict[str, Callable] = {
    "claude-code": _claude_code.normalize_event,
}


def normalize(
    engine: str,
    raw: Any,
    event_type: str | None = None,
    *,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any] | None:
    """Dispatch to the engine's adapter. Unknown engine → None."""
    adapter = SUPPORTED_ENGINES.get(engine)
    if adapter is None:
        return None
    return adapter(raw, event_type=event_type, now=now)
