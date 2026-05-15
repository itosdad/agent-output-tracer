# agent-output-tracer

> Universal AI agent session forensic debugger. Replay, trace, and query
> agent behavior when output looks wrong.

A **Claude Code / Codex CLI plugin** that records every session via hooks.
When an agent's output looks off — wrong file touched, fact you never
mentioned, conclusion that doesn't match what was read — you replay the
session and walk back through exactly what happened, in chronological order,
with byte counts and tool inputs intact.

The plugin is **issue-agnostic** (it doesn't try to classify "hallucination"
vs "context rot" vs "wrong tool") and **user-driven** (no proactive alerts;
you decide when something needs investigation). Hooks are observation-only
— the agent is never blocked.

**Current: v0.6.0** — Phase A (capture) + Phase B (forensic query
suite) + Phase C (Codex CLI support) + Phase D-1..D-7 (UX foundation,
schema v2, causal core: `find` / `bisect` / `note` / `stats` / inverse
trace, live `tail` + `replay --watch`, side-channel `aot tui`, opt-in
bridges incl. OTel, safe-share `aot export`). 417 tests pass on Python
3.13; hook runtime still verified under Python 3.9. See
[`CHANGELOG.md`](CHANGELOG.md).

---

## Quick install

**Claude Code** — in a session, run:

```
/plugin marketplace add itosdad/agent-output-tracer
/plugin install agent-output-tracer@itosdad-agent-output-tracer
```

**Codex CLI** (≥ 0.128) — enable `codex_hooks = true` in
`~/.codex/config.toml`, then `codex plugin marketplace add itosdad/agent-output-tracer`.

**CLI binary** (needed only for `aot replay` / `aot grep` etc.):

```bash
pipx install git+https://github.com/itosdad/agent-output-tracer.git@v0.6.0

# Optional side-channel TUI:
pipx install 'git+https://github.com/itosdad/agent-output-tracer.git@v0.6.0#egg=agent-output-tracer[tui]'
```

Installs both `agent-output-tracer` and the short `aot` alias.

Full setup — dev mode, verify procedure, troubleshooting, version
requirements, Codex caveats — lives in [`docs/INSTALL.md`](docs/INSTALL.md).

---

## Daily usage

### Find a session

```bash
aot list --last 10            # 10 most recent sessions, newest first
aot latest                    # just the most-recent session id
```

### Replay it

```bash
aot replay --session latest             # full timeline
aot replay --session latest --show-hints   # + anomaly hints (B-8)
aot replay --session a3f2 --format json    # JSON for scripts
```

Session specs accept the full UUID, any unique ≥ 4-char prefix, `latest`,
`latest-N`, or `YYYY-MM-DD`.

### Investigate a specific output

```bash
# "Where did the agent get this phrase from?" — walks back from the first
# agent_response containing PHRASE, classifies each prior Read by whether
# its tool_response contains the phrase. Exit 3 if it's a hallucination
# candidate (no Read and no user prompt explains it).
aot trace --session latest --output "PHRASE"

# "Why did this event fire?" — surfaces the 3 events before, the most-
# recent user_prompt, and any Glob whose result contained this path.
aot why --session latest --path /proj/foo.md

# Session-level hallucination scan: paths the agent mentioned that no
# user prompt nor tool_response introduced.
aot mentioned-but-not-read --session latest

# Asymmetric user-vs-agent diff: paths the user asked for vs paths the
# agent actually touched (basename-aware).
aot diff --session latest
```

### Other forensic verbs

```bash
aot grep --session latest --pattern "regex" -i      # full-text search
aot state-at --session latest --time 10:23:45        # state at moment T
aot causal-graph --session latest                    # mermaid causal graph
aot export-trace --session latest --output report.md # all-in-one forensic report
aot stats --session latest                           # session-level counters
aot find repeated-reads --session latest             # anomaly vocab (10 patterns)
aot find unmentioned-reads --session latest --threshold 1
```

### Live tail + side-channel TUI

```bash
aot tail --session latest                            # follow events.jsonl
aot tail --session latest --format stream-json       # JSON-Lines pipe
aot replay --session latest --watch                  # replay then keep following

# Side-channel TUI (requires `pip install 'agent-output-tracer[tui]'`)
aot tui                                              # opens against `latest`
aot tui --session a3f2
```

### Bisect / notes / cross-session review

```bash
aot bisect start --session latest                    # binary search
aot bisect good       # mark candidate as "before-the-break"
aot bisect bad        # mark candidate as "after-the-break"
aot bisect status

aot note add --session latest --tag root-cause "wrong glob pattern"
aot note list --session latest

aot review --since 2026-05-01                        # opt-in cross-session summary
```

### Safe-share export (PII / cwd / response bodies stripped)

```bash
aot export --session latest --format markdown        # to stdout
aot export --session latest --format json --output redacted.json
aot export --session latest --format archive --output bundle.zip
```

### Maintenance

```bash
aot doctor               # runtime / data dir / hook wiring self-check
aot config list          # show every CLI default + its source
aot config set defaults.color never
aot gc --dry-run         # show what retention policy would prune
aot gc                   # apply: strip content >30d, delete dirs >365d
```

---

## What gets recorded

Per session, in `${CLAUDE_PLUGIN_DATA}/sessions/<session_id>/`:

| file | content |
|---|---|
| `events.jsonl` | One JSON line per event — `user_prompt` / `pre_tool` / `post_tool` / `agent_response` / `session_end` (+ Codex `session_start` / `compact_pre` / `compact_post`) |
| `metadata.json` | Running counters: tool calls, unique files read, total bytes, `ts_start` / `ts_end`, etc. Rewritten on every appended event |

Default secret patterns (OpenAI / Anthropic API keys, GitHub PATs, AWS
access keys, JWT, common `password=` / `token=` / `secret=` shapes) are
masked before write. Hook exceptions are swallowed; the agent is never
blocked by an observation-only plugin (DESIGN §9.1).

Events from both engines normalize to the same schema, so the same `aot`
query commands work regardless of which engine produced the session.

---

## How it's safe to leave on

| Concern | How the plugin handles it |
|---|---|
| Hooks could block the agent | Every hook exits 0 unconditionally. JSON parse errors, recorder failures, redactor crashes — all swallowed |
| Host repo could get polluted | Writes only to `${CLAUDE_PLUGIN_DATA}` (per engine). Never touches `<repo>/.claude/` or `<repo>/tasks/` |
| Secrets could leak into events.jsonl | `core/redactor.py` masks 7 common formats by default. Custom patterns via config (D-2+) |
| Disk could grow forever | `aot gc` strips content fields after 30 days, deletes session dirs after 365 days (configurable). Run from cron or just on demand |
| Old sessions could break a new reader | events.jsonl is append-only and versioned (`v` field). Future schema additions stay forward/backward compatible |

---

## Phase status

| Phase | Scope | Status |
|---|---|---|
| **A** | Capture pipeline (5 hooks → adapter → recorder), redaction, `replay` / `list` / `latest` / `grep` / `state-at` | ✅ v0.1.0 |
| **B** | `trace` / `why` / `diff` / `mentioned-but-not-read` / `causal-graph` / `export-trace` / anomaly hints / `gc` | ✅ v0.3.0 |
| **C** | Codex CLI support (`adapters/codex.py`, dual-engine hooks, install docs) | ✅ v0.4.0 |
| **D-1** | UX foundation (`aot` alias, color, 3-line errors, `doctor`, `config`) | ✅ v0.5.0 |
| **D-2** | Schema v2 (correlation_id, sha256, tokens, hook_self_ms, v1↔v2 readers) | ✅ v0.6.0 |
| **D-3** | Causal Core (`find` vocab, `trace --missing` / `--by-sha`, `bisect`, `note`, `stats`) | ✅ v0.6.0 |
| **D-4** | Live UX (`tail` follower, `replay --watch`, `stream-json`) | ✅ v0.6.0 |
| **D-5** | Side-channel `aot tui` (optional `[tui]` extra) | ✅ v0.6.0 |
| **D-6** | Bridges (engine-log overlay, OTel sidecar span model, cross-session `review`) | ✅ v0.6.0 |
| **D-7** | Safe-share `aot export` (markdown / json / archive, sanitised) | ✅ v0.6.0 |

Phase B-1 (per-session search index for faster grep) is deferred until
grep actually feels slow on real data.

---

## Design

[`docs/DESIGN.md`](docs/DESIGN.md) — goals, non-goals, hook contract,
event schema, CLI surface, safety guarantees, version constraints.

[`docs/DESIGN_FORENSIC_UX.md`](docs/DESIGN_FORENSIC_UX.md) — Phase D
roadmap (TUI, bisect, content-address, OTel sidecar).

[`CHANGELOG.md`](CHANGELOG.md) — per-version diff.

## License

MIT — see [`LICENSE`](LICENSE).
