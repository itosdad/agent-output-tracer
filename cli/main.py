"""CLI entry point for `agent-output-tracer`.

Defines the argparse surface and dispatches to the query modules.
Exposed as a console script via the `[project.scripts]` table in
`pyproject.toml`.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from importlib import metadata


def _version() -> str:
    try:
        return metadata.version("agent-output-tracer")
    except metadata.PackageNotFoundError:
        return "0.0.0-dev"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-output-tracer",
        description=(
            "Forensic debugger for AI agent sessions. Replay, trace, and "
            "query agent behavior captured via Claude Code / Codex hooks."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_version()}",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help=("Override the plugin data directory (otherwise read from CLAUDE_PLUGIN_DATA)."),
    )

    subparsers = parser.add_subparsers(dest="cmd", metavar="COMMAND")
    subparsers.required = True

    # replay
    p_replay = subparsers.add_parser(
        "replay",
        help="Render a session's timeline.",
    )
    p_replay.add_argument(
        "--session",
        required=True,
        help=(
            "Session spec: full id, short prefix (>=4 chars), 'latest', "
            "'latest-N', or 'YYYY-MM-DD'."
        ),
    )
    p_replay.add_argument(
        "--format",
        dest="fmt",
        choices=["text", "json", "markdown"],
        default="text",
        help="Output format (default: text).",
    )
    p_replay.add_argument(
        "--show-hints",
        action="store_true",
        help="Emit anomaly hints alongside the timeline (Phase B-8).",
    )

    # list
    p_list = subparsers.add_parser(
        "list",
        help="List captured sessions (newest first).",
    )
    p_list.add_argument(
        "--last",
        type=int,
        default=None,
        help="Show only the N most recent sessions.",
    )
    p_list.add_argument(
        "--format",
        dest="fmt",
        choices=["text", "json"],
        default="text",
    )

    # latest
    subparsers.add_parser(
        "latest",
        help="Print the most-recent session id.",
    )

    # state-at
    p_state = subparsers.add_parser(
        "state-at",
        help="Snapshot of session state at a chosen moment.",
    )
    p_state.add_argument("--session", required=True)
    p_state.add_argument(
        "--time",
        required=True,
        help="ISO 8601 timestamp, HH:MM:SS (against session's date), or 'latest'.",
    )

    # grep
    p_grep = subparsers.add_parser(
        "grep",
        help="Full-text regex search across a session.",
    )
    p_grep.add_argument(
        "--session",
        required=True,
        help="Session spec (see `replay --help`).",
    )
    p_grep.add_argument(
        "--pattern",
        required=True,
        help="Python regex pattern.",
    )
    p_grep.add_argument(
        "-i",
        "--ignore-case",
        action="store_true",
        help="Match case-insensitively.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "replay":
        from core.session_io import SessionNotFoundError
        from core.session_resolver import (
            AmbiguousSessionSpec,
            SessionSpecNotFound,
            resolve_session_id,
        )
        from query.replay import replay

        try:
            resolved = resolve_session_id(args.session, data_dir=args.data_dir)
            replay(
                resolved,
                data_dir=args.data_dir,
                fmt=args.fmt,
                show_hints=args.show_hints,
                stream=sys.stdout,
            )
        except (SessionNotFoundError, SessionSpecNotFound, AmbiguousSessionSpec) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        return 0

    if args.cmd == "list":
        from query.list_sessions import list_command

        list_command(
            data_dir=args.data_dir,
            last=args.last,
            fmt=args.fmt,
            stream=sys.stdout,
        )
        return 0

    if args.cmd == "latest":
        from core.session_resolver import SessionSpecNotFound
        from query.latest import latest_command

        try:
            latest_command(data_dir=args.data_dir, stream=sys.stdout)
        except SessionSpecNotFound as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        return 0

    if args.cmd == "state-at":
        from core.session_io import SessionNotFoundError
        from core.session_resolver import (
            AmbiguousSessionSpec,
            SessionSpecNotFound,
            resolve_session_id,
        )
        from query.state_at import state_at

        try:
            resolved = resolve_session_id(args.session, data_dir=args.data_dir)
            state_at(
                resolved,
                args.time,
                data_dir=args.data_dir,
                stream=sys.stdout,
            )
        except (SessionNotFoundError, SessionSpecNotFound, AmbiguousSessionSpec) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        return 0

    if args.cmd == "grep":
        import re as _re

        from core.session_io import SessionNotFoundError
        from core.session_resolver import (
            AmbiguousSessionSpec,
            SessionSpecNotFound,
            resolve_session_id,
        )
        from query.grep import grep

        try:
            resolved = resolve_session_id(args.session, data_dir=args.data_dir)
            n = grep(
                resolved,
                args.pattern,
                data_dir=args.data_dir,
                ignore_case=args.ignore_case,
                stream=sys.stdout,
            )
        except (SessionNotFoundError, SessionSpecNotFound, AmbiguousSessionSpec) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        except _re.error as exc:
            print(f"error: invalid regex: {exc}", file=sys.stderr)
            return 2
        return 0 if n > 0 else 1  # grep convention: 1 means no match

    parser.error(f"unknown command: {args.cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
