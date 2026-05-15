# agent-output-tracer

> Universal AI agent session forensic debugger. Replay, trace, and query
> agent behavior when output looks wrong.

`agent-output-tracer` is a Claude Code / Codex plugin that **records every
session completely** via hooks. When you notice that an agent's output looks
off, you can **replay, trace, and query** the session to reconstruct exactly
what happened — what files were read, in what order, in response to which user
prompts.

The plugin is **issue-agnostic** (it doesn't try to classify "hallucination" vs
"context rot" vs "wrong tool") and **user-driven** (no proactive alerts; you
decide when something needs investigation).

## Status

**v0.2.0** — Phase A capture pipeline + Phase B-2..B-5 forensic query
suite. Headline commands `replay`, `list`, `latest`, `grep`, `state-at`,
`trace`, `why`, `diff`, `mentioned-but-not-read` all ship. Codex support
and remaining Phase B items (`causal-graph`, anomaly hints, etc.) land
later.

246 tests pass on macOS / Python 3.13; hook runtime verified under
`/usr/bin/python3` (Python 3.9) so it works on every Mac.

See [`docs/DESIGN.md`](docs/DESIGN.md) for the full design and
[`CHANGELOG.md`](CHANGELOG.md) for what's landed.

## Quick example

```bash
# Replay the latest session as a timeline
$ agent-output-tracer replay --session latest
Session: demo
Started: 2026-05-15T10:10:49.411+09:00
Cwd:     /proj
Events:  5
Counts:  tools=1 user_prompts=1 agent_responses=1 unique_reads=1 (23 B)

[10:10:49] [user] Hi please read foo.md
[10:10:49] [tool] Read /proj/foo.md
[10:10:49]   ↳ result: 23 B
[10:10:49] [agent] (end_turn) foo.md contains hello world
[10:10:49] [session_end]

# List captured sessions
$ agent-output-tracer list --last 5

# Print the most recent session's id (useful for scripting)
$ agent-output-tracer latest

# Full-text regex across every string field in the session
$ agent-output-tracer grep --session latest --pattern "DI container" -i

# Snapshot of state at time T (lets you see context as it grew)
$ agent-output-tracer state-at --session latest --time 10:23:45
```

The headline `replay` view stitches together user prompts, tool calls, byte
counts, and agent responses in chronological order. It's the fastest way to
notice things like "this file was read 3 times" or "the agent touched a file
I never mentioned."

## Install

See [`docs/INSTALL.md`](docs/INSTALL.md) for Claude Code + Codex install
steps, the verify procedure (`_install_verify.jsonl` lands on the first
hook fire so you can confirm wiring before relying on it), and troubleshooting.

## What gets recorded

For every session:

- `events.jsonl` — one JSON line per event (user prompt / tool call
  pre+post / agent response / session end).
- `metadata.json` — running counters (tool calls, unique files read,
  total bytes, ts_start/ts_end, etc.).

Default secret patterns (OpenAI/Anthropic API keys, GitHub PATs, AWS keys,
JWT, common `password=`/`token=` shapes) are masked before write. Hook
exceptions are swallowed; the agent is never blocked by an
observation-only plugin.

## Design

See [`docs/DESIGN.md`](docs/DESIGN.md) for goals, non-goals, hook contract,
schema, CLI surface, safety, and limits.

## License

MIT — see [`LICENSE`](LICENSE).
