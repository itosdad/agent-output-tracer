"""Capture SVG screenshots of every key TUI screen for the README.

Runs the TUI under Textual's Pilot test harness against a synthetic
session that's seeded specifically to make each screenshot visually
informative — a couple of user prompts, a Read + Bash with real
content, an agent response, and at least one detector-friendly
hallucination so the Find / Stats screens have something to show.

Usage:

    python tools/capture_screenshots.py [--out docs/img]

The script is idempotent — running it twice produces byte-identical
SVGs (Pilot snapshots are deterministic given the same seeded data).
Re-run whenever the TUI layout changes.
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


# Half-desktop viewport that the design targets. Picked tall enough to
# fit the Home banner + function picker + preview pane comfortably.
VIEWPORT = (96, 32)


def _seed_data(data_dir: Path) -> str:
    """Append a tiny but representative synthetic session into data_dir.

    Generic English content — a developer asking an AI agent to
    investigate an auth handler. The agent reads one real file, runs
    the test suite, then emits a response that names a second file
    (`legacy_handler.py`) which it never actually fetched. That last
    sentence is the textbook hallucination the Find detector is
    designed to surface, and gives every screenshot something real
    to display.
    """
    from core.recorder import append_event

    sid = "demo-session-01"
    base = {
        "v": 1,
        "engine": "claude-code",
        "session_id": sid,
        "cwd": "/Users/dev/work/api-service",
        "tool_name": None,
        "tool_input": None,
        "tool_response": None,
        "agent_response_text": None,
        "user_prompt_text": None,
        "stop_reason": None,
        "paths": [],
        "command": None,
        "result_bytes": 0,
        "raw_event": {},
    }
    # 1) user_prompt — typical investigation request
    append_event(
        {
            **base,
            "event_type": "user_prompt",
            "ts": "2026-05-16T10:14:01.000+00:00",
            "user_prompt_text": "What changed in the auth handler last week?",
        },
        data_dir=data_dir,
    )
    # 2) pre_tool Read — real file the agent does fetch
    append_event(
        {
            **base,
            "event_type": "pre_tool",
            "ts": "2026-05-16T10:14:03.000+00:00",
            "tool_name": "Read",
            "tool_input": {"file_path": "/Users/dev/work/api-service/auth/handler.py"},
            "paths": ["/Users/dev/work/api-service/auth/handler.py"],
        },
        data_dir=data_dir,
    )
    # 3) post_tool Read
    append_event(
        {
            **base,
            "event_type": "post_tool",
            "ts": "2026-05-16T10:14:03.500+00:00",
            "tool_name": "Read",
            "tool_input": {"file_path": "/Users/dev/work/api-service/auth/handler.py"},
            "tool_response": (
                "def authenticate(req):\n"
                "    token = req.headers.get('Authorization')\n"
                "    return verify_jwt(token)\n"
            ),
            "paths": ["/Users/dev/work/api-service/auth/handler.py"],
            "result_bytes": 2147,
        },
        data_dir=data_dir,
    )
    # 4) pre_tool Bash — running the test suite
    append_event(
        {
            **base,
            "event_type": "pre_tool",
            "ts": "2026-05-16T10:14:08.000+00:00",
            "tool_name": "Bash",
            "tool_input": {"command": "pytest tests/auth/ -v"},
            "command": "pytest tests/auth/ -v",
        },
        data_dir=data_dir,
    )
    # 5) post_tool Bash
    append_event(
        {
            **base,
            "event_type": "post_tool",
            "ts": "2026-05-16T10:14:09.200+00:00",
            "tool_name": "Bash",
            "tool_input": {"command": "pytest tests/auth/ -v"},
            "tool_response": (
                "tests/auth/test_handler.py::test_valid_token PASSED\n"
                "tests/auth/test_handler.py::test_expired_token PASSED\n\n"
                "2 passed in 0.43s"
            ),
            "command": "pytest tests/auth/ -v",
            "result_bytes": 124,
        },
        data_dir=data_dir,
    )
    # 6) agent_response — names a file (`legacy_handler.py`) that no
    #    Read fetched and the user never mentioned. Guaranteed
    #    hallucinations hit for Find.
    append_event(
        {
            **base,
            "event_type": "agent_response",
            "ts": "2026-05-16T10:14:12.000+00:00",
            "agent_response_text": (
                "The auth handler now uses JWT validation. The previous "
                "implementation is preserved at "
                "/Users/dev/work/api-service/auth/legacy_handler.py "
                "for reference."
            ),
        },
        data_dir=data_dir,
    )
    return sid


async def _capture(out_dir: Path, theme: str, suffix: str) -> None:
    """Run the Pilot, walk through every screen, save SVG per stop."""
    from tui.app import AOTApp

    data_dir = Path(tempfile.mkdtemp(prefix=f"aot-shot-{suffix}-"))
    try:
        _seed_data(data_dir)
        app = AOTApp(None, data_dir=data_dir)
        async with app.run_test(size=VIEWPORT) as pilot:
            await pilot.pause()
            # Force the requested theme so we get one shot per palette.
            app.theme = theme
            app.user_theme_override = True
            await pilot.pause()

            # Home
            app.save_screenshot(str(out_dir / f"home-{suffix}.svg"))

            # Home → Sessions (with preview pane populated by the
            # auto-highlight of the seeded session)
            await pilot.press("enter")
            await pilot.pause()
            app.save_screenshot(str(out_dir / f"sessions-{suffix}.svg"))

            # Sessions → Timeline
            await pilot.press("enter")
            await pilot.pause()
            app.save_screenshot(str(out_dir / f"timeline-{suffix}.svg"))

            # Timeline → Event detail (the agent_response with the
            # hallucination, last row in our seeded data)
            from textual.widgets import OptionList

            ol = app.screen.query_one(OptionList)
            ol.highlighted = ol.option_count - 1
            await pilot.press("enter")
            await pilot.pause()
            app.save_screenshot(str(out_dir / f"event-detail-{suffix}.svg"))

            # Back out: event → timeline → sessions → home
            for _ in range(3):
                await pilot.press("escape")
                await pilot.pause()

            # Drill into Find via the function picker (index 1)
            ol = app.screen.query_one(OptionList)
            ol.highlighted = 1
            await pilot.press("enter")
            await pilot.pause()
            app.save_screenshot(str(out_dir / f"find-{suffix}.svg"))

            # Pick 'hallucinations' (the most marketing-friendly result)
            ol = app.screen.query_one(OptionList)
            for i in range(ol.option_count):
                if ol.get_option_at_index(i).id == "hallucinations":
                    ol.highlighted = i
                    break
            await pilot.press("enter")
            await pilot.pause()
            app.save_screenshot(str(out_dir / f"find-results-{suffix}.svg"))

            # Back to Home and then drill into Doctor
            for _ in range(2):
                await pilot.press("escape")
                await pilot.pause()
            ol = app.screen.query_one(OptionList)
            ol.highlighted = 5  # doctor
            await pilot.press("enter")
            await pilot.pause()
            app.save_screenshot(str(out_dir / f"doctor-{suffix}.svg"))

            # Doctor → back → Stats (4)
            await pilot.press("escape")
            await pilot.pause()
            ol = app.screen.query_one(OptionList)
            ol.highlighted = 4
            await pilot.press("enter")
            await pilot.pause()
            app.save_screenshot(str(out_dir / f"stats-{suffix}.svg"))

            # Stats → back → Theme (6)
            await pilot.press("escape")
            await pilot.pause()
            ol = app.screen.query_one(OptionList)
            ol.highlighted = 6
            await pilot.press("enter")
            await pilot.pause()
            app.save_screenshot(str(out_dir / f"theme-{suffix}.svg"))

            # Theme → back → Config (7)
            await pilot.press("escape")
            await pilot.pause()
            ol = app.screen.query_one(OptionList)
            ol.highlighted = 7
            await pilot.press("enter")
            await pilot.pause()
            app.save_screenshot(str(out_dir / f"config-{suffix}.svg"))
    finally:
        shutil.rmtree(data_dir, ignore_errors=True)


def _redact_real_paths(svg_dir: Path) -> int:
    """Substitute the capturing user's real machine paths with the
    synthetic ones used elsewhere in the seed data.

    Doctor reads `hooks.json` from the live install location and Config
    reads `~/.config/aot/config.toml` — both call into the runtime
    environment and bypass the synthetic seed in `_seed_data`. Rather
    than thread a demo flag through every command, we strip the leak
    here as a final post-process step. Returns the number of files
    modified.
    """
    home = str(Path.home())  # e.g. /Users/work
    cwd = str(REPO)  # e.g. /Users/work/work/agent-output-tracer
    # Order matters: replace the longer, repo-specific prefix first so
    # the home-replacement doesn't truncate it mid-string.
    substitutions = [
        (cwd, "/Users/dev/work/agent-output-tracer"),
        (home, "/Users/dev"),
    ]
    changed = 0
    for svg in svg_dir.glob("*.svg"):
        text = svg.read_text()
        new = text
        for needle, replacement in substitutions:
            new = new.replace(needle, replacement)
        if new != text:
            svg.write_text(new)
            changed += 1
    return changed


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--out",
        type=Path,
        default=REPO / "docs" / "img",
        help="output directory for SVG screenshots",
    )
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    asyncio.run(_capture(args.out, theme="aot-codex", suffix="codex"))
    asyncio.run(_capture(args.out, theme="aot-claude", suffix="claude"))

    redacted = _redact_real_paths(args.out)
    if redacted:
        print(f"# redacted real paths in {redacted} svg(s)")

    written = sorted(args.out.glob("*.svg"))
    for p in written:
        print(p.relative_to(REPO))


if __name__ == "__main__":
    main()
