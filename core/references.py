"""Path-like token extraction from free-form text.

Used by the forensic commands that need to compare what the user or
the agent said about files against what was actually touched
(`query/diff.py`, `query/mentioned_but_not_read.py`, …).

The token shapes covered:
- absolute path:           `/foo/bar.md`
- home-relative:           `~/foo/bar`
- explicit relative:       `./foo`, `../bar`
- bare basename-with-ext:  `foo.tsx`, `README.md`

Stopped at whitespace, common punctuation, quotes, and brackets.
Trailing sentence punctuation is stripped on the extracted token.

3.9-compat (loaded by hook-side code only indirectly through query/).
"""

from __future__ import annotations

import re

PATH_TOKEN = re.compile(
    r"(?:[/~][^\s,()\[\]\'\"`]+"
    r"|\.{1,2}/[^\s,()\[\]\'\"`]+"
    r"|\b[\w\-.]+\.[A-Za-z0-9]{1,5}\b)"
)

_TRAILING_PUNCT = ".,;:!?"


def extract_path_tokens(text):
    """Return the set of path-like tokens found in `text`."""
    if not isinstance(text, str) or not text:
        return set()
    raw = PATH_TOKEN.findall(text)
    return {tok.rstrip(_TRAILING_PUNCT) for tok in raw if tok}
