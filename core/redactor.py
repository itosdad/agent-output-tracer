"""Secret-pattern redactor.

Applied to normalized events before they are written to events.jsonl
(DESIGN §9.3). Read-mostly: a list of default regexes covers the common
secret shapes (API keys, GitHub PATs, key=value pairs for password /
token / secret). Callers can extend with project-specific patterns
through the config file.

3.9-compat (loaded by hook scripts running under the user's `python3`).
"""

from __future__ import annotations

import copy
import re

DEFAULT_REPLACEMENT = "[REDACTED]"


# Each pattern is paired with a flags value (0 means no flags). Stored as
# tuples so individual patterns can opt in to IGNORECASE without
# polluting the rest.
DEFAULT_PATTERN_SPECS = [
    # OpenAI-style API key (sk-...)
    (r"sk-[A-Za-z0-9]{20,}", 0),
    # Anthropic-style (sk-ant-...)
    (r"sk-ant-[A-Za-z0-9_\-]{20,}", 0),
    # GitHub personal access token / app token
    (r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b", 0),
    # AWS access key id
    (r"\bAKIA[0-9A-Z]{16}\b", 0),
    # JWT (eyJ...eyJ...sig)
    (r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b", 0),
    # Generic secret-y key=value: at least 16 chars of value
    (
        r"(?:password|passwd|api[_-]?key|secret|token|auth)\s*[:=]\s*"
        r"['\"]?([A-Za-z0-9_\-]{16,})['\"]?",
        re.IGNORECASE,
    ),
]

# Flat string list of just the source patterns — what `config.toml`
# typically wants to extend.
DEFAULT_PATTERNS = [spec[0] for spec in DEFAULT_PATTERN_SPECS]


def _compile_one(pattern, flags=0):
    try:
        return re.compile(pattern, flags)
    except re.error:
        return None


def compile_patterns(patterns):
    """Compile a list of regex strings. Silently drop invalid entries."""
    out = []
    for p in patterns or []:
        compiled = _compile_one(p)
        if compiled is not None:
            out.append(compiled)
    return out


def _get_active_patterns(custom, include_defaults):
    """Build the working set of compiled patterns for this call."""
    actives = []
    if include_defaults:
        for src, flags in DEFAULT_PATTERN_SPECS:
            compiled = _compile_one(src, flags)
            if compiled is not None:
                actives.append(compiled)
    if custom:
        actives.extend(compile_patterns(custom))
    return actives


def redact_text(text, patterns=None, *, replacement=DEFAULT_REPLACEMENT, include_defaults=True):
    """Replace every match of every pattern with `replacement`.

    Non-string input (including None) is returned unchanged.
    """
    if not isinstance(text, str):
        return text
    actives = _get_active_patterns(patterns, include_defaults)
    out = text
    for regex in actives:
        out = regex.sub(replacement, out)
    return out


def redact_event(event, patterns=None, *, replacement=DEFAULT_REPLACEMENT, include_defaults=True):
    """Deep-copy the event and redact every string within it.

    Non-dict inputs pass through unchanged (including None).
    """
    if not isinstance(event, dict):
        return event
    cloned = copy.deepcopy(event)
    actives = _get_active_patterns(patterns, include_defaults)
    if not actives:
        return cloned

    def _walk(node):
        if isinstance(node, str):
            out = node
            for regex in actives:
                out = regex.sub(replacement, out)
            return out
        if isinstance(node, list):
            return [_walk(item) for item in node]
        if isinstance(node, dict):
            return {k: _walk(v) for k, v in node.items()}
        return node

    return _walk(cloned)
