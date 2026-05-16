# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.16.4] — 2026-05-16 — Plugin manifest version sync (cache-invalidation release)

### Fixed

- **Plugin marketplace cache was frozen at v0.6.0**, so every Claude
  Code / Codex install was running the pre-v0.16.1 hook code despite
  `aot` (the CLI/TUI side) tracking with `pyproject.toml`. Symptom: all
  Claude Code sessions captured by the installed plugin were tagged
  `engine: codex` because the old `_detect_engine` keyed on
  `permission_mode`, which Claude Code adopted after the heuristic was
  written. v0.16.1 fixed the detector in the repo (`hooks/_runner.py`
  now keys on `hook_event_name` casing) but the cache never picked it
  up — Claude Code's plugin manager keys cache entries on the
  `version` field of `plugin.json`, and that field had not moved since
  v0.6.0 (release commit `571e34e`).

  Bumped `.claude-plugin/plugin.json` and `.codex-plugin/plugin.json`
  from `0.6.0` → `0.16.4` (aligned with `pyproject.toml`) so a single
  semver line drives both the CLI release and the plugin cache key
  going forward. After updating the marketplace and reinstalling,
  newly captured sessions will be correctly tagged.

  Old sessions still carry `engine: codex` in their `metadata.json`;
  the Timeline screen already reads engine from the event stream
  (v0.16.2 fix) so they display under the right theme regardless.

### Docs / chores

- README now covers Stats / Theme / Config screens (screenshots added).
- All Japanese-language documentation translated to English to make
  the project fully accessible internationally: `docs/DESIGN.md`,
  `docs/DESIGN_FORENSIC_UX.md`, `docs/OBSERVATIONS.md`. Three
  intentionally-Japanese test fixtures in `core/references.py` and
  `tests/unit/test_references.py` / `test_recorder.py` are
  preserved — they exist specifically to verify non-ASCII handling
  in the path extractor and recorder, so translating them would
  defeat the test.
- Screenshot capture tool now post-processes `Path.home()` and
  `REPO` paths into synthetic `/Users/dev/...` values so the
  Doctor and Config screen SVGs don't expose the contributor's
  real machine path. Re-captured the four affected SVGs.
- Test fixtures `tests/unit/test_normalizer.py` and
  `test_codex_adapter.py` swapped `/Users/work/proj` →
  `/Users/dev/proj` for consistency with the rest of the
  synthetic seed data.
- Status table phase note for TUI 4.A extended to mention the
  responsive vertical-centring fix shipped in v0.16.3.

## [0.16.3] — 2026-05-16 — Responsive vertical centering for short-content screens

### Fixed

- **Body content on short-content screens (Home / Sessions / Stats /
  Doctor / Theme / Config / Trace / Search / Find / TraceResults /
  FindResults / SearchResults / EventDetail) was not properly
  positioned — content rendered at unpredictable y-offsets, often
  with 15+ rows of dead space above it.** Two independent root
  causes:

  1. **`base.tcss` was overriding per-screen `align` directives.**
     Textual's CSS cascade loads `DEFAULT_CSS` first, then `CSS_PATH`
     (`base.tcss`). At equal specificity, the later rule wins — so
     `AOTScreen > .body { align: left top; }` in `base.tcss` was
     beating every subclass's `DEFAULT_CSS` override. Removed the
     blanket `align` from `base.tcss`; each screen now declares its
     own positioning in `DEFAULT_CSS`.

  2. **`with Vertical():` inside `compose_body()` mounted the
     Vertical as a sibling of `.body`, not as its child.** Textual's
     `with` form relies on the compose-time widget stack, which is
     only active inside `compose()` itself — not in helper methods
     like `compose_body()`. Switched to explicit `Vertical(...,
     id="wrap")` construction in `home.py`, `sessions.py`,
     `trace.py`, `search.py` so the wrap mounts as a real child of
     `.body`.

  Net effect: short-content screens now centre vertically inside
  the viewport (`align: center middle`) while filling screens
  (Timeline, EventDetail, FindResults, SearchResults) still expand
  to use available space via `height: auto`.

### Changed

- **Responsive max-width caps on every screen's content wrap.**
  - Home, Sessions, Timeline, EventDetail, FindResults,
    SearchResults: `max-width: 100–120` (data-dense)
  - Stats, Doctor, Find, TraceResults: `max-width: 72–96` (medium)
  - Trace, Search, Theme, Config: `max-width: 72–80` (compact)

  Content stays readable on wide terminals (no full-width sprawl)
  and still flows correctly on the half-desktop 72×24 target.

### Screenshots

- Regenerated all 14 screenshot pairs (Claude + Codex × 7 screens)
  to reflect the new centred layout. Verified content y-offsets:
  - Theme / FindResults (very short): y=386–410 — centred
  - Doctor / EventDetail (medium): y=215–532
  - Timeline / Stats (longer): y=264–532 / y=118–654
- Added Stats / Theme / Config screenshot pairs (previously
  missing).

## [0.16.2] — 2026-05-16 — Theme robustness + top alignment + per-engine semantic colours

### Fixed

- **Timeline forced the wrong theme on sessions captured before
  v0.16.1.** Those sessions have `metadata.engine = "codex"`
  burned in (the recorder writes engine once from the first event
  and never updates it; pre-v0.16.1 the first event was always
  misdetected as Codex). Timeline read that stale field and kept
  flipping the theme to Codex on every reload, even when the
  actual events are clearly Claude Code.

  Root-cause fix: `_sync_theme_to_engine` now reads engine from the
  *event stream*, not from metadata. A new `_majority_engine()`
  helper returns the most common engine across the loaded events,
  with ties broken deterministically toward the first-seen.
  Metadata is no longer touched for theming.

- **Body content rendered in the vertical middle of the viewport
  on short-content screens** (Stats / Doctor / Theme / Config /
  Trace / Search). Added explicit `align: left top` /
  `content-align: left top` to `AOTScreen > .body` and any
  `Vertical` nested in it. Long screens (Timeline) already filled
  the viewport so were unaffected.

### Changed

- **Semantic colours (success / warning / error) now follow the
  active theme.** Previously hardcoded Rich names (`"red"`,
  `"green"`, `"bold yellow"`) ignored the engine palette, so the
  same error message rendered identically on both themes. Now
  every coloured glyph reads from `app.current_theme.{success,
  warning, error}`:
  - Doctor `✓ / ⚠ / ✗` status icons + headline
  - StatusBar live-follow shimmer
  - Find / Search match bullets
  - Trace results "✓ mentioned / ✗ not mentioned",
    "⚠ hallucination candidate"
  - Stats / Find / Search / Trace error messages
  - Sessions preview anomaly counters

  Codex shows bright terminal-style green / amber / red. Claude
  shows muted warm green / tan / red that harmonises with the
  salmon accent. New shared helpers in `tui._accent`:
  `success()`, `warning()`, `error()`, `severity(name)`.

### Tests

- 2 new tests:
  - Timeline mounted on a session whose metadata.engine is stale
    (`codex`) but whose events say `claude-code` lands on the
    Claude theme.
  - `_majority_engine()` returns the most-frequent engine, ties
    break to first-seen, empty input returns None.

## [0.16.1] — 2026-05-16 — Engine detector + Timeline follow UX fixes

### Fixed

- **Every Claude Code event was being tagged `engine: codex`.** The
  hook engine detector keyed off `permission_mode`'s presence,
  which used to be a Codex-only field. Claude Code has since
  adopted the same field on every event, so the detector silently
  routed every Claude payload through the Codex adapter. Side
  effects: wrong `engine` in metadata + every event, wrong theme
  auto-detect, miscounted tool-mix per engine. The casing of
  `hook_event_name` is the actually-reliable signal — Claude Code
  uses CamelCase (`Stop`, `PreToolUse`), Codex uses snake_case
  (`stop`, `pre_tool_use`). The detector now keys off that
  instead, with `permission_mode` retained only as a tail
  fallback.

  This is why `agent_response_text` *looked* fine on the surface
  (both adapters happen to read `last_assistant_message` for the
  Stop event) but the engine field on every recorded event was
  wrong, breaking every downstream consumer that branches on
  engine.

- **Timeline follow snapped the cursor back to the top on every
  refresh.** `_reload()` unconditionally set `highlighted = 0`
  after rebuilding the OptionList. In follow mode that fought the
  poll: every new event reset the cursor away from the bottom.
  New behaviour:
  - follow mode → cursor snaps to the *newest* row after each
    reload (tail -f)
  - manual mode → cursor stays on the same event id if it's still
    in view, or falls back to the same row index, instead of
    jumping to 0

- **Follow polling was sluggish.** `poll_interval=0.5` left visible
  lag between the recorder writing an event and it appearing on
  screen. Dropped to `0.2s` — well within the floor where the
  `stat()` cost noticeably outpaces what an operator can use.

### Tests

- New integration test: a CamelCase `Stop` payload carrying
  `permission_mode` (the actual production shape) routes to the
  Claude Code adapter and populates `agent_response_text`.
- New unit tests: Timeline follow mode keeps the cursor on the
  newest row across reloads; manual mode preserves the cursor
  across reloads.

## [0.16.0] — 2026-05-16 — Display name + OhMyZsh-style banner

### Added

- **`tui._banner` module** centralises the application's formal
  identity: `APP_NAME = "agent-output-tracer"`, `TAGLINE`, and a
  `render_banner(app)` helper that returns themed Rich Text.
- **Home banner.** A slant-figlet ASCII rendering of "AOT" sits at
  the top of the Home screen, with the formal product name and
  tagline aligned beside it, and a version + quick-key strip below:

      ___    ____  ______
     /   |  / __ \/_  __/
    / /| | / / / / / /     agent-output-tracer
   / ___ |/ /_/ / / /      forensic debugger for AI agent sessions
  /_/  |_|\____/ /_/

  v0.16.0  ·  ? help  ·  : palette  ·  t cycle theme

  Colours follow the active theme accent — cyan on Codex, salmon on
  Claude. Renders on Home only; deeper screens own their own chrome.

### Changed

- **Display name everywhere is `agent-output-tracer`, not `aot`.**
  Every breadcrumb root, every toast `title=` field, the terminal
  window title (`App.TITLE`), the help overlay heading — all read
  the new constant. The CLI binary stays `aot` (and so does the
  config-file path `~/.config/aot/`); only user-facing display
  changed.

### Tests

- 3 new tests: banner constants expose the full product name, Home
  renders the ASCII banner with the slant-font signature, the App
  window title matches the constant.
- Updated breadcrumb assertions across the smoke tests
  (`["aot", "home"]` → `["agent-output-tracer", "home"]` etc.).

## [0.15.1] — 2026-05-16 — Bare `aot tui` reads the live engine env var

### Changed

- **Launch theme precedence reordered: `--session` → env var →
  newest session → default.** Previously the plugin-host env var
  (`CLAUDE_PLUGIN_DATA` / `CODEX_PLUGIN_DATA`) only kicked in as a
  fallback for "first launch with no data yet" — useless in
  practice because everyone has captures by the time they care.
  The env var is in fact the strongest signal for "which CLI am
  I inside *right now*", stronger than the newest captured
  session, which might be a stale Codex run from earlier in the
  day while the operator has since switched engines. Bare
  `aot tui` (no `--session`) now picks the right theme on first
  launch from inside Claude Code or Codex.

### Tests

- New: env var beats a stale newest-session of the other engine.
- New: bare shell with no env var falls back to newest session.
- Updated: the codex-auto-detect test now sets
  `CODEX_PLUGIN_DATA` explicitly (the `plugin_data_dir` fixture
  defaults to Claude Code's env var).

## [0.15.0] — 2026-05-16 — Phase 4.A: theme override fix, menu preview pane, clipboard yank

Phase 3 is closed (v0.10.0 → v0.14.1). Phase 4 opens with the bug
sweep and UX foundation that turns the TUI from "data dump" into a
discoverable tool.

### Fixed

- **Timeline silently flipped the theme back on every reload.**
  `_sync_theme_to_engine()` re-applied the session's engine theme
  on every `_reload()` (including from `r` refresh, follow events,
  navigation), wiping out any manual choice the user had made via
  `t` or the ThemeScreen. Now the helper consults a new
  `app.user_theme_override` flag set by either explicit-choice
  path and short-circuits when it's True. Auto-detect still runs
  on launch.

- **Launch theme didn't follow the session you're actually
  opening.** `aot tui --session <sid>` always picked the newest
  captured session's engine, so opening an older Claude session
  in a Codex-dominated data_dir landed you on cyan. New precedence:
  explicit `--session` → newest session → env-var hint
  (`CLAUDE_PLUGIN_DATA` / `CODEX_PLUGIN_DATA` for "first launch
  inside that CLI environment") → codex default.

### Added

- **Home preview pane.** Below the function picker, a Static pane
  shows three lines for the highlighted menu item: "What it does",
  "What you'll see", "Example finding". Updates live as the cursor
  steps through. Operators no longer have to drill into every
  function just to find out what's inside.

- **Sessions preview pane.** Same pattern: highlight a session and
  the pane shows engine / span / cwd / event count / prompt mix /
  byte total / top tools / top anomaly counters from `metadata.json`.
  Decide whether to drill in without leaving the list.

- **Clipboard yank (`y`).** Universal `y` binding on AOTScreen
  copies the screen's payload to the system clipboard. Each screen
  decides what "payload" means via a `yank_payload()` hook:
  - EventDetail → the structured event as pretty JSON
  - Stats / Doctor → the rendered body text
  - Timeline / Sessions / Find / Search → the highlighted row's
    plain text (default `_focused_text()` fallback)
  Clipboard wrapper (`tui/_clipboard.py`) shells out to
  `pbcopy` / `xclip` / `xsel` / `wl-copy` / `clip` — no
  third-party dep. Native terminal selection still works via
  Option-drag (iTerm2 / Terminal.app / Kitty); the help overlay
  now documents both paths.

- **Help overlay globals updated.** Adds `y` yank and Opt+drag
  notes to the universal keybind list. Drops the Phase markers
  from `:` and `t` since both are now real.

### Tests

- 4 new Pilot tests:
  - Timeline drill does NOT override a user's manual theme choice
  - `--session <sid>` picks that session's engine theme even when
    the newest captured session is a different engine
  - `EventDetail.yank_payload()` returns valid event JSON
  - Home preview pane updates as the OptionList cursor moves

- 1 unit test: `tui._clipboard.copy("")` returns False, `available()`
  returns bool — no crashes on platforms without a clipboard tool.

### Notes

The Phase 4 plan (4.A done, 4.B-4.D pending):
- 4.B — Diagnostic Brief: one-screen session executive summary
  (verdict, top anomalies, activity profile, hot files / phrases,
  timeline sparkline). The "why use this tool" answer.
- 4.C — Context Reconstruction: for an `agent_response`, surface
  what the agent actually saw (Read history head + tool outputs)
  to investigate hallucinations.
- 4.D — Session Compare + Pattern Detection: diff two sessions;
  detect recurring anomalies across the whole capture.

## [0.14.1] — 2026-05-16 — Unify accent colour under the active theme

### Fixed

- **Theme leaked the codex cyan into the Claude theme.** Six render
  paths hardcoded `cyan` instead of reading the active theme's
  accent, so on the Claude (salmon) theme the chrome was salmon
  but the latest-session marker, the Timeline `pre_tool` prefix,
  the help overlay heading + key column, every modal border, and
  the InlinePrompt label were all still cyan. Engine-wide
  consistency was broken.

  All six are now theme-aware:
  - `tui/themes/codex.tcss` — `Breadcrumb` and
    `InlinePrompt > .prompt-label` now read `$accent` (Textual's
    CSS variable bound to the active Theme's `accent` field).
  - `HelpOverlay`, `ExportModal`, `CommandPalette`, `NoteModal`
    border + title colours → `$accent`.
  - `sessions.py` latest-session `●` marker → reads
    `app.current_theme.accent` at render time.
  - `timeline.py` `pre_tool` event prefix → reads accent
    likewise. Other event prefixes (`post_tool` green,
    `session_*` dim) keep their semantic colours.
  - `help.py` heading + key column → reads accent.

- Extracted a shared `tui._accent.accent(app)` helper. Previously
  `footer.py` and `status_bar.py` each defined their own private
  copy; the new module collapses both call sites onto one
  implementation and is what the new theme-aware render paths
  import from.

### Tests

- 1 new Pilot regression test seeds a claude-code session and
  asserts that the Timeline `pre_tool` prefix and the Help overlay
  body contain the Claude accent hex (`#e08a6a`) and NOT the
  literal `"cyan"` anywhere. Catches future regressions where a
  new render path forgets to thread the accent through.

## [0.14.0] — 2026-05-16 — Home menu: Theme + Config screens

### Fixed

- **Theme and Config rows on Home were dead.** They were marked
  `available=False` (showing `(Phase 2)`) and the router fell
  through to `bell()`. Phase 3.A wired the `t` cycle and Phase 3.B
  wired sticky-defaults persistence, but neither surfaced through
  Home — a user picking either row got nothing. Both rows now
  drill into real screens.

### Added

- **ThemeScreen** (`Home → Theme`). Lists the two engine themes
  (Codex / Claude) with a `●` marker on whichever is currently
  active. Enter applies the highlighted theme and pops back to
  Home with a toast confirmation. The universal `t` cycle binding
  still works in parallel for power users.
- **ConfigScreen** (`Home → Config`). Read-only viewer of the
  sticky-defaults persisted under `~/.config/aot/config.toml`,
  including the file path itself, the known history keys with
  their stored values, and a note that theme is intentionally
  not persisted. `c` clears all sticky defaults via a new
  `tui.config.clear_history()` helper; `r` re-reads from disk.
- **`tui.config.clear_history()`** wipes the `[history]` section
  without going through the merge path. The old
  `save_config({"history": {}})` round-trip hit
  `_deep_merge`, which recurses into nested dicts and preserved
  every existing key — so "clear" was a no-op. The new helper
  pops the section and rewrites the file directly.

### Tests

- 2 new Pilot tests: Home → Theme picker → apply → Home with the
  theme actually changed; Home → Config → `c` actually clears the
  persisted history.

## [0.13.1] — 2026-05-16 — Package `tui.themes` in the wheel

### Fixed

- **`ImportError: cannot import name 'CLAUDE_THEME' from 'tui.themes'`**
  on every pipx-installed build of v0.10.0 through v0.13.0. Phase
  3.A added `tui/themes/__init__.py` (turning the previously
  `.tcss`-only directory into a real Python subpackage) but the
  `[tool.setuptools].packages` list was never updated, so the wheel
  shipped the module's `.tcss` files (via `package-data`) without
  the `__init__.py`. Adding `"tui.themes"` to `packages` makes
  `aot tui` start again on a fresh install.

### Notes

- A development install (`pip install -e .`) didn't hit this because
  editable mode imports from the working tree. The bug only
  surfaced once a wheel was actually built and installed — which is
  exactly the path users take.

## [0.13.0] — 2026-05-16 — Phase 3.D: Visual polish (closes Phase 3)

### Added

- **Shimmer indicator** on the StatusBar `live` segment. While the
  Timeline is in follow mode, the glyph pulses between `●` (bright
  green) and `○` (dim green) every 700ms via a Textual interval
  timer that's paused when follow is off. Calm enough to live in
  peripheral vision, visible enough to confirm the tail is alive.
- **StatusBar wired to the Timeline screen.** The bar was a Phase 1
  stub that never updated — it now reflects the session id,
  engine, event count, and follow state of whatever Timeline is
  currently rendered, via a new `_update_status_bar()` helper
  invoked on every `_reload()` and follow toggle.
- **Actionable empty states** replace the dead-end one-liners:
  - Sessions empty: "(no sessions captured yet)" now points at
    `aot doctor` and the trigger conditions (any tool call under
    Claude Code / Codex with the plugin active).
  - Timeline empty: explains the metadata-but-no-events case and
    points at `aot doctor` for hooks-wiring diagnosis.
  - Find empty: re-frames "no matches" as the healthy outcome and
    suggests `esc` to try a different vocab.
  - Search empty: shows a quick `re` syntax reminder (`|`, `(?i)`,
    `\b`) so the user can iterate on the pattern in place.

### Tests

- 3 new Pilot / unit tests:
  - StatusBar reflects the Timeline's session / engine / event count
  - `o` flips follow on the bar, shimmer ticks alternate the glyph
  - Sessions empty state contains an `aot doctor` hint

## [0.12.0] — 2026-05-16 — Phase 3.C: Session-scoped sub-actions

### Added

- **`S` / `T` / `F` on a Sessions row** open Stats / Timeline / Find
  scoped to the *highlighted* session, not "latest":
  - `S` pushes `StatsScreen(sid)` — useful when you want the metrics
    for a specific session without first drilling into its timeline.
  - `T` pushes `TimelineScreen(sid)` — synonym for Enter, kept for
    mnemonic consistency with `S` and `F`.
  - `F` pushes `FindScreen(sid)` — vocab picker scoped to this
    session, so the eventual `FindResultsScreen` runs `find()` against
    the same session id, not whichever one happens to be newest at
    the time the user picks the vocab.
- Uppercase bindings deliberately avoid colliding with OptionList's
  lowercase first-letter search behaviour.

### Notes

- Existing Enter-on-row → Timeline flow is unchanged.
- `e` (export) was already session-scoped; this round completes the
  set of session-scoped sub-actions.

### Tests

- 3 new Pilot tests cover `S` / `T` / `F` opening the right screen
  with the highlighted session's id (not "latest" / not the first
  row when a different one is highlighted).

## [0.11.0] — 2026-05-16 — Phase 3.B: Sticky defaults

### Added

- **Sticky-default config** at `~/.config/aot/config.toml` (honours
  `$XDG_CONFIG_HOME`, and `$AOT_CONFIG_HOME` as a test escape hatch).
  Read via stdlib `tomllib`, written with a hand-rolled minimal
  encoder so the wheel doesn't pull `tomli_w`.
- **Pre-fill on screen mount** wires four common workflows to the
  config:
  - **Find**: the last vocab the user ran is pre-highlighted in the
    picker, so `Enter` re-runs it.
  - **Trace**: the Input is pre-populated with the last phrase typed.
    The field is focused so a single keystroke replaces it — sticky
    behaves like "remembered", not "stuck".
  - **Search**: the Input is pre-populated with the last regex typed.
  - **Export modal**: the format / safe-share / excerpt knobs open
    on the values used last time. Output path stays per-session
    (with the suffix derived from the saved format).
- **Persist on submit** for each of the four flows. The export
  modal's output path is intentionally NOT persisted — it's
  per-session by design.

### Notes

- Theme preference is intentionally NOT persisted. `t` is a
  per-session override; the next launch re-runs the engine-based
  auto-detect from the newest session. This keeps a simple mental
  model ("the TUI follows my engine, I can flip it temporarily")
  and avoids stale overrides from one-off experiments.
- A corrupted config.toml silently returns `{}` so a malformed file
  cannot crash the TUI on launch.

### Tests

- 7 new Pilot / unit tests in `tests/unit/test_d5_tui.py` covering:
  - `set_history` → `get_history` round-trip
  - Corrupted file returns `{}` (no crash)
  - Trace / Search / Find pre-fill from saved history
  - Running a Find vocab persists the choice
  - ExportModal opens with saved format / safe-share / excerpt

## [0.10.0] — 2026-05-16 — Phase 3.A: Engine-aware theme system

### Added

- **Two custom Textual themes**, registered on app mount:
  - `aot-codex` — cyan accent. Sourced from openai/codex Rust TUI
    (`codex-rs/tui/src/style.rs` uses `Color::Cyan + BOLD` as primary
    accent against the terminal default background).
  - `aot-claude` — salmon/rust accent. β-flavored from Anthropic's
    `#CC785C` brand colour. Claude Code itself ships without a
    documented colour spec, so this is an inspired approximation,
    not a one-for-one clone.
- **Auto-detect on launch.** `AOTApp._initial_theme_name()` reads the
  newest captured session's `engine` field and picks the matching
  theme. A developer who lives in Claude Code opens `aot tui` and
  immediately sees the salmon accent without pressing `t`. Falls
  back to Codex (cyan) for unknown / empty engines or when no
  session has been captured yet — cyan is safer across the variety
  of terminal palettes most people run.
- **`t` cycles themes.** The `t` binding on `AOTScreen` was a
  placeholder in Phase 1; it now toggles between `aot-codex` and
  `aot-claude` via `tui.themes.next_theme()` and emits a 1-second
  toast notification confirming the active theme.
- **Timeline auto-syncs theme to session engine.** When you drill
  into a session's timeline, `_sync_theme_to_engine()` reads the
  session's metadata and switches the active theme to match — so
  jumping between a Claude Code session and a Codex session in the
  same `aot tui` run swaps the accent automatically.
- **Theme-aware chrome.** `StatusBar`, `FooterHints`, and
  `Breadcrumb` widgets now read the accent colour from
  `app.current_theme.accent` at render time instead of using a
  hardcoded "bold cyan" Rich style. Cycling themes immediately
  re-tints the breadcrumb / status engine name / footer keybind
  hints without any manual refresh.

### Tests

- 5 new Pilot tests in `tests/unit/test_d5_tui.py` covering:
  - `theme_for_engine()` and `next_theme()` helper logic
  - Claude-engine session auto-detect to `aot-claude`
  - Codex-engine session auto-detect to `aot-codex`
  - `t` press cycles between the two themes
  - Drilling into a claude-code session swaps to `aot-claude`
    even if the app started on Codex

## [0.9.8] — 2026-05-15 — Phase 2 bug-fix sweep

### Fixed

- **Find / Search results crashed with `DuplicateID`** when a single
  event produced multiple matches (one agent_response can be the
  source of several hallucinations tokens; one event can have the
  search pattern in multiple fields). The OptionList option ids were
  the bare `event_idx`, which collided. Switched to `match-<i>` ids
  and resolved them back to event_idx through the in-memory match list.
- **`?` help binding** is now also reachable via `F1`. Some terminal
  / IME combinations swallow the literal `?` before Textual sees it.
- **Note / Export silent success.** Pressing Enter on the Note modal
  used to dismiss with only a `bell()` — no feedback. Replaced with
  `app.notify()` toasts (`note saved on event N`, `exported → <path>`)
  including an error path that surfaces exceptions instead of
  swallowing them.

## [0.9.7] — 2026-05-15 — Phase 2.H: Live follow (closes Phase 2)

### Added

- **Timeline live follow.** `o` on Timeline now actually tails the
  session's events.jsonl via `core.follower.follow_events` in a daemon
  thread. New events are dispatched to the main loop with
  `app.call_from_thread`, the OptionList refreshes, and the cursor
  snaps to the latest row. Toggling `o` again stops the polling
  thread. Drilling away (push) or quitting (`q`) also stops it via
  `on_unmount` so the file handle never leaks.

This commit closes Phase 2 of the TUI roadmap. All 17 CLI commands
now have a TUI surface (Sessions / Timeline / EventDetail / Find /
Trace / Search / Stats / Doctor / Note / Export / live follow) and
the command palette routes power-user syntax across them.

## [0.9.6] — 2026-05-15 — Phase 2.G: Command palette `:`

### Added

- **Command palette** — `:` from any screen opens a single-line input
  that parses CLI-like syntax and routes to the right destination:

      :sessions
      :stats            (latest)        :stats <sid>
      :doctor
      :find <vocab>     (latest)        :find <vocab> <N>     (threshold)
                                        :find <vocab> --session <sid>
      :trace <phrase>
      :search <regex>
      :home             (pops back to Home)
      :help             (opens help overlay for the screen below)
      :quit

  Tokenisation goes through `shlex.split`, so quoted phrases like
  `:trace "hooks_wiring setup"` are parsed as one argument.
  Process-local history recall on ↑/↓.

  The palette dismisses itself before invoking the dispatched action,
  so the new screen pushes onto the underlying stack rather than on
  top of the modal.

## [0.9.5] — 2026-05-15 — Phase 2.F: Note + Export modals

### Added

- **Note modal** triggered by `n` on Event Detail. Single-line body
  input; tag defaults to `observation` (richer tag selection is a
  palette concern, `:note tag:question body…`). Session id and
  event_idx are pre-filled from the parent screen.
- **Export modal** triggered by `e` on Sessions. Multi-field form:
  format (markdown / json / archive, ←/→ cycle), safe-share (Space
  toggle), excerpt size (←/→ -100/+100), output path. Default path
  is `~/aot-export-<sid8>.md`. Enter exports — the common case stays
  two keystrokes.

## [0.9.4] — 2026-05-15 — Phase 2.E: Search screen

### Added

- **Search screen** (Home → Search) — regex full-text search across
  every string-valued field of every event in the latest session
  (same field set the CLI `aot grep` walks). Input is the focal
  element; ↑/↓ recalls previous queries from a process-local ring.
- **SearchResults screen** renders one match per row (`event_type.
  field` + truncated preview) and drills into Event Detail on Enter.
  Cross-session fan-out is deferred to Phase 2.G (`:search <regex>`
  without a session scope will hit the global index).

## [0.9.3] — 2026-05-15 — Phase 2.D: Trace screen

### Added

- **Trace screen** (Home → Trace) — input-driven phrase tracer. The
  screen places an Input as the focal element, ↑/↓ recall recent
  phrases from a process-local ring buffer (config-persisted recall
  is Phase 3).
- **TraceResults screen** renders the structured `query.trace.trace()`
  output: first-mention event, last user prompt before, every prior
  Read with `✓ contains` / `✗ does not contain`, and a `⚠
  hallucination candidate` banner when nothing grounded the phrase.
  Enter opens the source event's Event Detail.

## [0.9.2] — 2026-05-15 — Phase 2.C: Find screen

### Added

- **Find screen** (Home → Find) — anomaly vocabulary picker. Lists
  all 10 detectors with one-line descriptions, Enter runs on the
  latest session with default thresholds, drills into:
- **FindResults screen** — the match list, each match a 2-line card
  with the source event ts + key/value details (path, token, count,
  size, etc. — whatever the vocab populated). Enter on a match drills
  into the source event's Event Detail.

Threshold overrides (e.g. `repeated-reads 5`) and explicit session
selection are deferred to Phase 2.G's command palette so the picker
itself stays one Enter away from results for the common case.

## [0.9.1] — 2026-05-15 — Phase 2.B: Stats + Doctor screens

### Added

- **Stats screen** (Home → Stats). Wraps `query.stats.stats()` and
  renders a single read-only card: session id, engine, period, event
  counts, tool mix (top 6 by call count), files touched, anomaly
  counters, token totals. Defaults to `latest` session; switching to
  a different session is deferred to the command palette (Phase 2.G)
  and the `S` shortcut on Sessions rows (Phase 2.E).
- **Doctor screen** (Home → Doctor). Wraps `query.doctor.doctor()`
  with `✓ ⚠ ✗` glyphs per check and an inline `fix:` hint when one
  is provided. `r` re-runs all checks. Same backend as the CLI
  `aot doctor` — single source of truth.

### Changed

- Home menu: Stats and Doctor entries are no longer marked
  `(Phase 2)`. The remaining four (Find / Trace / Search / Theme /
  Config) still are.

## [0.9.0] — 2026-05-15 — Phase 2.A: help overlay

### Added

- **`?` help overlay** on every screen. A centered modal at 56-col
  width (so it fits half-desktop layouts at 72 cols viewport) shows
  the current screen's keybinds plus the universal global keybinds
  (`esc`, `g/G`, `Home/End`, `:`, `?`, `t`, `q`). Any keystroke
  dismisses — no need to memorise which key closes it.
- `AOTScreen.help_entries()` hook so each screen can advertise more
  detail in `?` than fits in the cramped footer. Sessions / Timeline /
  Event Detail use this to expose bindings like `r refresh`, `/`
  search, `y` yank, `n` note that the footer hides.

## [0.8.1] — 2026-05-15

### Added

- **vim-style top/bottom jump on every list and scroll view.**
  `g` / `Home` → first row, `G` / `End` → last row. Universal — wired
  on the `AOTScreen` base class so every screen inherits it. The
  handler dispatches on the focused widget type so OptionLists,
  DataTables, and ScrollableContainers all respond correctly. Footer
  hints on Home / Sessions / Timeline / EventDetail now advertise
  `g/G top/bot` so the binding is discoverable.

## [0.8.0] — 2026-05-15

Half-desktop UI/UX optimisation: the TUI now fits a 72-column viewport
without horizontal scroll, matching the typical "split the desktop,
Claude Code on one half, tracer on the other" workflow.

### Changed

- **Sessions and Timeline screens switched from DataTable to
  OptionList.** Columns are gone. Each session and each event renders
  as a 2-line vertical card with Codex-style semantic prefixes
  (`›` / `⏵` / `✓` / `•` / `─`), reading top-to-bottom. The new layout
  is width-adaptive: long bodies wrap rather than being chopped by a
  fixed column. This mirrors how Codex CLI itself renders history
  cells (`tui/src/history_cell/messages.rs` cited in our theme tokens).

  Side benefit: drill-in is now handled by OptionList's first-class
  `OptionSelected` event instead of the DataTable-RowSelected workaround.

- **Paths in event cards now show only the last two components**
  (`.../parent/file.md`) rather than the full absolute path. The Event
  Detail screen still shows the full path — the truncation is purely
  for the list view.

- **Event Detail footer hint condensed** to fit a 72-col row in one
  line: `↑↓ step  r raw  s safe  enter related  esc back`. `y` yank
  and `n` note are still bound, just no longer advertised in the
  cramped footer.

- **FooterHints** gets `overflow-x: hidden` so a too-long hint row
  truncates rather than wrapping a 1-row widget into something that
  looks broken.

### Fixed

- **OptionList that's populated via `add_option()` (rather than init)
  no longer leaves `highlighted=None`.** Sessions and Timeline now
  explicitly set `highlighted = 0` after populating, so Enter on first
  focus actually drills in.

### Added

- `test_no_horizontal_overflow_at_half_desktop_width` — Pilot test
  that runs the app at `size=(72, 24)`, drills Home → Sessions →
  Timeline → Event Detail with a synthetic long-body event, and
  asserts no OptionList shows a horizontal scrollbar at any step.

## [0.7.2] — 2026-05-15

### Fixed

- **Esc on the Home screen froze the TUI.** Textual's default empty
  Screen sits at stack index 0; HomeScreen was at index 1. Pressing
  Esc on Home unconditionally called `app.pop_screen()`, exposing
  that empty default Screen with no widgets, no bindings, no
  breadcrumb — the TUI looked alive but rejected every keystroke
  (the user could only kill it from outside).
  Fixed by introducing `AOTScreen.IS_ROOT` and a guarded
  `action_safe_back` that no-ops with a bell when called on a root
  screen. `HomeScreen` sets `IS_ROOT = True`. Regression test pins it.

## [0.7.1] — 2026-05-15

Two Phase 1 TUI bugs that shipped in v0.7.0:

### Fixed

- **Enter on a DataTable row didn't drill in.** Both `SessionsScreen`
  and `TimelineScreen` relied on a screen-level `Binding("enter", …)`,
  but Textual's `DataTable` with `cursor_type="row"` consumes Enter
  via its own `select_cursor` action which emits a `RowSelected`
  message. The screen's binding never fired, so users were stuck on
  Sessions and Timeline with no way to drill in to a session or event.
  Fixed by listening for `DataTable.RowSelected` instead. Two
  regression tests pin the contract.
- **EventDetailScreen crashed the compositor.** `_render` is a
  Textual `Widget` internal method (`widget.py:1900` calls
  `visual = self._render()`). The screen accidentally overrode it
  with a `None`-returning method, so as soon as the screen took the
  viewport the renderer raised `'NoneType' object has no attribute
  'render_strips'`. Renamed our method to `_refresh_view` and noted
  the trap in the source.

## [0.7.0] — 2026-05-15

TUI redesign Phase 1 and the hallucination detector overhaul. 461
tests pass on Python 3.13; the textual-missing CLI test skips when
textual is installed in dev.

### Added

- **TUI screen-based navigation.** The TUI is being repositioned from
  a 2-pane session browser into the tracer's primary console. Phase 1
  ships a screen router with universal Esc-to-go-back, a Home menu
  listing every top-level operation, and dedicated Sessions / Timeline
  / Event Detail screens. Enter drills in; Esc pops back; `q` quits;
  `?` `:` `t` are reserved for help / command palette / theme toggle
  (Phase 2+).
- **Codex theme tokens.** Source-cited from openai/codex Rust workspace
  (`codex-rs/tui/`): cyan accent, borderless prose, `›` user prefix,
  `  └ ` tool detail, `  │ ` quote gutter, `•` semantic bullets. Every
  value documented with a file:line evidence pointer.
- **Semantic event prefixes** on the Timeline screen: `›` user_prompt,
  `⏵` pre_tool, `✓` post_tool, `•` agent_response, `─` session
  markers.
- **Input widget skeletons** for Phase 2 command wiring: `InlinePrompt`
  (lazygit-style bottom row with ↑/↓ history recall) and `ModalForm`
  (text / bool / enum / number fields, full keyboard navigation).

### Fixed

- **Hallucination detectors — four real bugs.** `_hallucinations`,
  `_unmentioned_reads`, and `mentioned_but_not_read` previously
  treated the entire session as one bag of text, which let a user
  prompt that arrived AFTER an agent response retroactively "ground"
  the agent's claim. Time-causality is now respected. When the operator
  pastes a prior `aot find` output into the next prompt, the detector
  now recognises the CLI output fingerprint and excises it before
  treating the prompt as a grounding source — the detector no longer
  silently consumes its own warnings. The token extractor restricts
  path content to ASCII (so non-ASCII prose like CJK / Cyrillic / Arabic
  no longer matches as a path) and preserves URL schemes
  (`https://github.com/...` survives intact instead of degenerating
  to `//github.com/...`). 27 new unit tests pin these behaviours.
- **`aot doctor`** now probes Claude Code marketplace clones
  (`~/.claude/plugins/marketplaces/*/hooks/hooks.json`) and the Codex
  plugin cache, so pipx-installed CLIs no longer report a spurious
  "hooks.json not found" failure.
- **`resolve_data_dir`** scans `~/.claude/plugins/data/agent-output-tracer*`
  to find the actual Claude Code data directory (which is named
  `<plugin>-<marketplace>` on disk, not the bare plugin name).

### Changed

- `aot tui` (no flag) now lands on the Home screen instead of
  deep-linking to "latest". `aot tui --session <id>` still drills
  directly into a timeline, with Home + Sessions pre-pushed on the
  stack so Esc/Esc walks back to Home.
- Package layout: `tui.screens` and `tui.widgets` are explicit
  subpackages; `tui/themes/*.tcss` ships as package data.

## [0.6.0] — 2026-05-15

Phase D-2 through D-7 — schema v2, causal core, live UX, side-channel
TUI, bridges, safe-share export. 417 tests pass on Python 3.13; the
single skip is the textual-app constructor test which runs only when
the `[tui]` optional dependency is installed.

### Added

- **D-2 Schema v2** — additive schema bump across events.jsonl /
  metadata.json / index.json. Events now carry `v`, `response_sha256`
  + `response_size_bytes` (post_tool), `correlation_id` (recorder-minted
  per turn; reuses Codex `turn_id` when present), `tool_use_id`,
  `parent_session_id`, `tokens`, `duration_ms`, `engine_version`,
  `permission_mode`, `hook_self_ms`. metadata.json migrates v1→v2 in
  place on first append and grows `notes_count` / `findings` /
  `anomaly_counters` / `tokens_total` / `cwd_hash`. New `core/indexer.py`
  builds per-session search indexes (bigram_inverted,
  content_hash_to_events, path_first_seen, phrase_to_first_agent_event)
  lazily on demand.
- **D-3 Causal Core** — 5 new query verbs:
  - `aot find VOCAB` over 10 anomaly vocab terms (unmentioned-reads /
    repeated-reads / glob-burst / routing-thrash / large-read /
    hallucinations / empty-glob / stale-cache / silent-failure /
    abandoned-write). `denied-permission` deferred to engine-log
    overlay.
  - `aot trace --missing PHRASE [--reference-paths ...]` — inverse
    hallucination: phrase in a tool_response but absent from every
    downstream agent_response.
  - `aot trace --by-sha SHA256_HEX` — content-address lookup over the
    v2 `response_sha256` field.
  - `aot bisect start|good|bad|skip|view|status|log|quit` — git-bisect
    flavoured binary search; first-bad finding appended to
    `metadata.findings` (append-only).
  - `aot note add|list|rm` — human-attached notes at
    `<session>/notes.jsonl` with standard tag vocabulary
    (root-cause / observation / question / false-positive / followup /
    `custom:<...>`).
  - `aot stats` — session-level forensic counters (NOT cost) with
    `--format json` for CI.
- **D-4 Live UX** — `core/follower.py` polling tail with shrink-detection
  fallback; new `aot tail [--format text|stream-json] [--from-start]`
  command; `aot replay --watch` continues into live tail after the
  initial replay.
- **D-5 Side-channel TUI** — `aot tui` launches a textual-based
  side-channel UI (DESIGN_FORENSIC_UX §5). Two-pane layout
  (session list + timeline), keybinds for navigation / session switch /
  search filter / live follow / quit. Optional dependency — install
  with `pip install 'agent-output-tracer[tui]'`; without the extra,
  `aot tui` emits the standard 3-line error pointing at the install
  command.
- **D-6 Bridges** — all default-off, opt-in, one-way:
  - `bridges/engine_log.py` — read `~/.claude/debug/<session>.txt`
    (honors `CLAUDE_CODE_DEBUG_LOGS_DIR` env), timestamp-merge with
    AOT events.
  - `bridges/otel_export.py` — build engine-neutral span payload
    (`aot.session` / `aot.turn` / `aot.tool` / `aot.finding` / opt-in
    `aot.user_prompt`); console exporter implemented, others raise
    clear errors. `log_user_prompt` and `log_raw_tool_response` default
    False (DESIGN_FORENSIC_UX §8.3).
  - `core/global_index.py` — `<data_dir>/global_index.json` aggregating
    sessions / paths / SHAs / phrase grams across the retention window
    (default 30 days).
  - `aot review --since DATE [--until DATE]` — user-explicit
    cross-session summary that builds the global index on demand.
- **D-7 Safe-share Export** — `core/sanitiser.py` produces a redacted
  view of a session (cwd → `<repo>`, `$HOME` → `<HOME>`, emails / long
  hex / phone-shaped digit runs masked, tool_response stripped to
  sha+size+excerpt). `aot export --session SPEC --format markdown|json|archive`
  writes the safe payload to stdout or a file; `--format archive`
  produces a zip with `metadata.json` + `events.jsonl` + `REPORT.md`.
- New `[tui]` and `[dev]` optional dependency sets in `pyproject.toml`.
- `bridges/` and `tui/` packages registered for distribution.

### Tests

- D-2: 13 new tests (schema stamping, correlation_id anchoring, v1→v2
  metadata migration, adapter pass-through, indexer build / persist /
  reload).
- D-3: 27 new tests (every find vocab term, both new trace modes,
  bisect convergence, note round-trip, stats output).
- D-4: 6 new tests (follower from-start / tail-only / appended-during-loop /
  shrink-recovery, tail text + stream-json output).
- D-5: 3 tests (`is_available()` agreement, CLI without the extra
  emits the 3-line error, app constructor smoke — last skipped when
  textual isn't installed).
- D-6: 13 new tests (engine_log path resolution / timestamp parse /
  merge ordering, span model PII redaction defaults / opt-in, OTel
  is_available, global_index aggregation, review summary +
  since-filter).
- D-7: 9 new tests (sanitiser PII / cwd / tool_response handling,
  excerpt length, markdown / json / archive output paths, archive
  output-required validation).



Phase D-1 — CLI UX foundation. New `aot` short alias for the binary,
3-line error UX, color/symbol palette honoring `NO_COLOR`, self-
diagnostic `doctor`, and `config get/set/list/unset` for CLI defaults.
347 tests pass on Python 3.13; hook runtime still 3.9-compatible.

### Added

- D-1 / Phase D §9.1 deliverables:
  - `aot` console script alongside the canonical `agent-output-tracer`
    (both point at `cli.main:main`). All existing commands work under
    either name.
  - `--color {auto,always,never}` global flag. `auto` honors `NO_COLOR`
    env and TTY detection. ANSI codes are emitted by a `cli/colors.Palette`
    with the symbol/color table from DESIGN_FORENSIC_UX §4.2 (ASCII only,
    no emoji).
  - 3-line error UX (`cli/errors.format_error_block` / `print_error`):
    `error:` headline → `cause:` data → `try:` next-action commands.
    Wired into every `--session` resolution path; ambiguous prefixes,
    missing sessions, malformed `--time`, bad regex, and unknown config
    keys all surface a consistent structure.
  - `aot doctor` — runtime / data dir / recent sessions / hooks wiring
    self-check. Each check returns ok/warn/fail with a `fix:` hint when
    something needs attention. `--format json` for scripting.
  - `aot config get|set|unset|list` — TOML at
    `~/.config/agent-output-tracer/config.toml` (overridable via
    `AOT_CONFIG_DIR` env). Validates `defaults.density` and
    `defaults.color` enums; rejects unknown keys with the same 3-line
    error UX.
- 19 new unit tests covering Palette TTY/NO_COLOR/--color logic, error
  block formatting (minimal / multiline cause / aligned tries), doctor
  text + JSON output (empty data dir + seeded), and the full config
  get/set/unset/list round-trip.
- README.md rewritten as an install + daily-usage runbook with the
  Claude Code 2-step marketplace flow, Codex feature-flag setup,
  per-verb examples, and a phase status table.



Phase C — Codex CLI support. Codex sessions now record alongside Claude
Code through the same hook script set, with runtime engine detection
choosing the right adapter. 328 tests pass on Python 3.13; hook runtime
still 3.9-compatible.

### Added

- Phase C-1: `adapters/codex.py` — normalize 7 Codex hook events
  (`session_start` / `user_prompt_submit` / `pre_tool_use` /
  `post_tool_use` / `stop` / `pre_compact` / `post_compact`). Codex's
  `permission_request` is observed by Codex but intentionally not
  recorded (design §3.2.2). `core/normalizer.py` adds `"codex"` to
  `SUPPORTED_ENGINES`. 20 unit tests.
- Phase C-2: single `hooks/hooks.json` covers both engines. New scripts
  `hooks/session_start.py` / `pre_compact.py` / `post_compact.py` for
  the Codex-only event names. `hooks/_runner.py` detects engine from
  the payload (Codex emits `permission_mode` on every event; Claude
  Code does not) and dispatches to the right adapter. PreToolUse /
  PostToolUse matcher now also covers Codex's `apply_patch`.
- Phase C-3 / C-10: `docs/INSTALL.md` Codex section — marketplace add,
  `[features] codex_hooks = true` feature flag (required; without it
  Codex silently ignores hooks), version requirements (≥ 0.128 for
  plugin-bundled hooks, ≥ 0.129 for compaction events), trusted-project
  caveat, env var resolution order.
- Phase C-4: `core/path_utils.resolve_data_dir` lookup order extended
  to `CLAUDE_PLUGIN_DATA` → `CODEX_PLUGIN_DATA` → default Codex install
  cache path. Forward-compatible if a future Codex release ships its
  own native env var.
- Phase C-5: no active SessionEnd synthesis. `metadata.json` is
  rewritten on every appended event (Phase A-3 behavior), so
  `ts_end` / counters stay current without a finalize step — Codex's
  lack of a session-end signal is a non-issue in practice.
- Phase C-6: PostToolUse limitation (Bash / `apply_patch` / MCP only)
  documented; adapter still extracts `command` for Bash and
  `file_path` / `path` for the other Codex tool shapes.
- Phase C-7: 8 integration tests exercising real hook-script
  subprocesses with Codex-shaped payloads. Engine-detection regression
  test confirms a Claude-shaped payload still routes to the Claude
  adapter even though the script is now bi-engine.
- Phase C-8: cross-engine `session_id` collision policy — UUID
  conventions on both sides make real collisions vanishingly rare;
  operators that need stronger separation pass distinct `--data-dir`.
- Phase C-9: Codex `turn_id` propagated through normalization onto
  the normalized event when present (omitted for non-turn-scoped
  events like SessionStart / PreCompact / PostCompact).



Phase B-6 through B-9 — graphing, bundled forensic export, anomaly
hints, and retention/GC. 296 tests pass on Python 3.13; hook runtime
still 3.9-compatible.

### Fixed

- `mentioned-but-not-read`: trailing-slash tokens were never grounded
  by user prompts because `os.path.basename("~/proj/hooks/")` returns
  `""`. The token is now stripped of trailing slashes before basename
  lookup, and the stripped form is also matched directly against
  user_prompt and tool_response text. Caught on live-session smoke.

### Added

- CLI integration tests for the Phase B-6..B-9 surface
  (`tests/integration/test_cli_new_commands.py`): causal-graph stdout +
  `--output`, export-trace stdout + `--output`, replay `--show-hints`
  text + json, gc `--dry-run` + actual mutation. 8 new tests.
- Phase B-6: `causal-graph` command — render a session as a mermaid
  `graph TD` block with one node per event, linear edges, and dashed
  `Glob → Read` arrows when a Read's path appeared in a prior Glob's
  result. `--output <file>` writes the markdown bundle; stdout
  otherwise. 10 unit tests.
- Phase B-7: `export-trace` command — bundles replay (markdown) + diff
  + mentioned-but-not-read + causal-graph into one forensic report
  markdown. Metadata table at the top, sections under `## …`
  headers. 6 unit tests.
- Phase B-8: anomaly hints. `analyzer/anomaly_hints.detect_hints` runs
  7 patterns from DESIGN §11 Phase B-8 — repeated_read,
  routing_config_thrash, long_session_outlier (cross-session
  percentile), config_drift (wrapper↔core within window),
  namespace_bleed (boundary-prefix mixing), protected_bash_read,
  skill_group_parallel (Task subagent_type within window). Wired into
  `replay --show-hints` (text / json / markdown formats all emit them).
  15 unit tests covering each pattern's hit and miss cases.
- Phase B-9: `gc` command. `core.retention.run_gc` walks the data dir
  and, per DESIGN §9.4, strips content fields (`tool_response`,
  `agent_response_text`, `user_prompt_text`, `command`, `raw_event`)
  for sessions older than `--archive-days` (default 30) while
  preserving counters, then deletes session dirs older than
  `--delete-days` (default 365). `--dry-run` reports without mutating.
  Already-stripped sessions skipped on re-runs. Corrupt metadata
  silently bypassed. 10 unit tests. 287 total pass.

## [0.2.0] — 2026-05-15

Phase B-2 through B-5 — the high-value forensic commands. `trace` /
`why` / `diff` / `mentioned-but-not-read` ship together. 246 tests
pass on Python 3.13; hook runtime still 3.9-compatible.

### Added

- Phase B-5: `mentioned-but-not-read` command (DESIGN §7.3.8).
  Session-level hallucination candidate extractor. Walks every
  `agent_response`, pulls path-like tokens, and returns those the user
  never prompted and no tool response introduced. Basename-aware
  grounding (user `foo.md` → agent `/proj/foo.md` is grounded). CLI
  exit codes: 0 clean, 3 candidates surfaced. 11 unit + 3 CLI
  integration tests.
- Phase B refactor: extract the shared path-token regex into
  `core/references.py` (`extract_path_tokens`). `query/diff.py` updated
  to use it, no behavior change. 246 total pass.
- Phase B-4: `diff` command. Two-way asymmetric report on a session:
  paths the user mentioned in any prompt that the agent never touched,
  and paths the agent touched whose full path or basename never appears
  in any user prompt. Basename-aware matching (user says `foo.md` →
  agent reads `/proj/foo.md` is counted as served; user says `log.py`
  → agent reads `/proj/dialog.py` is still flagged as unprompted).
  11 unit + 3 CLI integration tests. 232 total pass.
- Phase B-3: `why` command. Identifies a target event by `--path` /
  `--tool` / `--ts` / `--event-index` and surfaces (a) the three events
  immediately before, (b) the most-recent user_prompt prior, and
  (c) a "Glob origin" — a prior `post_tool` Glob whose response
  contained the target's path (catches "agent picked this from a Glob
  result without explicit user mention"). 14 unit + 4 CLI integration
  tests. 218 total pass.
- Phase B-2: `trace` command. Given `--session <spec> --output <phrase>`,
  finds the first `agent_response` containing the phrase, walks back
  through prior events, classifies each prior Read by whether its
  `tool_response` contains the phrase, and flags
  `hallucination_candidate` when no user prompt nor Read source can
  explain where the phrase came from. CLI exit codes: 0 grounded /
  not-found, 3 hallucination candidate (so scripts can branch). 13 new
  unit tests + 5 CLI integration tests. 200 total pass.

## [0.1.0] — 2026-05-15

Phase A milestone: Claude Code capture pipeline + the headline forensic
query surface (`replay`, `list`, `latest`, `grep`, `state-at`). 182 tests
pass on Python 3.13; hook runtime verified under macOS system Python 3.9.

### Added

- Phase A-0: repo skeleton, directory layout, pyproject, CI workflow stubs.
- Phase A-1: Claude Code plugin manifest (`.claude-plugin/plugin.json`),
  Codex plugin manifest mirror (`.codex-plugin/plugin.json`),
  hooks registration (`hooks/hooks.json`), and 5 hook entry scripts
  (`user_prompt_submit` / `pre_tool_use` / `post_tool_use` / `stop` /
  `session_end`) running in install-verify mode — each fires writes one
  diagnostic line to `${CLAUDE_PLUGIN_DATA}/_install_verify.jsonl` so the
  operator can confirm the plumbing is wired. Hook scripts are 3.9+
  compatible (run under any `python3` on PATH).
- `docs/DESIGN.md` (design document transplant) and `docs/INSTALL.md`
  (Claude Code + Codex install / verify steps).
- Phase A-2: `adapters/claude_code.py` normalizes the 5 hook event types
  to the engine-agnostic schema in DESIGN §3.3 / §5.1
  (`user_prompt` / `pre_tool` / `post_tool` / `agent_response` /
  `session_end`). Returns None for non-dict input, unknown
  `hook_event_name`, or missing `session_id`. Path extraction for Read /
  Write / Edit / MultiEdit / Glob / Grep. Bash command captured
  separately. `tool_response` is stringified for downstream grep when not
  already a string. Injectable `now` for deterministic tests.
  `core/normalizer.py` dispatches by engine. 31 unit tests covering all
  event types, both happy paths and malformed inputs.
- Phase A-3: `core/path_utils.py` (data-dir resolution from
  `CLAUDE_PLUGIN_DATA`, session_id traversal guard) and `core/recorder.py`
  (`append_event` → `<data_dir>/sessions/<session_id>/events.jsonl` plus
  `metadata.json` with ts_start / ts_end / tool_calls_total /
  user_prompts_count / agent_responses_count / unique_files_read /
  total_bytes_read). Metadata is rewritten atomically via temp+rename
  and self-heals if found corrupt. `hooks/pre_tool_use.py` rewritten to
  feed real events through the normalizer → recorder chain. e2e smoke
  confirmed under macOS system Python 3.9.6. 20 new recorder tests; 51
  total pass.
- Phase A-4: All 5 hook scripts (`user_prompt_submit` / `pre_tool_use` /
  `post_tool_use` / `stop` / `session_end`) now feed real events through
  the normalizer → recorder chain. Common pipeline factored into
  `hooks/_runner.run_hook(event_type)`. Transitional install-verify
  helper removed. New integration suite `tests/integration/test_hook_scripts.py`
  runs each script as a real subprocess: well-formed event, bad JSON,
  empty stdin, missing env, pre/post pair round-trip, full 5-hook session.
  74 total pass.
- Phase A-5: `core/redactor.py` masks common secret formats
  (OpenAI / Anthropic API keys, GitHub PATs, AWS access keys, JWTs,
  generic `password=`/`token=`/`secret=` key-value pairs with 16+ chars
  of value) with `[REDACTED]` before write. `redact_event` walks the
  event recursively (tool_input, raw_event, paths). Recorder wires
  redaction in by default; `redact=False` is available for tests.
  98 total pass.
- Phase A-6: `replay` command — the headline forensic capability.
  `core/session_io.py` (`load_events` / `load_metadata` / `list_sessions`,
  silently skips corrupt JSONL lines, rejects unsafe session_id),
  `core/time_utils.py` (short_time / long_time / human_bytes /
  truncate), `query/replay.py` (text / json / markdown formats, header
  with counters, per-event timeline rendering with tool name, paths,
  Bash command, and human-readable byte counts), and `cli/main.py`
  argparse entry exposed as the `agent-output-tracer` console script.
  e2e demo (5 hooks → recorder → replay) verified under macOS system
  Python 3.9.6 + dev venv. 128 total pass.
- Phase A-7: session navigation. `core/session_resolver.py` parses
  DESIGN §8.3 specs (`latest`, `latest-N`, full id, ≥4-char unique
  prefix, ISO date `YYYY-MM-DD`). `AmbiguousSessionSpec` raised on
  multi-match prefixes. New CLI subcommands `list` (text table or
  `--format json`, optional `--last N`) and `latest`. `replay
  --session` accepts every spec form. 149 total pass.
- Phase A-8: `grep` command — regex search across every string-bearing
  field of a session (user_prompt_text / agent_response_text /
  tool_response / command / tool_name / stop_reason / cwd /
  paths[i] / tool_input.\*). `-i` flag for case-insensitive. Returns
  grep-conventional exit codes (0 = matches, 1 = none, 2 = error).
  Session spec resolver applied to `--session`. 164 total pass.
- Phase A-9: `state-at` command — snapshot of session state at a chosen
  moment (DESIGN §7.3.5). Time spec accepts ISO 8601, HH:MM:SS
  (rendered against the session's date), or `latest`. Output: unique &
  total file reads, byte count, user prompts / tool calls / agent
  responses counters, top-10 reads with a `⚠️ repeated` flag at the
  3+ threshold. 177 total pass.
- Phase A-10: end-to-end lifecycle test driving a multi-turn session
  through every hook script (subprocess) and exercising every Phase A
  query (replay / list / latest / grep / state-at). Performance budget
  test asserts `append_event` averages <15ms per call (DESIGN §9.5) and
  1000 events finalize in under 5s. README updated to v0.1.0 with real
  CLI output. 182 total pass.

[0.9.8]: https://github.com/itosdad/agent-output-tracer/releases/tag/v0.9.8
[0.9.7]: https://github.com/itosdad/agent-output-tracer/releases/tag/v0.9.7
[0.9.6]: https://github.com/itosdad/agent-output-tracer/releases/tag/v0.9.6
[0.9.5]: https://github.com/itosdad/agent-output-tracer/releases/tag/v0.9.5
[0.9.4]: https://github.com/itosdad/agent-output-tracer/releases/tag/v0.9.4
[0.9.3]: https://github.com/itosdad/agent-output-tracer/releases/tag/v0.9.3
[0.9.2]: https://github.com/itosdad/agent-output-tracer/releases/tag/v0.9.2
[0.9.1]: https://github.com/itosdad/agent-output-tracer/releases/tag/v0.9.1
[0.9.0]: https://github.com/itosdad/agent-output-tracer/releases/tag/v0.9.0
[0.8.1]: https://github.com/itosdad/agent-output-tracer/releases/tag/v0.8.1
[0.8.0]: https://github.com/itosdad/agent-output-tracer/releases/tag/v0.8.0
[0.7.2]: https://github.com/itosdad/agent-output-tracer/releases/tag/v0.7.2
[0.7.1]: https://github.com/itosdad/agent-output-tracer/releases/tag/v0.7.1
[0.7.0]: https://github.com/itosdad/agent-output-tracer/releases/tag/v0.7.0
[0.6.0]: https://github.com/itosdad/agent-output-tracer/releases/tag/v0.6.0
[0.5.0]: https://github.com/itosdad/agent-output-tracer/releases/tag/v0.5.0
[0.4.0]: https://github.com/itosdad/agent-output-tracer/releases/tag/v0.4.0
[0.3.0]: https://github.com/itosdad/agent-output-tracer/releases/tag/v0.3.0
[0.2.0]: https://github.com/itosdad/agent-output-tracer/releases/tag/v0.2.0
[0.1.0]: https://github.com/itosdad/agent-output-tracer/releases/tag/v0.1.0
