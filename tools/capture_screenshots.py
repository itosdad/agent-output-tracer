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
    """Append a tiny but representative session into data_dir."""
    from core.recorder import append_event

    sid = "demo-session-01"
    base = {
        "v": 1,
        "engine": "claude-code",
        "session_id": sid,
        "cwd": "/Users/you/work/example",
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
    # 1) user_prompt
    append_event(
        {
            **base,
            "event_type": "user_prompt",
            "ts": "2026-05-16T19:42:01.000+00:00",
            "user_prompt_text": "describe Phase D — the plan and the layout we want",
        },
        data_dir=data_dir,
    )
    # 2) pre_tool Read
    append_event(
        {
            **base,
            "event_type": "pre_tool",
            "ts": "2026-05-16T19:42:03.000+00:00",
            "tool_name": "Read",
            "tool_input": {"file_path": "/Users/you/work/example/DESIGN.md"},
            "paths": ["/Users/you/work/example/DESIGN.md"],
        },
        data_dir=data_dir,
    )
    # 3) post_tool Read
    append_event(
        {
            **base,
            "event_type": "post_tool",
            "ts": "2026-05-16T19:42:03.500+00:00",
            "tool_name": "Read",
            "tool_input": {"file_path": "/Users/you/work/example/DESIGN.md"},
            "tool_response": "# DESIGN\n\n## §4 layout — Phase D…",
            "paths": ["/Users/you/work/example/DESIGN.md"],
            "result_bytes": 47104,
        },
        data_dir=data_dir,
    )
    # 4) pre_tool Bash
    append_event(
        {
            **base,
            "event_type": "pre_tool",
            "ts": "2026-05-16T19:42:08.000+00:00",
            "tool_name": "Bash",
            "tool_input": {"command": "pytest -q tests/unit"},
            "command": "pytest -q tests/unit",
        },
        data_dir=data_dir,
    )
    # 5) post_tool Bash
    append_event(
        {
            **base,
            "event_type": "post_tool",
            "ts": "2026-05-16T19:42:09.200+00:00",
            "tool_name": "Bash",
            "tool_input": {"command": "pytest -q tests/unit"},
            "tool_response": "....\n4 passed in 0.21s",
            "command": "pytest -q tests/unit",
            "result_bytes": 28,
        },
        data_dir=data_dir,
    )
    # 6) agent_response with a path the user never mentioned and no
    # Read produced — guaranteed hallucination hit for Find.
    append_event(
        {
            **base,
            "event_type": "agent_response",
            "ts": "2026-05-16T19:42:12.000+00:00",
            "agent_response_text": (
                "Phase D ships across four sub-phases; the canonical reference is "
                "/Users/you/work/example/DOES_NOT_EXIST.md"
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
    finally:
        shutil.rmtree(data_dir, ignore_errors=True)


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

    written = sorted(args.out.glob("*.svg"))
    for p in written:
        print(p.relative_to(REPO))


if __name__ == "__main__":
    main()
