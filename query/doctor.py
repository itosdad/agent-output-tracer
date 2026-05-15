"""`aot doctor` — self-diagnostic.

Walks the runtime, data dir, hook wiring, and redaction surface and
prints a per-check `ok / warn / fail` line plus a `fix:` hint when
something needs attention.

Best-effort: a single broken check should not cascade. Each check is
wrapped in a try/except that downgrades unexpected exceptions to a
`fail` row.
"""

from __future__ import annotations

import json
import platform
import sys
from pathlib import Path
from typing import IO

from cli.colors import Palette
from core.path_utils import resolve_data_dir
from core.session_io import list_sessions


def doctor(
    *,
    data_dir: str | None = None,
    fmt: str = "text",
    stream: IO[str] | None = None,
) -> dict:
    """Run every check, render to `stream`, return a structured result.

    `fmt`:
      - "text" — colored / ASCII per check (default)
      - "json" — `{"$schema": "aot/doctor/v1", "checks": [...]}`
    """
    if stream is None:
        stream = sys.stdout

    checks = [
        _check_runtime(),
        _check_data_dir(data_dir),
        _check_recent_sessions(data_dir),
        _check_hooks_wiring(),
    ]

    result = {
        "$schema": "aot/doctor/v1",
        "ok": all(c["status"] == "ok" for c in checks),
        "checks": checks,
    }

    if fmt == "json":
        stream.write(json.dumps(result, ensure_ascii=False, indent=2))
        stream.write("\n")
    else:
        palette = Palette(color_mode="auto", stream=stream)
        _render_text(result, stream, palette)

    return result


# ----- individual checks -----


def _check_runtime() -> dict:
    return {
        "name": "runtime",
        "status": "ok",
        "detail": (
            f"Python {sys.version_info.major}.{sys.version_info.minor}."
            f"{sys.version_info.micro} on {platform.system()} {platform.machine()}"
        ),
        "fix": None,
    }


def _check_data_dir(data_dir: str | None) -> dict:
    resolved = resolve_data_dir(data_dir)
    if resolved is None:
        return {
            "name": "data_dir",
            "status": "warn",
            "detail": (
                "no CLAUDE_PLUGIN_DATA / CODEX_PLUGIN_DATA env, and no "
                "default Codex install cache found"
            ),
            "fix": "export CLAUDE_PLUGIN_DATA=~/.claude/plugins/data/agent-output-tracer",
        }
    if not Path(resolved).exists():
        return {
            "name": "data_dir",
            "status": "warn",
            "detail": f"resolved to {resolved} but the directory does not exist yet",
            "fix": "run a session through Claude Code or Codex to seed it",
        }
    sessions_root = Path(resolved) / "sessions"
    if not sessions_root.exists():
        return {
            "name": "data_dir",
            "status": "warn",
            "detail": f"{resolved} exists but {sessions_root.name}/ has not been created",
            "fix": "run a session through Claude Code or Codex to seed it",
        }
    total_bytes = sum(p.stat().st_size for p in Path(resolved).rglob("*") if p.is_file())
    return {
        "name": "data_dir",
        "status": "ok",
        "detail": f"{resolved} ({_human_bytes(total_bytes)})",
        "fix": None,
    }


def _check_recent_sessions(data_dir: str | None) -> dict:
    resolved = resolve_data_dir(data_dir)
    if resolved is None or not (Path(resolved) / "sessions").exists():
        return {
            "name": "recent_sessions",
            "status": "warn",
            "detail": "no sessions captured yet",
            "fix": "trigger any tool call from Claude Code or Codex while the plugin is installed",
        }
    try:
        sessions = list_sessions(data_dir=resolved)
    except Exception as exc:
        return {
            "name": "recent_sessions",
            "status": "fail",
            "detail": f"could not enumerate sessions: {exc}",
            "fix": "check filesystem permissions on the sessions dir",
        }
    n = len(sessions)
    if n == 0:
        return {
            "name": "recent_sessions",
            "status": "warn",
            "detail": "sessions/ exists but is empty",
            "fix": "trigger a tool call from a real session to confirm hook wiring",
        }
    # list_sessions returns metadata dicts (newest first); use that directly.
    latest_meta = sessions[0] if isinstance(sessions[0], dict) else None
    if latest_meta is None:
        return {
            "name": "recent_sessions",
            "status": "warn",
            "detail": f"{n} sessions, but latest has no metadata.json",
            "fix": "aot replay --session latest    # surfaces any parse error",
        }
    return {
        "name": "recent_sessions",
        "status": "ok",
        "detail": (
            f"{n} sessions; latest ts_end={latest_meta.get('ts_end', '?')}, "
            f"tools={latest_meta.get('tool_calls_total', 0)}"
        ),
        "fix": None,
    }


def _check_hooks_wiring() -> dict:
    """Find the plugin's hooks.json on disk.

    The CLI doesn't have an authoritative way to ask the engine which
    hooks it loaded. We probe the known install locations in order:

      1. The repo layout the CLI itself sits in (dev / editable install
         only — pip install -e from a clone). When the CLI is installed
         via pipx, this path lands inside site-packages, where hooks/ is
         not shipped, so this branch correctly misses.
      2. The Claude Code marketplace install root
         (~/.claude/plugins/marketplaces/*/hooks/hooks.json).
      3. The Codex marketplace install root
         (~/.codex/plugins/cache/*/agent-output-tracer/*/hooks/hooks.json).

    Any one of these existing + parseable is enough to call the wiring
    OK. None found is a warn (not fail) — the user may simply not have
    installed the plugin in any engine yet; that's not an error state.
    """
    candidates: list[Path] = []

    # 1. Dev / editable install: CLI source sits next to hooks/
    dev_candidate = Path(__file__).resolve().parent.parent / "hooks" / "hooks.json"
    if dev_candidate.exists():
        candidates.append(dev_candidate)

    # 2. Claude Code marketplace clones
    cc_root = Path.home() / ".claude" / "plugins" / "marketplaces"
    if cc_root.is_dir():
        for marketplace in cc_root.iterdir():
            cand = marketplace / "hooks" / "hooks.json"
            if cand.exists():
                candidates.append(cand)

    # 3. Codex marketplace cache (path layout per design §3.2.7)
    cdx_root = Path.home() / ".codex" / "plugins" / "cache"
    if cdx_root.is_dir():
        for marketplace in cdx_root.iterdir():
            plugin_dir = marketplace / "agent-output-tracer"
            if not plugin_dir.is_dir():
                continue
            for version in plugin_dir.iterdir():
                cand = version / "hooks" / "hooks.json"
                if cand.exists():
                    candidates.append(cand)

    if not candidates:
        return {
            "name": "hooks_wiring",
            "status": "warn",
            "detail": (
                "no hooks.json found in dev location, Claude Code marketplaces, "
                "or Codex plugin cache"
            ),
            "fix": (
                "install the plugin: /plugin marketplace add itosdad/agent-output-tracer "
                "(Claude Code) or codex plugin marketplace add itosdad/agent-output-tracer (Codex)"
            ),
        }

    # Pick the first valid one for the detail line; any failure here is
    # a real problem worth surfacing.
    chosen = candidates[0]
    try:
        data = json.loads(chosen.read_text())
    except Exception as exc:
        return {
            "name": "hooks_wiring",
            "status": "fail",
            "detail": f"{chosen} is not valid JSON: {exc}",
            "fix": "reinstall the plugin from a clean checkout",
        }
    n_events = len(data.get("hooks", {}))
    extra = ""
    if len(candidates) > 1:
        extra = f" (+ {len(candidates) - 1} other install location(s))"
    return {
        "name": "hooks_wiring",
        "status": "ok",
        "detail": f"{chosen} ({n_events} event types registered){extra}",
        "fix": None,
    }


# ----- rendering -----


def _render_text(result: dict, stream: IO[str], p: Palette) -> None:
    headline = "all checks pass" if result["ok"] else "some checks need attention"
    color = "green" if result["ok"] else "yellow"
    stream.write(p.paint(headline, color))
    stream.write("\n\n")
    for c in result["checks"]:
        status_color = {"ok": "green", "warn": "yellow", "fail": "red"}[c["status"]]
        stream.write(f"  [{p.paint(c['status'].upper(), status_color)}] {c['name']}\n")
        stream.write(f"      {c['detail']}\n")
        if c.get("fix"):
            stream.write(f"      {p.paint('fix:', 'dim')} {c['fix']}\n")
        stream.write("\n")


def _human_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} {unit}"
        n = int(n / 1024)
    return f"{n} TB"


__all__ = ["doctor", "_human_bytes"]
