# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.1.0]: https://github.com/itosdad/agent-output-tracer/releases/tag/v0.1.0
