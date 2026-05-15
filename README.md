# agent-output-tracer

> Universal AI agent session forensic debugger. Replay, trace, and query agent
> behavior when output looks wrong.

`agent-output-tracer` is a Claude Code / Codex plugin that **records every
session completely** via hooks. When you notice that an agent's output looks
off, you can **replay, trace, and query** the session to reconstruct exactly
what happened — what files were read, in what order, in response to which user
prompts.

The plugin is **issue-agnostic** (it doesn't try to classify "hallucination" vs
"context rot" vs "wrong tool") and **user-driven** (no proactive alerts; you
decide when something needs investigation).

## Status

Phase A — in active development. See [`docs/DESIGN.md`](docs/DESIGN.md) for the
full design and [`CHANGELOG.md`](CHANGELOG.md) for what's landed.

## Quick example

```bash
# Replay the latest session as a timeline
$ agent-output-tracer replay --session latest

# Find the first time a phrase appeared in agent output and trace it back
$ agent-output-tracer trace --session latest --output "DI container"

# Show user prompts vs agent file accesses
$ agent-output-tracer diff --session latest

# Search the session full-text
$ agent-output-tracer grep --session latest --pattern "FooBar"
```

## Install

See [`docs/INSTALL.md`](docs/INSTALL.md).

## Design

See [`docs/DESIGN.md`](docs/DESIGN.md) for goals, non-goals, hook contract,
schema, CLI surface, safety, and limits.

## License

MIT — see [`LICENSE`](LICENSE).
