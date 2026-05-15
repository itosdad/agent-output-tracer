# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
