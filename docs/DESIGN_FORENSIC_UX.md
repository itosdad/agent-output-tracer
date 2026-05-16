---
title: agent-output-tracer — Phase D Power-Up design (Forensic UX enhancement)
plugin_name: agent-output-tracer
target_repo: ~/work/agent-output-tracer/
phase: D (next-generation design predicated on Phase A-C completion)
intended_engines:
  - Claude Code (primary axis; assumed implemented in Phase A-B)
  - Codex CLI (assumed implemented in Phase C)
date: 2026-05-15
author: Claude (claude-opus-4-7, 1M context)
status: design draft (pre-implementation; written at a granularity that allows handoff to other sessions)
companion_doc: docs/DESIGN.md (Phase A-C design baseline; this document extends it)
primary_sources:
  - Claude Code official docs: https://code.claude.com/docs/en/
  - Codex official docs: https://developers.openai.com/codex/
  - Codex generated schemas: https://github.com/openai/codex/tree/main/codex-rs/hooks/schema/generated
  - DESIGN.md in this repo (especially §0.5 design rationale, §1.2 non-goals, §2 design principles)
verification_dates:
  - CC / Codex debug-mode feature gap investigation: 2026-05-15 (via claude-code-guide / general-purpose subagent)
handoff_notes:
  - This document records only diffs and extensions to DESIGN.md. The Phase A-C baseline takes DESIGN.md as the primary source.
  - Intended granularity: implementable for D-1 on a cold read. When starting implementation, begin at §9 Phased rollout.
  - When a philosophical conflict is suspected, consult §1 Philosophical axes → DESIGN.md §0.5 / §1.2 / §2.
  - Unverified items are consolidated in §11; complete primary-source verification before starting implementation.
---

# ⚠ Historical baseline — Phase D design draft (2026-05-15)

This document is the **pre-implementation design** of Phase D
(forensic UX power-up + TUI side-channel). It is preserved as the
historical record of how Phase D was scoped before code was written.

For the **current state**, refer to:

- [`README.md`](../README.md) — overview, screenshots, current
  status table covering Phase D + TUI Phase 1–4.A as shipped
- [`docs/TUI.md`](TUI.md) — comprehensive TUI guide
- [`CHANGELOG.md`](../CHANGELOG.md) — per-version diff

Implementation has shipped Phase D in full plus the TUI Phase 1–4.A
that wasn't in the original draft (engine themes, OhMyZsh-style
banner, menu preview pane, clipboard yank, sticky defaults, etc.).
This document is not deleted because the §1 Philosophical axes / §2 design
principles are still load-bearing for PR review.

---

# 0. Executive Summary

## 0.1 In one line

On top of the forensic recorder + post-hoc query CLI completed in Phase A-C, add **"a side-channel UI that enables forensic analysis without ever interrupting the session"** and **"unique workflows that support user judgment (bisect / note / find vocabulary / content-address)"**, plus a full power-up that **translates the strengths of the Claude Code / Codex standard debug modes into AOT philosophy**.

## 0.2 Problems solved

| Problem | Existing (as of Phase C completion) | Solution in Phase D |
|---|---|---|
| Running forensic commands inside the CC TUI contaminates the observed target | Only slash command / Bash routes available; consumes context tokens | Side-channel `aot tui` running persistently in a separate pane, fully decoupled from CC |
| "Where did things go wrong" can only be searched by visual replay | Scroll the replay up and down | git-bisect-style `bisect` workflow |
| No way to attach conclusions or hypotheses to a session | Must be transcribed to external doc / memo | Persist in session metadata via `note` |
| Anomaly hints stop at "per-hint output" | Inline display during replay only | Vocabularize via `find`, enabling search / aggregation |
| Cannot tell whether the same tool_response appeared in other sessions | Session-isolated forensic design | Cross-session matching via content-addressable (SHA256), opt-in |
| Cost / token / latency / engine-side permission decision invisible | Many things unobtainable via the hook route | Complement via **one-way bridges**: OTel sidecar export and engine-log overlay |
| CLI is long and typing is heavy | Only the absolute form `agent-output-tracer ...` | `aot` alias, no-argument defaults, tab completion, density switching |

## 0.3 Three design pillars

| Pillar | Role | Main deliverables |
|---|---|---|
| **Pillar 1: Forensic UX layer** | Directly touches the user's fingertips and eyes | CLI verb reorganization, alias, color, density switching, error UX, slash command policy |
| **Pillar 2: Causal Core deepening** | The core where AOT's distinctiveness lives | Schema v2, bisect, note, find vocabulary, content-address, bidirectional trace |
| **Pillar 3: Interop Bridges** | Translate the strengths of existing debug modes into the philosophy and absorb them | engine-log overlay, OTel sidecar, cross-session index (all opt-in) |

## 0.4 Phasing

| Phase | Purpose | Dependencies |
|---|---|---|
| D-1 | UX foundation (alias / density / color / errors / doctor / config) | None |
| D-2 | Schema v2 (purely additive; reader supports both v1/v2) | None |
| D-3 | Causal Core enhancement (find vocabulary / trace extension / bisect / note / stats) | D-2 |
| D-4 | Live UX (tail / replay --watch / stream-json) | D-2 |
| D-5 | aot tui (side-channel TUI, primary non-interrupting UI) | D-3, D-4 |
| D-6 | Bridges (engine-log overlay / OTel sidecar / cross-session) | D-2, D-3 |
| D-7 | Safe-share Export | D-2 |

---

# 1. Philosophical axes

## 1.1 Constitution (restated from DESIGN.md §2; **not relaxed at all** in Phase D)

| Principle | No evolution |
|---|---|
| Issue-agnostic | Do not auto-classify anomalies; keep anomalies at the hint level |
| User-driven | Proactive alerts default off; dispatch is user-initiated |
| Mechanical | No reliance on agent self-report; hook payload only |
| Observation-only | All hooks `exit 0`; never intervene |
| Host repo non-contamination | Writes go only under `${CLAUDE_PLUGIN_DATA}`; do not write to `<host>/tasks/` etc. either |
| Engine-agnostic | The normalized event schema is the single source of truth |

## 1.2 Principles added in Phase D

| New principle | Intent | Scope |
|---|---|---|
| **Defaults that just work** | Most frequent behavior with no arguments (`aot` alone = `replay latest --brief`) | Entire CLI |
| **Bridges are explicit and one-way** | OTel / engine-log / cross-session always opt-in; AOT → outward only | All of Pillar 3 |
| **Composable exit codes & --json everywhere** | Every query has `--json` so it can be embedded in shell pipelines / CI | All subcommands |
| **Schema additive evolution** | v1 → v2 → v3 is additive only; readers can read older versions | All of events / metadata / index |
| **Color & density honor the user's terminal** | `NO_COLOR` / `--color {auto,always,never}` / TTY detection; density has 4 levels: brief / full / raw / json | Both CLI and TUI |
| **Errors carry next-action** | Errors guarantee 3 lines: "what happened / cause / commands to run next" | All subcommands |

## 1.3 Rules for detecting philosophical conflicts

Revisit design decisions if any of the following signals appear during Phase D implementation:

- "Proactively warn" proposals → conflict with §1.1 user-driven; reject
- "Inject a slash command into the agent" proposals → conflict with §1.1 observation-only; immediate reject (Phase D ships no slash commands at all / OQ6 decision 2026-05-15)
- "Write into the host repo" proposals → conflict with §1.1 host repo non-contamination; immediate reject
- "Embed an OTel collector" proposals → conflict with §0.3 Pillar 3 "bridges are one-way"; stay with sidecar exporter

---

# 2. Overall architecture diagram

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                        Pillar 1: Forensic UX layer                           │
│  CLI verbs (17) ─ alias `aot` ─ 4 density levels ─ color ─ 3-line errors ─   │
│   doctor / config                                                            │
│  aot tui (side-channel TUI, primary non-interrupting UI)                     │
└──────────┬──────────────────────────────────────────────────────────┬────────┘
           │                                                          │
           ▼                                                          ▼
┌──────────────────────────────┐                ┌─────────────────────────────────┐
│   Pillar 2: Causal Core      │                │   Pillar 3: Interop Bridges     │
│                              │                │   (all opt-in, one-way)         │
│  events.jsonl v2             │                │                                 │
│   - SHA256 / tool_use_id     │                │  engine-log overlay             │
│   - correlation_id / tokens  │   (read-only   │   (merge ~/.claude/debug/*)     │
│   - parent_session_id        │    consumer)   │                                 │
│                              │ ──────────────▶│  OTel sidecar export            │
│  index.json v2               │                │   (aot.session/turn/tool span)  │
│   - bigram_inverted          │                │                                 │
│   - content_hash_to_events   │                │  cross-session global_index     │
│   - phrase_to_first_agent    │                │   (for review / --since)        │
│                              │                │                                 │
│  metadata.json v2            │                │  (slash commands not shipped:   │
│   - notes / findings         │                │    OQ6 decision, aot tui is     │
│   - anomaly_counters         │                │    the sole non-interrupting    │
│                              │                │    UI)                          │
│  query: trace±/bisect/note   │                └─────────────────────────────────┘
│         find/stats/review    │
└──────────────────────────────┘
           ▲
           │ hook payload (unchanged from Phase A-C)
           │
┌──────────────────────────────────────────────────────────────────────────────┐
│           hooks/ (5 kinds) ─ adapters/{claude_code,codex}.py ─ recorder      │
│                                                                              │
│           Phase D leaves hooks themselves unchanged (observation-only kept)  │
│           If new fields (tokens etc.) arrive in hook payload, they go to v2  │
│           via the adapter                                                    │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

# 3. CLI verb canonical table

## 3.1 Verb list (17 verbs)

| Group | Verb | alias | Status | Role |
|---|---|---|---|---|
| Browse | `replay` | `r` | Extended | Timeline playback; `--brief/--full/--raw`, `--watch`, `--overlay engine-log` |
| Browse | `list` | `ls` | Extended | Session list; `--filter` (engine, has-hallucination, has-notes, prefix) |
| Browse | `latest` | `l` | Extended | Latest session id; last N entries via `--n N` |
| Browse | `tail` | `t*` | **New** | Follow events.jsonl of an in-progress session; `--format stream-json` |
| Browse | `tui` | — | **New** | Side-channel TUI (non-interrupting UI; see §5 for details) |
| Search | `grep` | `g` | Extended | Full-text regex search; `-C N` (context); colored matches |
| Search | `find` | `f` | **New** | Anomaly vocabulary search (§7.4) |
| Trace | `trace` | `tr` | Extended | Reverse lookup of output phrases; `--missing` / `--by-sha` (§7.1) |
| Trace | `why` | `w` | Existing | Query the reason for an individual event |
| Trace | `diff` | `d` | Existing | Diff between user instruction and agent action |
| Trace | `graph` | `gr` | Renamed | Shortened name for existing `causal-graph` |
| State | `state-at` | `s` | Extended | Cumulative state at any time; adds `--since-prompt` / `--before-event` |
| State | `stats` | — | **New** | Session-level forensic stats (anomaly / bytes / unique paths, not cost) |
| Workflow | `bisect` | — | **New** | git-bisect-style binary search (§7.2) |
| Workflow | `note` | `n` | **New** | Attach human-curated annotations to a session (§7.3) |
| Workflow | `review` | — | **New** | User-explicit cross-session summary via `--since DATE` (§7.6) |
| Meta | `doctor` | — | **New** | Self-diagnostics (§7.7) |
| Meta | `config` | — | **New** | Configuration operations without directly editing TOML (§7.8) |
| Meta | `export` | `x` | **New** | Safe-share export (`--safe-share`; §7.9) |
| Meta | `purge` | — | **New** | Session deletion (called from doctor's `fix:`) |

`t*` = the alias for `tail` is `t`, but to avoid collision with the §1.1 "trace" verb's alias `tr`, leaving `tail` without an alias is an option. Decide at implementation time.

## 3.2 Why we do not create sub-subcommands

The groups `browse / search / trace / state / workflow / meta` are conceptual organization only; the CLI is flat. Hierarchies like `aot trace search foo` hurt typing speed, so we do not create them. Instead, ergonomics are secured via **aliases + strong `--help` + tab completion**.

## 3.3 Exit code convention

| code | Meaning | Subcommands using it |
|---|---|---|
| 0 | Success / match found | General |
| 1 | No match | `grep` / `find` (follows grep convention) |
| 2 | User error (session not found / invalid regex / time parse failure / bad arguments) | General |
| 3 | Special finding | `trace`: hallucination_candidate / `bisect`: aborted |
| 4 | I/O error | Data dir missing / permission denied |
| ≥10 | Reserved (future extension) | — |

## 3.4 `--json` across all subcommands

Every subcommand has `--json`, and structured output schemas are **versioned `v` per subcommand**. Example:

```json
{"$schema": "aot/trace/v1", "session_id": "...", "phrase": "...", "verdict": "grounded|hallucination_candidate|not_found", "sources": [...], "...": ...}
```

For CI use.

---

# 4. Output UX

## 4.1 4 density levels

| Density | Use case | Default subcommands |
|---|---|---|
| `--brief` | One event per line, abbreviated proper nouns | `replay`, `list` |
| `--full` | Existing standard output | `trace`, `why`, `state-at` |
| `--raw` | Nearly the internal JSON as-is | Machine reading |
| `--json` | Schema fixed per subcommand | Scripting |

User defaults can be overridden via `aot config set defaults.density brief|full`.

## 4.2 Colors and glyphs (ASCII only; no emoji)

| event / state | Glyph | Color |
|---|---|---|
| user_prompt | `>>` | cyan |
| pre_tool | `..` | dim |
| post_tool | `↪` | normal |
| agent_response | `<<` | green |
| session_end | `==` | dim |
| hint | `!` | yellow |
| hallucination_candidate | `?` | red |
| note (human-attached) | `*` | magenta |
| engine overlay line | `@engine` | dim cyan |

Color OFF conditions: `NO_COLOR` env / `--color never` / `not isatty(stdout)`.

## 4.3 3-line error structure

```
error: <short declaration>
  cause: <primary cause, with data if possible>
  try:   <1-3 commands to run next>
```

Example:

```
$ aot trace --session abc --output "JWT"
error: session 'abc' is ambiguous
  cause: 3 sessions match prefix 'abc' in your data dir
           abc94a3e-...  2026-05-12-pm3
           abc12f70-...  2026-05-08-am2
           abcd8e21-...  2026-04-30-pm5
  try:   aot list --filter prefix=abc
         aot trace --session abc94a3e --output "JWT"
```

The same shape is guaranteed across all error kinds. In `aot doctor` the `fix:` line plays the same role.

## 4.4 Tab completion

Emit completion scripts via `aot --install-completion {bash,zsh,fish}`. Session specs are also completed (the 20 most recent sessions are presented).

---

# 5. `aot tui` detailed design

## 5.1 Role

**Primary non-interrupting forensic UI.** An independent process that does not communicate with CC at all and follows `${CLAUDE_PLUGIN_DATA}/sessions/` events.jsonl via fsevents/inotify. Intended to run persistently in a tmux split / iTerm pane / separate window.

## 5.2 Layout

```
┌─ aot tui ─────────────────────────────────────────────────────────────────┐
│ Status bar: session id / live·past / engine / hint count / cand / notes   │
├──────────────────────────┬────────────────────────────────────────────────┤
│ Session list (28 cols)   │ Main pane                                      │
│  ● current               │  Renders timeline / overlay (why/trace/bisect/ │
│  ○ recent N              │   note/find/grep) in one pane by mode switch   │
│                          │                                                │
│  [filter]  [search]      │                                                │
├──────────────────────────┴────────────────────────────────────────────────┤
│ Keybinding hint bar (changes by mode)                                     │
└───────────────────────────────────────────────────────────────────────────┘
```

Detailed per-mode screens live outside this document, in `docs/wireframes/` (to be added at implementation time) or in the wireframe output from the conversation.

## 5.3 Key bindings

| Key | Action | State transition |
|---|---|---|
| `j` / `k` | Event cursor movement | timeline mode |
| `↑` / `↓` | Session cursor movement | session list focus |
| `Tab` | Switch pane focus (session list ⇄ main) | any |
| `Enter` | Event detail / confirm session selection | mode-dependent |
| `t` | trace (from cursor's agent_response) | timeline → trace overlay |
| `w` | why (from cursor's event) | timeline → why overlay |
| `b` | Start bisect | timeline → bisect mode |
| `n` | note input | timeline → note form |
| `f` | find vocabulary picker | timeline → find mode |
| `/` | grep input | timeline → grep mode |
| `s` | session switch picker | any |
| `o` | Toggle engine-log overlay | timeline |
| `x` | Export current view | any |
| `?` | help overlay | any |
| `Esc` | Close overlay / return from mode | any |
| `q` | quit | any |

## 5.4 File watch strategy

| Platform | 1st choice | Fallback | Verification needed? |
|---|---|---|---|
| macOS | fsevents (watchdog) | polling 500ms | Measure in §11 |
| Linux | inotify (watchdog) | polling 500ms | Measure in §11 |
| Windows | ReadDirectoryChangesW (watchdog) | polling 500ms | Outside official support; polling only |

events.jsonl is append-only, so we hold only the "last inode position", and when a watch event arrives we read the appended portion and push it to the tail buffer.

## 5.5 Dependency package selection

| Library | Role | Decision |
|---|---|---|
| `textual` | TUI framework (declarative layout / event loop on top of rich) | **First choice** (modern; declarative layout) |
| `urwid` | TUI framework (classic) | Alternative candidate (Python 3.9 compatibility is certain) |
| `curses` (stdlib) | Minimal fallback | Only if all the above are unusable |
| `watchdog` | Cross-platform file watch | Adoption candidate (fsevents / inotify / per-OS integration) |

**Policy**: keep the core CLI dependency-free. Isolate the TUI as an **optional dependency** via `pip install agent-output-tracer[tui]`. If not installed when `aot tui` starts, display:

```
error: 'aot tui' requires optional dependencies
  cause: textual / watchdog not installed
  try:   pip install 'agent-output-tracer[tui]'
```

## 5.6 Launch options

```
aot tui [--session SPEC] [--data-dir PATH] [--no-color] [--polling]
```

- `--session SPEC` specifies the initial session (default = `latest`)
- `--polling` forces fsevents/inotify OFF (for CI / virtualized environments)

## 5.7 Non-interruption guarantees

- No process communication with CC
- State touched by CC (`~/.claude/projects/...`) is **read-only**; CC debug logs are read only when `--overlay engine-log` is specified
- AOT's own events.jsonl is append-only; reads use inode tracking and do not collide

---

# 6. Schema v2 specification

## 6.1 Design policy

**Purely additive.** A v1 reader can ignore the added fields in v2 events. A v2 reader reads v1 events with a `None` fallback. If the `v` field is missing, treat as v1.

## 6.2 events.jsonl v2 (fields added vs. v1)

| field | Appears in event | Type | Role | When missing |
|---|---|---|---|---|
| `v` | All | int | Schema version (v2) | Reader treats as v1 |
| `response_sha256` | post_tool | str (hex 64) | SHA256 of tool_response body | Content-address unavailable; otherwise no impact |
| `response_size_bytes` | post_tool | int | Full size independent of excerpt | Skipped in size stats |
| `tool_use_id` | pre_tool / post_tool | str | Engine-supplied (CC: `toolu_01...`); strict pre↔post linkage | pre/post linkage falls back to ts proximity |
| `correlation_id` | All | str (uuid) | Binds events within the same turn; origin of subagent lineage (generated by AOT) | Reduced trace / why precision |
| `parent_session_id` | Equivalent of session_start | str / null | Parent session of subagent / Task spawn | Lineage cannot be restored; treat as independent session |
| `tokens` | agent_response | object: `{input, output, cache_read, cache_creation}` (each int / null) | Only within the range provided by the hook payload | Skipped in stats / review |
| `duration_ms` | post_tool / agent_response | int / null | Engine-reported (if provided) | Skipped in profile stats |
| `hook_self_ms` | All | int | Processing time of the AOT hook itself | Skipped in self-instrumentation |
| `engine_version` | All | str | CC / Codex version | Displayed as unknown |
| `permission_mode` | All | str | Normalized common-required field across CC / Codex | Displayed as unknown |

## 6.3 metadata.json v2 (additions vs. v1)

| field | Type | Role |
|---|---|---|
| `v` | int | Schema version (2) |
| `notes_count` | int | Number of `note`s |
| `findings` | array of object | `bisect` conclusions etc. `{kind, event_idx?, ts, by}` |
| `anomaly_counters` | object | `{unmentioned_reads, repeated_reads, hallucination_candidates, glob_burst, routing_thrash, large_read}` |
| `tokens_total` | object | `{input, output, cache_read, cache_creation}` |
| `cwd_hash` | str (hex 64) | SHA256 of cwd (for identity hiding on safe-share export) |
| `engine_version` | str | Value from the session's first event |

## 6.4 index.json v2 (additions / evolution vs. v1)

| field | Role |
|---|---|
| `v` | Schema version (2) |
| `bigram_inverted` | Faster grep prefix search. Evolved from v1 word-level to bigram |
| `content_hash_to_events` | SHA256 → set of event idx. O(1) count of same tool_response occurrences |
| `path_first_seen` | path → first-occurrence event idx |
| `phrase_to_first_agent_event` | n-gram (length 3-5) → event idx where it first appeared in agent_response. Speeds up `trace` |

## 6.5 global_index.json (new, opt-in)

Created at `${CLAUDE_PLUGIN_DATA}/global_index.json`. **Only generated / updated when `aot review` is run or the `--cross-session` flag is set.** Never touched proactively (§1.1 user-driven).

| field | Role |
|---|---|
| `v` | Schema version (1) |
| `built_at` | Last build time |
| `retention_days` | 30 (default; changeable via config) |
| `sessions` | array `{session_id, ts_start, ts_end, engine, anomaly_counters, notes_tags}` |
| `phrase_cross_index` | n-gram → array `{session_id, event_idx}` |
| `path_cross_index` | path → array `{session_id, event_count}` |
| `sha_cross_index` | SHA256 → array `{session_id, event_idx, ts}` |

When `aot review` is launched, incrementally builds from the diff against the latest events.jsonl set.

## 6.6 v1 → v2 migration policy

| Action | Policy |
|---|---|
| Convert existing v1 events.jsonl | No. Keep as v1; reader supports both |
| New hook writes in v2 | After D-2 completion, writes are v2 |
| Handle a mix of old sessions | Yes. Reader dispatches per `v` |
| `aot doctor` displays schema versions | Yes: `schema v1: N, v2: M` |
| Forced migration command | Not provided (avoids overdesign) |

---

# 7. New query feature specifications

## 7.1 `trace` extensions

### 7.1.1 Existing (Phase B-2, implemented in CHANGELOG Unreleased)

```
aot trace --session SPEC --output PHRASE
```

Locate the first event where PHRASE appears in agent_response → walk prior user_prompts / Reads / tool_responses to decide grounded / hallucination_candidate. Exit 3 flags candidate.

### 7.1.2 Phase D extensions

#### `--missing` (inverse hallucination)

```
aot trace --session SPEC --missing PHRASE --reference-paths PATH1,PATH2,...
```

Intent: detect "the user asked a question premising material they had the agent read, but the corresponding keyword does not appear in agent_response."

| Input | Content |
|---|---|
| `--missing PHRASE` | Expected phrase |
| `--reference-paths` | Reference paths the user expects to be consulted |

Output: enumerate events where "the tool_response of a reference path contained a token derived from the phrase, but the agent did not mention it."

Philosophical alignment: the user provides expectations explicitly, so AOT only matches and does not judge.

#### `--by-sha` (content-address)

```
aot trace --by-sha SHA256_HEX [--since DATE]
```

Intent: aggregate how many times and in which sessions a given tool_response (SHA256) appeared elsewhere. Cross-session results go through global_index only when `--since` is specified (opt-in).

Philosophical alignment: cross-session is user-explicit opt-in, never proactive.

## 7.2 `bisect`

```
aot bisect start --session SPEC [--from EVENT_IDX] [--to EVENT_IDX]
aot bisect (good|bad|skip|view|quit)
aot bisect status
aot bisect log
```

### 7.2.1 Behavior

1. `start` determines the range [from, to] (default: 1 to last event)
2. Present the midpoint event; the user judges with `good/bad/skip`
3. Repeat log₂(N) times to identify the first-bad event
4. Append the conclusion to `metadata.findings[]` in the form `{kind: "bisect_first_bad", event_idx, steps, ts, by}`

### 7.2.2 Non-interactive mode (for CI)

```
aot bisect run --session SPEC --predicate 'jq ...'
```

If a predicate function (shell command that decides via exit 0/1) can be provided, automatic bisect is possible. Reserved as design headroom, but the non-interactive mode is **not implemented** in D-3; decision deferred to D-5 or later.

### 7.2.3 Persistence

- `metadata.findings[]` is append-only (no overwrites; re-bisecting preserves old findings)
- View history via `aot bisect log --session SPEC`

## 7.3 `note`

```
aot note add --session SPEC [--event IDX] [--tag TAG] [--finding FINDING_IDX] BODY
aot note list --session SPEC [--tag TAG]
aot note rm --session SPEC --id NOTE_ID
```

### 7.3.1 Storage

- `<session_dir>/notes.jsonl`, append-only
- One line = one note: `{id, ts, by, tag, body, links: {event_idx?, finding_idx?}}`
- `by` is the OS user / overridable via `aot config set user.name "X"`

### 7.3.2 Tag vocabulary (default)

`root-cause` / `observation` / `question` / `false-positive` / `followup` / `custom:<freeform>`

### 7.3.3 Search

Enumerate sessions with notes via `aot list --filter has-note[=TAG]`.

## 7.4 `find` (anomaly vocabularization)

### 7.4.1 Default vocabulary

| Term | Definition (strict) | Default parameters |
|---|---|---|
| `unmentioned-reads` | Path tokens are disjoint from the token set of every preceding user_prompt | — |
| `repeated-reads N` | Same path appears in post_tool at least N times | N=3 |
| `glob-burst` | K consecutive Reads of paths included in the immediately preceding Glob results | K=2 |
| `routing-thrash` | `CLAUDE.md` / `AGENTS.md` etc. are read at least M times in the same session | M=2; target paths configurable |
| `large-read N` | A single Read's result_bytes exceeds N KB | N=50 (KB) |
| `hallucinations` | agent_response with trace's hallucination_candidate flag set | — |
| `denied-permission` | From engine-log overlay; tool denied by permission_mode (D-6 onward) | — |
| `empty-glob` | Glob / Grep returns 0 results, and the immediately following agent_response refers to it as if it "found" something | — |
| `stale-cache` | Consecutive reads of the same path with the same SHA256 (visualizes wasted context budget) | — |
| `silent-failure` | post_tool ends in error / empty result and the immediately following agent_response does not mention it | — |
| `abandoned-write` | Re-Write / Edit on the same path without a Read in between after a Write / Edit (overwrite without review) | — |

### 7.4.2 User extensions

```toml
# config.toml
[find.custom]
my_pattern = { description = "...", regex = "...", target = "tool_response" }
```

### 7.4.3 Output

```
aot find VOCAB [--session SPEC] [--since DATE] [--json]
```

`--since` goes through global_index (opt-in).

## 7.5 `stats`

```
aot stats --session SPEC [--baseline 30d]
```

Outputs per-session forensic stats (**translates** CC `/usage`'s cost axis **into the forensic axis**):

| Metric | Content |
|---|---|
| `events_total` | Total event count |
| `tool_mix` | Per-tool ratio |
| `unique_paths_read` | Unique path count |
| `total_bytes_read` | Total bytes |
| `anomaly_counters` | From metadata |
| `tokens` | From metadata (if available) |
| `vs baseline` | Deviation from the user's past N-day average (opt-in) |

Cost is **not tallied** (API layer; not obtainable via AOT hooks). It is the responsibility of the OTel sidecar route to forward it to the organizational audit side.

## 7.6 `review`

```
aot review --since DATE [--until DATE] [--json]
```

Intent: user-explicit cross-session summary. **Translates** CC `/insights` **into user-driven form**. Never proactive.

Output (default brief per §4.1):

- Session count within the period / by engine / median duration
- Anomaly counter aggregates
- hallucination_candidate list
- Top read paths
- Sessions with notes

The sole subcommand that builds / consults global_index.json.

## 7.7 `doctor`

```
aot doctor [--json]
```

Self-diagnostics:

| Check | Output |
|---|---|
| runtime | Python version / hook runtime |
| data dir | path / size / session count / oldest |
| hooks | Hook registration status per engine |
| schema | v1/v2 ratio for the most recent 5 sessions; parse-failure / failed-load remnant warnings |
| redaction | Enable status; dry-run scan |
| bridges | otel / overlay / cross-session on/off status |
| recent activity | Session counts and anomaly counters for the past 7 days |

Each item has a `fix:` line presenting the command to run next (same shape as the error UX in §4.3).

## 7.8 `config`

```
aot config get KEY
aot config set KEY VALUE
aot config unset KEY
aot config list [--diagnose]
aot config schema [--json]
```

Do not have users edit `config.toml` directly (makes precedence visible). `--diagnose` shows **which source** a value came from (default / user config / env / CLI flag). Adopted from Codex's `/debug-config`.

`config schema` emits a JSON Schema (for IDE completion).

## 7.9 `export --safe-share`

```
aot export --session SPEC [--safe-share] [--format markdown|json|archive] [--keep-excerpt N]
```

Intent: export a session in a form safe to paste into team Slack / incident reports.

Transforms applied automatically with `--safe-share`:

| Transform | Content |
|---|---|
| Path abstraction | `/Users/<name>/...` → `<HOME>/...`; `/proj/foo/bar.ts` → `<repo>/foo/bar.ts` |
| cwd concealment | Keep only `cwd_hash`; remove the real path |
| tool_response removal | Remove body; keep only size / sha / excerpt (`--keep-excerpt N` characters; default 0) |
| user_prompt enhanced masking | Export-only secret pattern set (mail / phone / proper-noun option) |
| session_id shortening | First 8-character prefix |

`--format archive` packs as zip (events.jsonl / metadata.json / notes.jsonl / attached markdown bundled together).

## 7.10 `tail`

```
aot tail --session SPEC [--format text|stream-json] [--polling]
```

Follow events.jsonl of an in-progress session. `stream-json` is JSON Lines, one event per line. For direct connection with CI / log forwarders. AOT side owns the role of CC's `--output-format stream-json`.

## 7.11 `tui`

See §5 for details.

---

# 8. Bridges specifications

## 8.1 Common policy

| Principle | Application |
|---|---|
| Default OFF | All bridges must be explicitly enabled via `aot config set bridges.<x>.enabled true` |
| One-way | AOT → outward (read-only / write-only); two-way communication forbidden |
| AOT guarantees schema stability | AOT absorbs external schema variation |

## 8.2 engine-log overlay

```toml
[bridges.engine_log]
enabled = "auto"   # auto | true | false
claude_code_path = "~/.claude/debug/"     # auto-detect; CLAUDE_CODE_DEBUG_LOGS_DIR honor
codex_log_path = "$CODEX_HOME/log/"       # After Phase C completion
```

### 8.2.1 Behavior

1. `replay --overlay engine-log` or the `o` key in TUI
2. Read `~/.claude/debug/<session_id>.txt` etc. if present
3. Merge with events.jsonl via timestamp anchors and render as `@engine` lines

### 8.2.2 Available information (CC)

- Matcher evaluation results
- Source of permission decision (config / hook / user_permanent / user_temporary)
- auto-mode classifier response
- Hook execution timing / exit code

Fills the §A4 gap (permission decision audit) via the real-engine route. AOT is **read-only**; it does not affect the location or contents of the debug log.

## 8.3 OTel sidecar export

```toml
[bridges.otel]
enabled = false
exporter = "otlp-http"             # otlp-http | otlp-grpc | console | none
endpoint = "https://otel.example.com/v1/traces"
headers = { "x-otlp-api-key" = "$OTLP_TOKEN" }
log_user_prompt = false            # default false (redaction-strict)
log_raw_tool_response = false      # default false
```

### 8.3.1 Spans emitted

| span | Parent | attributes |
|---|---|---|
| `aot.session` | (root) | session_id (short hash), engine, engine_version, ts_start, ts_end, anomaly_counters |
| `aot.turn` | aot.session | correlation_id, user_prompt_present, agent_response_present |
| `aot.tool` | aot.turn | tool_name, paths_count, response_size_bytes, response_sha256, duration_ms, permission_mode |
| `aot.finding` | aot.session | kind (bisect_first_bad / hallucination_candidate), event_idx, ts |
| `aot.note` | aot.session | tag, links |

If `tokens` are included in events, add them as span attributes (can run in parallel with CC OTel `claude_code.llm_request`).

### 8.3.2 Operating modes

- **batch**: flush all spans at session_end
- **streaming**: emit sequentially in the hook back-end (D-6 back half; requires perf measurement)

D-6 implements batch only. Streaming is a Phase E candidate.

## 8.4 cross-session index

Defined in §6.5. The sole cross-session mechanism touched by `aot review` / `find --since` / `trace --by-sha --since`. **No proactive build**; incremental build at user invocation.

```toml
[bridges.cross_session]
enabled = false             # default off
retention_days = 30
auto_purge_on_doctor = true
```

`aot doctor --fix` presents retention-exceeded sessions as purge candidates.

---

# 9. Phased rollout

Each phase is **independently shippable** (stopping partway does not break existing features). Defined as a 3-tuple: Goal / Deliverable / Verification.

## 9.1 D-1: UX foundation

| Item | Content |
|---|---|
| Goal | `aot` alias, 4 density levels, color, 3-line errors, `doctor`, `config`, tab completion |
| Deliverable | Extend `cli/main.py`; `cli/colors.py` (new); `cli/errors.py` (new); `query/doctor.py`; `query/config.py`; `completion/_aot.{bash,zsh,fish}` |
| Verification | (1) Add `--brief/--full/--raw/--json` tests to every existing query  (2) `NO_COLOR` honoring test  (3) Snapshots showing each `aot doctor` check actually emits green / warn / fail  (4) Script test verifying tab completion returns `trace tail tui` for `aot t<TAB>` |
| Dependencies | None |
| Schema impact | None |

## 9.2 D-2: Schema v2

| Item | Content |
|---|---|
| Goal | Additively introduce v2 fields to events.jsonl / metadata / index; v1/v2 dual-support reader; `v`-missing fallback |
| Deliverable | Extend `core/recorder.py`; dual-support `core/session_io.py`; v2 field generation in `core/normalizer.py`; `core/indexer.py` (new; bigram / content_hash / phrase_to_first) |
| Verification | (1) Snapshot test verifying existing fixtures written as v1 do not break under the v2 reader  (2) Test verifying a v1 reader can ignore events written as v2  (3) Test verifying hook self_ms / correlation_id are always attached  (4) `aot doctor`'s schema integrity displays the v1/v2 ratio |
| Dependencies | D-1 (doctor extension shows versions) |
| Schema impact | events.jsonl, metadata.json, index.json |

## 9.3 D-3: Causal Core enhancement

| Item | Content |
|---|---|
| Goal | `find` vocabulary, `trace --missing` / `--by-sha`, `bisect`, `note`, `stats` |
| Deliverable | `query/find.py`; extend `query/trace.py`; `query/bisect.py`; `query/note.py`; `query/stats.py`; `analyzer/anomaly_vocab.py` |
| Verification | (1) Cover true-positive / false-positive across at least 3 fixture sessions for each find term  (2) CI test of `bisect run --predicate` non-interactive mode (not implemented in D-3; D-5 onward)  (3) Round-trip `note add` → `note list` → `list --filter has-note`  (4) Single-session round-trip of `trace --by-sha` (cross-session in D-6) |
| Dependencies | D-2 |
| Schema impact | metadata (findings / anomaly_counters) |

## 9.4 D-4: Live UX

| Item | Content |
|---|---|
| Goal | `tail` follow, `replay --watch`, stream-json |
| Deliverable | `query/tail.py`; `core/follower.py` (new; watchdog-based); `replay --watch` flag |
| Verification | (1) Mock-append to an in-progress events.jsonl and confirm the test sees the follow  (2) `--polling` fallback works with watchdog OFF  (3) Each stream-json line matches the `aot/<command>/v1` schema |
| Dependencies | D-2 |
| Schema impact | None |

## 9.5 D-5: `aot tui`

| Item | Content |
|---|---|
| Goal | Side-channel TUI per §5 spec |
| Deliverable | `tui/` package (new); optional dependency `[tui]`; launch entry `aot tui`; each mode (timeline / why / trace / bisect / note / find / grep / overlay) |
| Verification | (1) Manual verify of all key bindings (macOS / Linux)  (2) Live follow works through the D-4 follower  (3) Navigation does not lag (< 100ms) on huge sessions (10000+ events)  (4) Error UX when optional deps are not installed |
| Dependencies | D-3, D-4 |
| Schema impact | None |

## 9.6 D-6: Bridges

| Item | Content |
|---|---|
| Goal | engine-log overlay, OTel sidecar, cross-session index |
| Deliverable | `bridges/engine_log.py`; `bridges/otel_export.py`; `core/global_index.py`; `query/review.py` |
| Verification | (1) Assert all bridges default off  (2) engine-log auto-detect honors `CLAUDE_CODE_DEBUG_LOGS_DIR`  (3) Smoke OTel export via `console` exporter; verify prompt redaction defaults to ON  (4) Build cross-session index across 30 sessions; `review` completes within 1s |
| Dependencies | D-2, D-3 |
| Schema impact | global_index.json |

## 9.7 D-7: Safe-share Export

| Item | Content |
|---|---|
| Goal | `export --safe-share`, JSON Schema emission |
| Deliverable | `query/export.py`; `core/sanitiser.py`; `schemas/` directory |
| Verification | (1) Snapshot test verifying path / cwd / tool_response do not remain in the export  (2) Round-trip across the 3 formats markdown / json / archive  (3) Excerpt length control via `--keep-excerpt N` |
| Dependencies | D-2 |
| Schema impact | None |

---

# 10. Non-goals (line in the sand; explicitly not done in Phase D)

| Item | Reason |
|---|---|
| Automatic anomaly notification / proactive alert | §1.1 user-driven; §DESIGN.md §0.5 proxy problem |
| Session resume / fork (restoration of a live conversation) | Engine's responsibility; AOT is post-hoc forensic |
| Intervention against the agent (deny / approve / modify) | §1.1 observation-only |
| Built-in OTel collector | Bridges are one-way; sidecar exporter only |
| Automatic fixes / refactor suggestions / LLM-based summarisation | The recorder is not an advisor |
| Writes to host repo / `<repo>/tasks/` / `<repo>/.claude/` | §1.1 host repo non-contamination |
| Auto cross-indexing of all sessions | Proactive behavior is forbidden; only on user-explicit `review` |
| Web UI dashboard | CLI + TUI + OTel are sufficient; maintenance cost too high |
| Move events.jsonl to SQLite | Maintain per-session JSONL simplicity; ensure speed via the index |
| Automatic weighting of anomaly scores | Proxy-on-proxy worsens false rates; stop at vocabularization |
| Plugin auto-update | Delegated to the host mechanism |
| AOT-internal aggregation of tokens / cost (range unobtainable via the hook route) | Delegated to the organizational audit side via OTel sidecar; AOT displays only what it can obtain |

---

# 11. Unverified items (require primary-source verification before implementation)

| # | Item | Design areas affected | Verification method | Fallback if verification fails |
|---|---|---|---|---|
| V1 | `textual` compatibility with Python 3.9 | §5.5 TUI dep selection | PyPI `python_requires` / official docs + real-machine import (mandatory before starting D-5) | Switch to `urwid` or stdlib `curses`; restrict `[tui]` extras to Python 3.10+ |
| V2 | events.jsonl append latency via fsevents / inotify | §5.4 file watch strategy | Real-machine measurement on macOS / Linux (at D-5 start) | If > 100ms, change default to polling 500ms; default to watchdog OFF flag |
| V3 | Whether token usage appears in CC `Stop` event payload | §6.2 `tokens` field; §7.5 stats | Confirm via real-machine dump (OBSERVATIONS.md 2026-05-15 confirms `last_assistant_message`; `usage` unconfirmed) | Delegate tokens to the organizational audit side only via OTel sidecar; omit from AOT internals |
| V4 | Whether the CC hook payload carries a `parent_session_id`-equivalent field (subagent / Task related) | §6.2 `parent_session_id`; subagent lineage restoration | Real-machine dump of hook events on CC `Agent` tool launch | Abandon subagent lineage restoration; treat as independent sessions |
| V5 | Whether Codex's `~/.codex/sessions/` can be watched as an AOT plugin | §5.7 Codex support for `aot tui` (after Phase C completion) | Real-machine verify in Codex dev mode | For Codex, support only via `tail` / CLI for now; TUI is CC-only |
| V6 | Race condition when readers read events.jsonl during append | §5.4 file watch | Real-machine measurement; `fcntl.flock` or partial-line skip on the reader side | On the reader side, skip if the last line is not newline-terminated; re-read on the next watch event |
| V7 | Quality of the `watchdog` package's Windows support | §5.4 cross-platform | Official docs + real machine | Windows is polling-only; `aot tui` Windows support is best-effort |

---

# 12. Risks and migration

| Risk | Level | Mitigation |
|---|---|---|
| v1 sessions break under Schema v2 | High | Dual-support reader; `v`-missing fallback; mandatory snapshot tests in D-2 |
| `bisect` conclusions later turn out to be wrong | Medium | Findings are append-only; no overwrites; preserve re-bisect history |
| CC debug log location changes for `--overlay engine-log` | Medium | Honor `CLAUDE_CODE_DEBUG_LOGS_DIR` env; skip + warn if not found |
| Sensitive-info leakage via OTel sidecar export | High | Default `log_user_prompt = false` / `log_raw_tool_response = false`; apply the strengthened redaction on every export; dry-run export contents via `aot doctor` |
| `aot review`'s cross-session index bloats | Medium | 30-day retention; manual `aot purge`; `doctor --fix` suggestions |
| `note` / `findings` bleed into the host repo | Low | All files confined to `${CLAUDE_PLUGIN_DATA}/sessions/<id>/`; host writes made technically impossible |
| Friction installing TUI optional deps | Medium | The error at `aot tui` launch presents the `pip install` command; `aot doctor` displays TUI dep status |
| Unstable behavior from OS differences in watchdog | Medium | `--polling` always forces polling; TUI ships with a built-in polling fallback |
| Existing hook's post_tool processing time grows in D-2 (SHA256 computation) | Medium | For tool_response over 100KB, defer SHA computation to the back-end indexer (hook finalizes only size; SHA is computed at index build time) |

---

# 13. Open Questions (decision log)

Phase D Open Questions were **all 6 resolved on 2026-05-15** (see §14 revision history for details).

| # | Conclusion | Reflected in |
|---|---|---|
| OQ1 | TUI dep is `textual` as first choice. Verify Python 3.9 compatibility on a real machine before starting D-5; switch to `urwid` if not viable | §5.5 / §11 V1 |
| OQ2 | `bisect --predicate` non-interactive mode is not implemented in D-3; decide from Phase E onward based on real demand | §7.2.2 |
| OQ3 | OTel sidecar is batch-only in D-6; streaming is a Phase E candidate (to defend the hook perf budget) | §8.3.2 |
| OQ4 | Add `empty-glob` / `stale-cache` / `silent-failure` / `abandoned-write` to `find`'s default vocabulary | §7.4.1 |
| OQ5 | Default global_index retention 30 days; configurable via `config.toml` | §6.5 / §8.4 |
| OQ6 | Ship no slash commands at all (including `/aot-note`). `aot tui` is the sole non-interrupting UI | §8 (former §8.4 removed) / §11 (V1 removed) |

If new Open Questions arise, append them to this section.

---

# 14. Revision history

| Date | Content | Author |
|---|---|---|
| 2026-05-15 | Initial draft. Phase D design pinned down from the conversation log (review → power-up → non-interrupting correction → wireframe) | Claude (claude-opus-4-7, 1M context) |
| 2026-05-15 | All 6 of OQ1-OQ6 resolved (all user recommendations adopted). OQ1 textual / OQ2 bisect predicate deferred / OQ3 OTel batch-only / OQ4 4 find vocabulary additions / OQ5 retention 30 days / OQ6 all slash commands removed. Consistency updates to §1.3 / §2 / §7.4 / §8 (former §8.4 removed; §8.5 → §8.4 renumbered) / §11 (V1 removed; V2-V8 → V1-V7 renumbered) / §12 (slash-conflict row removed) / §13 (turned into decision log) | Claude |
