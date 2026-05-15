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

    parser.error(f"unknown command: {args.cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
