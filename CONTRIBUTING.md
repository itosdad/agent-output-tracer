# Contributing

Thanks for considering a contribution. This is a small, intentionally
focused tool — bug reports, regression fixes, and small targeted
improvements are the most welcome categories.

## Before you start

- **Read [`docs/DESIGN.md`](docs/DESIGN.md)** for the project's goals and
  non-goals. Most "should we do X?" questions are answered there.
- For Phase D and beyond, [`docs/DESIGN_FORENSIC_UX.md`](docs/DESIGN_FORENSIC_UX.md)
  is the source of truth.
- **Open an issue first** for anything larger than a small bug fix or
  docs nit. It saves both sides from re-doing work after a divergent
  implementation.

## Scope guardrails

This plugin is deliberately:

- **issue-agnostic** — it does not classify "hallucination" vs "context
  rot" vs "wrong tool". It records and lets humans investigate.
- **user-driven** — no proactive alerts, no agent injection, no
  background daemons.
- **observation-only** — every hook exits 0 unconditionally; the agent
  must never be blocked.
- **engine-agnostic at the core** — Claude Code / Codex CLI both
  flow through the same normalized event schema.

Proposals that violate any of those will probably be declined. See
[`docs/DESIGN.md`](docs/DESIGN.md) §2 for the formal version.

## Dev setup

```bash
git clone https://github.com/itosdad/agent-output-tracer
cd agent-output-tracer
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# optional, for working on `aot tui`:
pip install -e ".[dev,tui]"
```

## Running the tests

```bash
pytest                  # full suite
pytest tests/unit       # unit only (fastest)
pytest -k schema_v2     # by name
```

417 tests pass on Python 3.13. The hook runtime is verified under
Python 3.9 (the version `python3` resolves to on a stock macOS).

## Style

```bash
ruff check .            # lint
ruff format .           # format (if you want to reformat)
```

Per-file ignores in `pyproject.toml` keep `hooks/`, `adapters/`, and
`core/` 3.9-compatible. Don't add 3.10+ syntax (`X | Y`, `match`)
to those trees; the CLI surface in `cli/` and `query/` is 3.11+ and
free to use modern syntax.

## Commit style

- Short imperative subject line, prefix with a scope when useful:
  `fix(redactor): ...`, `docs(install): ...`, `feat(query): ...`.
- One concern per commit. Refactors and features in separate commits.
- Reference related issues with `#NN` in the body.

## Submitting a PR

1. Fork → branch off `main` → make changes
2. Tests + lint must pass locally
3. Open the PR with a short summary + motivation
4. CI will run `test.yml` + `lint.yml` automatically
5. Releases are tag-driven (`vX.Y.Z`); contributors don't need to bump
   versions

## What gets recorded by this project itself

This repo's `LICENSE` is MIT. Contributions are accepted under the same
license. No CLA.
