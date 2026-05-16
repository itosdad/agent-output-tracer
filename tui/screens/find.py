"""Find screen — anomaly vocabulary picker.

Lists the 10 detectors from `query.find.VOCAB` with one-line
descriptions. Enter on a row runs that vocab against the latest
captured session and drills into FindResultsScreen.

Phase 2.C only honours the default threshold per vocab — overriding
the threshold (e.g. `repeated-reads 5`) is a Phase 2.G command-palette
concern (`:find repeated-reads 5`).
"""

from __future__ import annotations

from rich.text import Text
from textual.binding import Binding
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from query.find import VOCAB
from tui.config import get_history, set_history
from tui.router import AOTScreen

VOCAB_DESCRIPTIONS: dict[str, str] = {
    "hallucinations": "agent named a path with no in-session source",
    "unmentioned-reads": "Read'd a file the user never named",
    "repeated-reads": "same path read ≥ N times (default N=3)",
    "glob-burst": "K consecutive Reads after a Glob (K=2)",
    "routing-thrash": "CLAUDE.md / AGENTS.md re-read (≥ M=2)",
    "large-read": "single Read ≥ N KB (default 50)",
    "empty-glob": "0 results but agent claimed it found something",
    "stale-cache": "same path re-read with identical SHA256",
    "silent-failure": "tool errored but agent didn't mention it",
    "abandoned-write": "Write then Write again with no Read in between",
}


class FindScreen(AOTScreen):
    TITLE = "find"

    BINDINGS = [
        Binding("enter", "run", "run", show=False),
    ]

    def __init__(self, session_id: str = "latest", *, data_dir=None) -> None:
        self.session_id = session_id
        self._data_dir = data_dir
        super().__init__()

    def breadcrumb_segments(self) -> list[str]:
        return ["agent-output-tracer", "find"]

    def footer_hints(self) -> list[tuple[str, str]]:
        return [
            ("↑↓", "select"),
            ("g/G", "top/bot"),
            ("enter", "run on latest"),
            ("esc", "back"),
        ]

    def help_entries(self) -> list[tuple[str, str]]:
        return [
            ("↑↓", "select vocab"),
            ("enter", "run on latest session  (palette overrides defaults)"),
            ("g / G", "first / last vocab"),
        ]

    def compose_body(self):
        ol = OptionList(id="find-vocab-list")
        yield ol

    def on_mount(self) -> None:
        ol = self.query_one(OptionList)
        for vocab in VOCAB:
            desc = VOCAB_DESCRIPTIONS.get(vocab, "")
            text = Text()
            text.append(f"{vocab:<20}", style="bold")
            text.append(f"  {desc}", style="dim")
            ol.add_option(Option(text, id=vocab))
        # Pre-highlight the vocab the user picked last time, if any.
        last = get_history("find_vocab")
        ol.highlighted = VOCAB.index(last) if last in VOCAB else 0
        ol.focus()

    def action_run(self) -> None:
        ol = self.query_one(OptionList)
        idx = ol.highlighted
        if idx is None:
            return
        try:
            opt = ol.get_option_at_index(idx)
        except Exception:
            return
        self._run_vocab(opt.id or "")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._run_vocab(event.option.id or "")

    def _run_vocab(self, vocab: str) -> None:
        if not vocab:
            return
        set_history("find_vocab", vocab)
        from tui.screens.find_results import FindResultsScreen

        self.app.push_screen(
            FindResultsScreen(
                vocab=vocab,
                session_id=self.session_id,
                data_dir=self._data_dir,
            )
        )
