"""Path-like token extraction from free-form text.

Used by the forensic commands that need to compare what the user or
the agent said about files against what was actually touched
(`query/diff.py`, `query/mentioned_but_not_read.py`, …).

The token shapes covered (URL pattern is tried first so schemed URLs
survive intact):
- full URL:                `https://github.com/foo/bar`
- absolute path:           `/foo/bar.md`
- home-relative:           `~/foo/bar`
- explicit relative:       `./foo`, `../bar`
- bare basename-with-ext:  `foo.tsx`, `README.md`

The path-content character class is intentionally ASCII-only — Japanese
or other non-ASCII characters do not appear in real file paths in this
codebase, and admitting them lets the regex eat free-form prose like
"メール/電話/長い hex" as a path. Trailing sentence punctuation is
stripped on the extracted token.

3.9-compat (loaded by hook-side code only indirectly through query/).
"""

from __future__ import annotations

import re

# Order matters: URL must come before the bare path patterns so that
# the `https:` scheme survives instead of the path-pattern stealing
# only the `//github.com/...` tail.
PATH_TOKEN = re.compile(
    r"(?:"
    # URL: scheme://… up to whitespace/quote/bracket
    r"https?://[A-Za-z0-9._~:/?#@!$&*+,;=%\-]+"
    # Absolute / home-relative path, ASCII only
    r"|[/~][A-Za-z0-9_\-./]+"
    # Explicit relative path
    r"|\.{1,2}/[A-Za-z0-9_\-./]+"
    # Bare basename with extension
    r"|\b[A-Za-z0-9_\-]+\.[A-Za-z0-9]{1,5}\b"
    r")",
    re.ASCII,
)

_TRAILING_PUNCT = ".,;:!?"


def extract_path_tokens(text):
    """Return the set of path-like tokens found in `text`."""
    if not isinstance(text, str) or not text:
        return set()
    raw = PATH_TOKEN.findall(text)
    return {tok.rstrip(_TRAILING_PUNCT) for tok in raw if tok}


# ---------- self-paste filtering ----------

# `aot find <vocab>` text output. Header + zero-or-more indented rows.
_FIND_OUTPUT_RE = re.compile(
    r"find '[a-z\-]+': \d+ match\(es\)\n"
    r"(?:[ \t]+\[\d{2}:\d{2}:\d{2}\] event \d+[^\n]*\n)*",
    re.ASCII,
)
# `aot find <vocab>`: empty-match path (the "No matches" line on its own).
_FIND_NOMATCH_RE = re.compile(r"No matches for find vocab '[a-z\-]+'\.\n", re.ASCII)
# `aot mentioned-but-not-read` text output.
_MBR_OUTPUT_RE = re.compile(
    r"Session: [A-Za-z0-9\-]+\s*\n\s*\n"
    r"Hallucination candidates[^\n]*\n"
    r"(?:[ \t]+- [^\n]+\n)*",
    re.ASCII,
)


def strip_tracer_output(text):
    """Remove pasted-back `aot find` / `mentioned-but-not-read` output blocks.

    When an operator pastes the tracer's own output into a follow-up
    user prompt, every previously-flagged token suddenly looks grounded
    to the next detector run, causing the detector to silently consume
    its own warnings. We recognise the output by its CLI-controlled
    fingerprint (which the operator has no incentive to forge) and
    excise the matching span before treating `text` as a grounding
    corpus.
    """
    if not isinstance(text, str) or not text:
        return text
    text = _FIND_OUTPUT_RE.sub(" ", text)
    text = _FIND_NOMATCH_RE.sub(" ", text)
    text = _MBR_OUTPUT_RE.sub(" ", text)
    return text


def is_grounded(token, *corpora):
    """True iff `token`, its trailing-slash-stripped form, or its
    basename appears as a substring in any of the given corpora."""
    import os

    stripped = token.rstrip("/")
    base = os.path.basename(stripped) or stripped
    for haystack in corpora:
        if not haystack:
            continue
        if token in haystack or stripped in haystack:
            return True
        if base and base in haystack:
            return True
    return False
