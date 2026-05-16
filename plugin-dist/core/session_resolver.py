"""Resolve a user-facing session spec (DESIGN §8.3) to a concrete id.

Accepted forms:
  - `latest`         — most recent session by ts_end
  - `latest-N`       — N-th most recent (latest-0 == latest)
  - `<full_id>`      — exact match
  - `<short_id>`     — unique prefix of at least 4 characters
  - `YYYY-MM-DD`     — most recent session whose ts_start has that date

Tag lookup is intentionally not part of Phase A (no `tag` command yet);
it will land alongside §8.2's auxiliary commands.
"""

from __future__ import annotations

import re

from core.session_io import list_sessions

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LATEST_N = re.compile(r"^latest-(\d+)$")
MIN_PREFIX_LEN = 4


class SessionSpecNotFound(LookupError):
    """No session matched the spec."""


class AmbiguousSessionSpec(LookupError):
    """The prefix matched more than one session."""


def _ts_for_ordering(meta):
    return meta.get("ts_end") or meta.get("ts_start") or ""


def _sorted_sessions(data_dir):
    """Return sessions newest-first (matches list_sessions's order)."""
    return list_sessions(data_dir=data_dir)


def resolve_session_id(spec, *, data_dir=None):
    if not isinstance(spec, str) or not spec:
        raise SessionSpecNotFound(f"empty session spec: {spec!r}")

    sessions = _sorted_sessions(data_dir)
    ids = [s["session_id"] for s in sessions if s.get("session_id")]

    # 1. exact id
    if spec in ids:
        return spec

    # 2. `latest`
    if spec == "latest":
        if not sessions:
            raise SessionSpecNotFound("no sessions captured yet")
        return sessions[0]["session_id"]

    # 3. `latest-N`
    m = LATEST_N.match(spec)
    if m:
        n = int(m.group(1))
        if n >= len(sessions):
            raise SessionSpecNotFound(f"only {len(sessions)} session(s); latest-{n} out of range")
        return sessions[n]["session_id"]

    # 4. ISO date — newest session whose ts_start lies on that date
    if ISO_DATE.match(spec):
        for s in sessions:
            ts = s.get("ts_start") or s.get("ts_end") or ""
            if ts.startswith(spec):
                return s["session_id"]
        raise SessionSpecNotFound(f"no session on {spec}")

    # 5. short prefix (only when >= 4 chars to avoid surprise matches)
    if len(spec) >= MIN_PREFIX_LEN:
        matches = [sid for sid in ids if sid.startswith(spec)]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise AmbiguousSessionSpec(
                f"prefix {spec!r} matches {len(matches)} sessions: "
                + ", ".join(sorted(matches)[:5])
            )

    raise SessionSpecNotFound(f"no session matches {spec!r}")
