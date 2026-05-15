"""CLI entry point for `agent-output-tracer` (alias: `aot`).

Defines the argparse surface and dispatches to the query modules.
Exposed as a console script via the `[project.scripts]` table in
`pyproject.toml`.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from importlib import metadata

from cli.colors import Palette
from cli.errors import print_error
from core.session_io import SessionNotFoundError
from core.session_resolver import (
    AmbiguousSessionSpec,
    SessionSpecNotFound,
    resolve_session_id,
)


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
    parser.add_argument(
        "--color",
        choices=["auto", "always", "never"],
        default="auto",
        help="Force color output on/off. 'auto' honors NO_COLOR and TTY (default).",
    )

    subparsers = parser.add_subparsers(dest="cmd", metavar="COMMAND")
    subparsers.required = True

    # replay
    p_replay = subparsers.add_parser("replay", help="Render a session's timeline.")
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
    p_replay.add_argument(
        "--watch",
        action="store_true",
        help="After the initial replay, follow events.jsonl until interrupted (Phase D-4).",
    )

    # list
    p_list = subparsers.add_parser("list", help="List captured sessions (newest first).")
    p_list.add_argument(
        "--last", type=int, default=None, help="Show only the N most recent sessions."
    )
    p_list.add_argument("--format", dest="fmt", choices=["text", "json"], default="text")

    # latest
    subparsers.add_parser("latest", help="Print the most-recent session id.")

    # diff
    p_diff = subparsers.add_parser("diff", help="Asymmetric diff: user mentions vs agent touches.")
    p_diff.add_argument("--session", required=True)

    # causal-graph
    p_cg = subparsers.add_parser(
        "causal-graph", help="Render the session as a mermaid causal graph."
    )
    p_cg.add_argument("--session", required=True)
    p_cg.add_argument(
        "--output", default=None, help="Write to this file (markdown). Defaults to stdout."
    )

    # gc
    p_gc = subparsers.add_parser(
        "gc", help="Apply retention policy (strip content >archive_days, delete >delete_days)."
    )
    p_gc.add_argument(
        "--archive-days",
        type=int,
        default=30,
        help="Strip content fields from sessions older than N days (default 30).",
    )
    p_gc.add_argument(
        "--delete-days",
        type=int,
        default=365,
        help="Remove session dirs older than N days (default 365).",
    )
    p_gc.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would happen without modifying anything.",
    )

    # export-trace
    p_export = subparsers.add_parser(
        "export-trace",
        help="Bundle replay / diff / mentioned-but-not-read / causal-graph into one report.",
    )
    p_export.add_argument("--session", required=True)
    p_export.add_argument(
        "--output", default=None, help="Write the markdown report to this file. Defaults to stdout."
    )

    # mentioned-but-not-read
    p_mbnr = subparsers.add_parser(
        "mentioned-but-not-read",
        help="Extract path-like tokens the agent mentioned but no visible source introduced.",
    )
    p_mbnr.add_argument("--session", required=True)

    # why
    p_why = subparsers.add_parser(
        "why", help="Surface the context that may have caused a specific event."
    )
    p_why.add_argument("--session", required=True)
    p_why.add_argument("--path", help="Filter by a path the event touches")
    p_why.add_argument("--tool", help="Filter by tool_name (Read, Bash, …)")
    p_why.add_argument("--ts", help="Disambiguate by timestamp (HH:MM:SS substring match)")
    p_why.add_argument(
        "--event-index", type=int, help="Direct address by 0-based events.jsonl index"
    )

    # trace
    p_trace = subparsers.add_parser(
        "trace", help="Reverse-lookup an output phrase to its causal trail."
    )
    p_trace.add_argument("--session", required=True)
    trace_mode = p_trace.add_mutually_exclusive_group(required=True)
    trace_mode.add_argument(
        "--output",
        help="Phrase to trace. The command finds the first agent_response containing it and walks back through prior events.",
    )
    trace_mode.add_argument(
        "--missing",
        help="Phrase that appeared in a tool_response but is absent from every subsequent agent_response (inverse hallucination).",
    )
    trace_mode.add_argument(
        "--by-sha",
        dest="by_sha",
        help="SHA256 of a tool_response. Lists every post_tool event with that content.",
    )
    p_trace.add_argument(
        "--reference-paths",
        dest="reference_paths",
        default=None,
        help="Comma-separated paths restricting --missing search.",
    )

    # state-at
    p_state = subparsers.add_parser(
        "state-at", help="Snapshot of session state at a chosen moment."
    )
    p_state.add_argument("--session", required=True)
    p_state.add_argument(
        "--time",
        required=True,
        help="ISO 8601 timestamp, HH:MM:SS (against session's date), or 'latest'.",
    )

    # grep
    p_grep = subparsers.add_parser("grep", help="Full-text regex search across a session.")
    p_grep.add_argument("--session", required=True, help="Session spec (see `replay --help`).")
    p_grep.add_argument("--pattern", required=True, help="Python regex pattern.")
    p_grep.add_argument(
        "-i", "--ignore-case", action="store_true", help="Match case-insensitively."
    )

    # doctor (D-1)
    p_doctor = subparsers.add_parser(
        "doctor", help="Self-diagnostic check of runtime, data dir, hook wiring."
    )
    p_doctor.add_argument("--format", dest="fmt", choices=["text", "json"], default="text")

    # config (D-1)
    p_config = subparsers.add_parser("config", help="Get/set CLI defaults.")
    cfg_sub = p_config.add_subparsers(dest="config_action", metavar="ACTION")
    cfg_sub.required = True
    p_cfg_get = cfg_sub.add_parser("get", help="Print one config value.")
    p_cfg_get.add_argument("key")
    p_cfg_set = cfg_sub.add_parser("set", help="Set one config value.")
    p_cfg_set.add_argument("key")
    p_cfg_set.add_argument("value")
    p_cfg_unset = cfg_sub.add_parser("unset", help="Clear one config value (revert to default).")
    p_cfg_unset.add_argument("key")
    cfg_sub.add_parser("list", help="List every key with its source (user/default).")

    # find (D-3)
    p_find = subparsers.add_parser(
        "find",
        help="Run anomaly vocabulary patterns (unmentioned-reads / repeated-reads / glob-burst / etc).",
    )
    p_find.add_argument(
        "vocab",
        help="Vocab term: unmentioned-reads / repeated-reads / glob-burst / routing-thrash / large-read / hallucinations / empty-glob / stale-cache / silent-failure / abandoned-write",
    )
    p_find.add_argument("--session", required=True)
    p_find.add_argument(
        "--threshold", type=int, default=None, help="Threshold override (vocab-specific)."
    )

    # bisect (D-3)
    p_bisect = subparsers.add_parser("bisect", help="Binary search across a session timeline.")
    bisect_sub = p_bisect.add_subparsers(dest="bisect_action", metavar="ACTION")
    bisect_sub.required = True
    p_bstart = bisect_sub.add_parser("start", help="Begin a bisect on a session.")
    p_bstart.add_argument("--session", required=True)
    p_bstart.add_argument(
        "--from", dest="lo", type=int, default=None, help="Lower bound (event idx)"
    )
    p_bstart.add_argument("--to", dest="hi", type=int, default=None, help="Upper bound (event idx)")
    for verb in ("good", "bad", "skip", "view", "status", "log", "quit"):
        p = bisect_sub.add_parser(verb, help=f"bisect {verb}")
        p.add_argument("--session", required=True)

    # note (D-3)
    p_note = subparsers.add_parser("note", help="Attach a human note to a session.")
    note_sub = p_note.add_subparsers(dest="note_action", metavar="ACTION")
    note_sub.required = True
    p_n_add = note_sub.add_parser("add", help="Add a note.")
    p_n_add.add_argument("--session", required=True)
    p_n_add.add_argument("body", help="Note body.")
    p_n_add.add_argument("--tag", default="observation", help="Tag (default 'observation').")
    p_n_add.add_argument(
        "--event", dest="event_idx", type=int, default=None, help="Anchor to an event index."
    )
    p_n_add.add_argument(
        "--finding", dest="finding_idx", type=int, default=None, help="Anchor to a finding index."
    )
    p_n_list = note_sub.add_parser("list", help="List notes on a session.")
    p_n_list.add_argument("--session", required=True)
    p_n_list.add_argument("--tag", default=None, help="Filter by tag.")
    p_n_rm = note_sub.add_parser("rm", help="Remove a note by id.")
    p_n_rm.add_argument("--session", required=True)
    p_n_rm.add_argument("--id", dest="note_id", required=True)

    # stats (D-3)
    p_stats = subparsers.add_parser("stats", help="Forensic statistics for a session.")
    p_stats.add_argument("--session", required=True)
    p_stats.add_argument("--format", dest="fmt", choices=["text", "json"], default="text")

    # tui (D-5)
    p_tui = subparsers.add_parser(
        "tui",
        help="Open the side-channel TUI (D-5; requires the [tui] extra).",
    )
    p_tui.add_argument(
        "--session",
        default=None,
        help=(
            "Optional initial session spec. When omitted, the TUI lands "
            "on the Home screen. When provided (id, prefix, or 'latest'), "
            "drills directly into that session's timeline; Esc still "
            "navigates back to Home."
        ),
    )

    # export (D-7 safe-share)
    p_xport = subparsers.add_parser(
        "export",
        help="Safe-share export of a session (D-7, sanitised).",
    )
    p_xport.add_argument("--session", required=True)
    p_xport.add_argument(
        "--safe-share",
        action="store_true",
        help="Always set in D-7 (default).",
    )
    p_xport.add_argument(
        "--format",
        dest="fmt",
        choices=["markdown", "json", "archive"],
        default="markdown",
    )
    p_xport.add_argument(
        "--keep-excerpt",
        type=int,
        default=0,
        help="Retain N leading characters of each tool_response (default 0).",
    )
    p_xport.add_argument(
        "--output",
        default=None,
        help="Output path. Required for --format archive.",
    )

    # review (D-6)
    p_review = subparsers.add_parser(
        "review",
        help="User-explicit cross-session summary (D-6, builds the global index).",
    )
    p_review.add_argument("--since", default=None, help="ISO date lower bound on ts_end.")
    p_review.add_argument("--until", default=None, help="ISO date upper bound on ts_end.")
    p_review.add_argument("--format", dest="fmt", choices=["text", "json"], default="text")

    # tail (D-4)
    p_tail = subparsers.add_parser(
        "tail",
        help="Follow events.jsonl as a session progresses (D-4).",
    )
    p_tail.add_argument("--session", required=True)
    p_tail.add_argument(
        "--format",
        dest="fmt",
        choices=["text", "stream-json"],
        default="text",
    )
    p_tail.add_argument(
        "--from-start",
        action="store_true",
        help="Render existing events first, then tail.",
    )
    p_tail.add_argument(
        "--poll-interval",
        type=float,
        default=0.5,
        help="Seconds between filesystem polls (default 0.5).",
    )
    p_tail.add_argument(
        "--stop-after",
        type=float,
        default=None,
        help="Bail out after N seconds (mainly for CI/tests).",
    )

    return parser


# --- shared session resolution wrapper (DRY for the 11 commands that need it) ---


def _resolve(spec: str, data_dir: str | None, palette: Palette) -> str | None:
    """Resolve a session spec or print a 3-line error and return None."""
    try:
        return resolve_session_id(spec, data_dir=data_dir)
    except AmbiguousSessionSpec as exc:
        print_error(
            f"session spec {spec!r} is ambiguous",
            cause=str(exc),
            tries=[f"aot list --filter prefix={spec}"],
            palette=palette,
        )
        return None
    except SessionSpecNotFound as exc:
        print_error(
            f"no session matches {spec!r}",
            cause=str(exc),
            tries=["aot list", "aot latest"],
            palette=palette,
        )
        return None
    except SessionNotFoundError as exc:
        print_error(
            f"session {spec!r} could not be loaded",
            cause=str(exc),
            tries=["aot doctor", f"aot list --filter prefix={spec}"],
            palette=palette,
        )
        return None


def _with_session(args, palette: Palette, body: Callable[[str], int]) -> int:
    resolved = _resolve(args.session, args.data_dir, palette)
    if resolved is None:
        return 2
    try:
        return body(resolved)
    except SessionNotFoundError as exc:
        print_error(
            f"session {resolved!r} disappeared mid-query",
            cause=str(exc),
            tries=["aot doctor"],
            palette=palette,
        )
        return 2


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    palette = Palette(color_mode=args.color, stream=sys.stderr)

    if args.cmd == "replay":
        from query.replay import replay

        def run(resolved: str) -> int:
            replay(
                resolved,
                data_dir=args.data_dir,
                fmt=args.fmt,
                show_hints=args.show_hints,
                stream=sys.stdout,
            )
            if args.watch:
                from query.tail import tail

                sys.stdout.write("\n--- following (Ctrl+C to stop) ---\n")
                sys.stdout.flush()
                try:
                    tail(
                        resolved,
                        data_dir=args.data_dir,
                        fmt=args.fmt if args.fmt == "json" else "text",
                        stream=sys.stdout,
                    )
                except KeyboardInterrupt:
                    pass
            return 0

        return _with_session(args, palette, run)

    if args.cmd == "list":
        from query.list_sessions import list_command

        list_command(data_dir=args.data_dir, last=args.last, fmt=args.fmt, stream=sys.stdout)
        return 0

    if args.cmd == "latest":
        from query.latest import latest_command

        try:
            latest_command(data_dir=args.data_dir, stream=sys.stdout)
        except SessionSpecNotFound as exc:
            print_error(
                "no sessions captured yet",
                cause=str(exc),
                tries=["aot doctor", "run a tool call in Claude Code or Codex"],
                palette=palette,
            )
            return 2
        return 0

    if args.cmd == "diff":
        from query.diff import diff

        def run(resolved: str) -> int:
            diff(resolved, data_dir=args.data_dir, stream=sys.stdout)
            return 0

        return _with_session(args, palette, run)

    if args.cmd == "gc":
        from core.retention import run_gc

        result = run_gc(
            data_dir=args.data_dir,
            archive_days=args.archive_days,
            delete_days=args.delete_days,
            dry_run=args.dry_run,
        )
        prefix = "[dry-run] " if result["dry_run"] else ""
        print(
            f"{prefix}stripped {result['stripped_count']}, "
            f"deleted {result['deleted_count']}, "
            f"untouched {result['untouched_count']}, "
            f"skipped {result['skipped_count']}."
        )
        if result["stripped"]:
            print("Stripped:")
            for s in result["stripped"]:
                print(f"  - {s}")
        if result["deleted"]:
            print("Deleted:")
            for s in result["deleted"]:
                print(f"  - {s}")
        return 0

    if args.cmd == "export-trace":
        from query.export import export_trace

        def run(resolved: str) -> int:
            export_trace(
                resolved,
                data_dir=args.data_dir,
                output_path=args.output,
                stream=sys.stdout,
            )
            return 0

        return _with_session(args, palette, run)

    if args.cmd == "causal-graph":
        from query.causal_graph import causal_graph

        def run(resolved: str) -> int:
            causal_graph(
                resolved,
                data_dir=args.data_dir,
                output_path=args.output,
                stream=sys.stdout,
            )
            return 0

        return _with_session(args, palette, run)

    if args.cmd == "mentioned-but-not-read":
        from query.mentioned_but_not_read import mentioned_but_not_read

        resolved = _resolve(args.session, args.data_dir, palette)
        if resolved is None:
            return 2
        result = mentioned_but_not_read(resolved, data_dir=args.data_dir, stream=sys.stdout)
        return 3 if result.get("candidates") else 0

    if args.cmd == "why":
        from query.why import EventNotFound, why

        resolved = _resolve(args.session, args.data_dir, palette)
        if resolved is None:
            return 2
        try:
            why(
                resolved,
                path=args.path,
                tool=args.tool,
                ts=args.ts,
                event_index=args.event_index,
                data_dir=args.data_dir,
                stream=sys.stdout,
            )
        except EventNotFound as exc:
            print_error(
                "no event matched the filter",
                cause=str(exc),
                tries=[f"aot replay --session {args.session} --brief"],
                palette=palette,
            )
            return 1
        return 0

    if args.cmd == "trace":
        from query.trace import trace, trace_by_sha, trace_missing

        resolved = _resolve(args.session, args.data_dir, palette)
        if resolved is None:
            return 2
        if args.output:
            result = trace(resolved, args.output, data_dir=args.data_dir, stream=sys.stdout)
            return 3 if result.get("hallucination_candidate") else 0
        if args.missing:
            refs = (
                [p.strip() for p in args.reference_paths.split(",") if p.strip()]
                if args.reference_paths
                else None
            )
            result = trace_missing(
                resolved,
                args.missing,
                reference_paths=refs,
                data_dir=args.data_dir,
                stream=sys.stdout,
            )
            return 3 if result.get("missing") else 0
        if args.by_sha:
            result = trace_by_sha(
                resolved,
                args.by_sha,
                data_dir=args.data_dir,
                stream=sys.stdout,
            )
            return 0 if result.get("matches") else 1

    if args.cmd == "state-at":
        from query.state_at import state_at

        resolved = _resolve(args.session, args.data_dir, palette)
        if resolved is None:
            return 2
        try:
            state_at(resolved, args.time, data_dir=args.data_dir, stream=sys.stdout)
        except ValueError as exc:
            print_error(
                "bad --time value",
                cause=str(exc),
                tries=["aot state-at --time latest", "aot state-at --time 10:23:45"],
                palette=palette,
            )
            return 2
        return 0

    if args.cmd == "grep":
        import re as _re

        from query.grep import grep

        resolved = _resolve(args.session, args.data_dir, palette)
        if resolved is None:
            return 2
        try:
            n = grep(
                resolved,
                args.pattern,
                data_dir=args.data_dir,
                ignore_case=args.ignore_case,
                stream=sys.stdout,
            )
        except _re.error as exc:
            print_error(
                "invalid regex",
                cause=str(exc),
                tries=["aot grep --pattern 'foo' --session latest"],
                palette=palette,
            )
            return 2
        return 0 if n > 0 else 1

    if args.cmd == "doctor":
        from query.doctor import doctor

        result = doctor(data_dir=args.data_dir, fmt=args.fmt, stream=sys.stdout)
        return 0 if result["ok"] else 1

    if args.cmd == "config":
        from query.config_cmd import config_get, config_list, config_set, config_unset

        try:
            if args.config_action == "get":
                return config_get(args.key, stream=sys.stdout)
            if args.config_action == "set":
                return config_set(args.key, args.value)
            if args.config_action == "unset":
                return config_unset(args.key)
            if args.config_action == "list":
                return config_list(stream=sys.stdout)
        except ValueError as exc:
            print_error(
                "config error",
                cause=str(exc),
                tries=["aot config list    # see valid keys"],
                palette=palette,
            )
            return 2

    if args.cmd == "find":
        from query.find import find

        resolved = _resolve(args.session, args.data_dir, palette)
        if resolved is None:
            return 2
        try:
            result = find(
                resolved,
                args.vocab,
                threshold=args.threshold,
                data_dir=args.data_dir,
                stream=sys.stdout,
            )
        except ValueError as exc:
            print_error(
                "unknown find vocab",
                cause=str(exc),
                tries=["aot find repeated-reads --session latest"],
                palette=palette,
            )
            return 2
        return 0 if result["matches"] else 1

    if args.cmd == "bisect":
        from query.bisect import (
            BisectError,
            bisect_log,
            bisect_mark,
            bisect_quit,
            bisect_start,
            bisect_status,
            bisect_view,
        )

        resolved = _resolve(args.session, args.data_dir, palette)
        if resolved is None:
            return 2
        try:
            if args.bisect_action == "start":
                bisect_start(
                    resolved,
                    lo=args.lo,
                    hi=args.hi,
                    data_dir=args.data_dir,
                    stream=sys.stdout,
                )
            elif args.bisect_action in ("good", "bad", "skip"):
                bisect_mark(
                    resolved,
                    args.bisect_action,
                    data_dir=args.data_dir,
                    stream=sys.stdout,
                )
            elif args.bisect_action == "view":
                bisect_view(resolved, data_dir=args.data_dir, stream=sys.stdout)
            elif args.bisect_action == "status":
                bisect_status(resolved, data_dir=args.data_dir, stream=sys.stdout)
            elif args.bisect_action == "log":
                bisect_log(resolved, data_dir=args.data_dir, stream=sys.stdout)
            elif args.bisect_action == "quit":
                bisect_quit(resolved, data_dir=args.data_dir, stream=sys.stdout)
        except BisectError as exc:
            print_error(
                "bisect error",
                cause=str(exc),
                tries=[f"aot bisect start --session {args.session}"],
                palette=palette,
            )
            return 2
        return 0

    if args.cmd == "note":
        from query.note import NoteError, note_add, note_list, note_rm

        resolved = _resolve(args.session, args.data_dir, palette)
        if resolved is None:
            return 2
        try:
            if args.note_action == "add":
                note_add(
                    resolved,
                    args.body,
                    tag=args.tag,
                    event_idx=args.event_idx,
                    finding_idx=args.finding_idx,
                    data_dir=args.data_dir,
                    stream=sys.stdout,
                )
            elif args.note_action == "list":
                note_list(
                    resolved,
                    tag=args.tag,
                    data_dir=args.data_dir,
                    stream=sys.stdout,
                )
            elif args.note_action == "rm":
                ok = note_rm(
                    resolved,
                    args.note_id,
                    data_dir=args.data_dir,
                    stream=sys.stdout,
                )
                return 0 if ok else 1
        except NoteError as exc:
            print_error(
                "note error",
                cause=str(exc),
                tries=["aot note add --session latest --tag observation 'body...'"],
                palette=palette,
            )
            return 2
        return 0

    if args.cmd == "stats":
        from query.stats import stats

        resolved = _resolve(args.session, args.data_dir, palette)
        if resolved is None:
            return 2
        stats(resolved, data_dir=args.data_dir, fmt=args.fmt, stream=sys.stdout)
        return 0

    if args.cmd == "tui":
        from tui import is_available

        if not is_available():
            print_error(
                "'aot tui' requires the [tui] optional dependencies",
                cause="textual / watchdog not installed",
                tries=["pip install 'agent-output-tracer[tui]'"],
                palette=palette,
            )
            return 2
        from tui.app import run as tui_run

        try:
            return tui_run(args.session, data_dir=args.data_dir)
        except Exception as exc:  # textual itself can raise startup errors
            print_error(
                "TUI startup failed",
                cause=str(exc),
                tries=["aot doctor", f"aot replay --session {args.session}"],
                palette=palette,
            )
            return 2

    if args.cmd == "export":
        from query.export import export_safe_share

        resolved = _resolve(args.session, args.data_dir, palette)
        if resolved is None:
            return 2
        try:
            export_safe_share(
                resolved,
                data_dir=args.data_dir,
                fmt=args.fmt,
                keep_excerpt=args.keep_excerpt,
                output_path=args.output,
                stream=sys.stdout,
            )
        except ValueError as exc:
            print_error(
                "export error",
                cause=str(exc),
                tries=["aot export --session latest --format markdown"],
                palette=palette,
            )
            return 2
        return 0

    if args.cmd == "review":
        from query.review import review

        review(
            since=args.since,
            until=args.until,
            data_dir=args.data_dir,
            fmt=args.fmt,
            stream=sys.stdout,
        )
        return 0

    if args.cmd == "tail":
        from query.tail import tail

        resolved = _resolve(args.session, args.data_dir, palette)
        if resolved is None:
            return 2
        try:
            tail(
                resolved,
                data_dir=args.data_dir,
                fmt=args.fmt,
                from_start=args.from_start,
                poll_interval=args.poll_interval,
                stop_after_seconds=args.stop_after,
                stream=sys.stdout,
            )
        except KeyboardInterrupt:
            pass
        return 0

    parser.error(f"unknown command: {args.cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
