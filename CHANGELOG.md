# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] — 2026-05-15

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

[0.3.0]: https://github.com/itosdad/agent-output-tracer/releases/tag/v0.3.0
[0.2.0]: https://github.com/itosdad/agent-output-tracer/releases/tag/v0.2.0
[0.1.0]: https://github.com/itosdad/agent-output-tracer/releases/tag/v0.1.0
