---
title: agent-output-tracer — AI Agent Session Forensic Debugger (design version)
plugin_name: agent-output-tracer
target_repo: ~/work/agent-output-tracer/
intended_engines:
  - Claude Code (official plugin mechanism → primary implementation)
  - Codex CLI (compatible implementation, supported in Phase C)
distribution_model: standalone plugin package (installed into a host repo but with no dependency on the host repo's structure — a generic plugin)
date: 2026-05-14
author: Claude (claude-opus-4-7, 1M context)
status: design draft (pre-implementation, written at a granularity that can be handed off to another session)
primary_sources:
  - Claude Code Hooks official docs: https://code.claude.com/docs/en/hooks.md
  - Claude Code Plugins official docs: https://code.claude.com/docs/en/plugins.md
  - Claude Code Plugins Reference: https://code.claude.com/docs/en/plugins-reference.md
  - Claude Code Settings: https://code.claude.com/docs/en/settings.md
verification_dates:
  - Claude Code plugin / hooks spec: 2026-05-14 (via claude-code-guide subagent)
  - Codex hook event structure: 2026-05-14 (empirically measured against the host repo's existing implementation)
  - Codex official hooks docs verify: 2026-05-14 to 2026-05-15 (via general-purpose subagent, OpenAI official docs `developers.openai.com/codex/hooks` + generated schemas)
handoff_notes:
  - This doc is intended to be readable standalone at a granularity that lets you start implementation
  - When another session / another agent picks this up, read §13 limitations + §11 implementation plan first
  - Primary features are in §8 CLI command list. For implementation, start from §7 architecture and §6 config
  - For the background and history of design decisions, see §0.5 (design rationale) and §Revision history
---

# ⚠ Historical baseline — Phase A–C design draft (2026-05-14)

This document is the **pre-implementation design** of the recorder
pipeline, hook contract, event schema, and CLI surface for Phase A–C.
It is preserved as the historical record of how the project was
scoped before code was written.

For the **current state**, refer to:

- [`README.md`](../README.md) — overview, screenshots, status table
- [`docs/TUI.md`](TUI.md) — TUI guide (the primary surface)
- [`CHANGELOG.md`](../CHANGELOG.md) — per-version diff

Implementation has evolved beyond this draft. Specifically:

- The engine detector (`hooks/_runner.py`) no longer keys off
  `permission_mode` — see CHANGELOG v0.16.1 / OBSERVATIONS for why.
- Timeline theme reads engine from events, not metadata — v0.16.2.
- Phase D shipped in full plus TUI Phase 1–4.A on top — see status
  table in README.

This document is not deleted because the §0.5 design rationale,
§1.2 non-goals, §2 design principles, and §9 safety guarantees are
still load-bearing for anyone reviewing PRs or contributing.

---

# 0. Executive Summary

## 0.1 In one sentence

**`agent-output-tracer`** is an **issue-agnostic forensic debugger plugin** that fully records sessions of AI agents (Claude Code / Codex, etc.) so that when the user notices something off in the agent's output, they can replay / query to trace **what happened, when, in what order, and which inputs the agent's output was derived from**.

## 0.2 Why it is needed

AI agents sometimes produce wrong outputs. The causes are varied:

- Missing or over-reading a file
- Cross-namespace bleed
- Mis-judgment influenced by past routing history
- Context Rot (degradation of attention state)
- Wrong choice of skill / tool
- Misunderstanding the user's instructions
- Hallucination (information in the output with no source)

If there is a **mechanism to trace what happened the moment the user notices something off**, there is no need to classify the cause type in advance. This plugin provides a forensic answer to the user's **"this looks wrong, why?"**.

## 0.3 Main features (preview)

```bash
# Replay the timeline of the most recent session
$ agent-output-tracer replay --session latest

# Reverse-lookup from a suspicious portion of the output
$ agent-output-tracer trace --session abc123 --output "uses a DI container..."
# → Identifies the event where the word "DI container" first appeared
# → Displays the files / user prompts the agent read prior to that
# → Identifies the event where the word "DI container" first appeared
# → Displays the files / user prompts the agent read prior to that

# Query the reason for a specific tool invocation
$ agent-output-tracer why --session abc123 --event "Read(file_X) at 10:23:45"
# → Displays the immediately preceding user prompt / agent reasoning

# Diff between user instructions and agent actions
$ agent-output-tracer diff --session abc123
# → Highlights actions the user did not instruct

# Full-text search within a session
$ agent-output-tracer grep --session abc123 --pattern "file X"

# Export a causal graph
$ agent-output-tracer causal-graph --session abc123 --output ./graph.md
```

## 0.4 Design characteristics

1. **Issue-agnostic**: Does not classify the kind of anomaly (hallucination / rot / wrong tool / etc.) in advance. Only provides **reconstruction of the factual trail**.
2. **User-driven**: The plugin does not proactively declare "rot is happening". The user notices something off and issues a query.
3. **Mechanical record**: Fully records sessions via hooks, without depending on agent compliance.
4. **Read-only forensic**: Does not interfere with agent behavior — observation only.
5. **No host repo contamination**: Contained to the plugin data dir, does not modify the host repo at all.
6. **Engine-agnostic core**: Claude Code is the primary axis, Codex is compatible.

## 0.5 Design rationale (why this design)

The decision to put this plugin's main feature at **"forensics / debug"** rather than **"automatic detection"** was made by comparison against rejected alternatives.

| Aspect | Rejected alternative (pattern auto-detection plugin) | This doc's design (forensic debugger) |
|---|---|---|
| Main feature | Auto-detect rot via detection patterns | Full session recording + arbitrary query for cause tracing |
| Detection actor | Plugin judges via proxy | User notices the anomaly, plugin provides forensic data |
| Issue scope | Limited to Context Rot | Any agent malfunction (rot / hallucination / wrong tool / etc.) |
| Philosophical basis | Proxy detection of rot | Rot cannot be directly detected from internal state; being a forensic recorder is more honest |
| Pattern detection (P-X series) | Main feature | **Subsidiary feature in the appendix** (shown as anomaly hint during replay) |

Reason for rejection: **the proxy problem**. Pattern auto-detection observes "proxies of rot symptoms (e.g., repeated reads of the same file)", but proxy ≠ rot itself (rot is the LLM's internal attention state). Proxies alone cannot avoid false positives / false negatives, and we cannot claim "we can detect it accurately". This plugin converges on a design that splits roles into **"user as anomaly detector + plugin as forensic recorder"**, accepting the limits of proxies and providing a certain value (reconstruction of the factual trail).

## 0.6 Image of the finished form (from the user's perspective)

```
[Day 1] $ claude plugin install ~/work/agent-output-tracer
✓ Installed agent-output-tracer v0.1.0

[Day 1 - Day N] User uses the agent in the host repo
  → The plugin records sessions fully in the background (user is not aware)

[Day N+1] User: "Something felt off about the agent's output this morning..."
  $ agent-output-tracer replay --session 2026-05-15-am1
  
  [09:30:00] [user] "Implement a FooBar component"
  [09:30:02] [agent] thinking...
  [09:30:03] [tool: Read] CLAUDE.md (12KB)
  [09:30:05] [tool: Glob] "src/**/*.tsx" → 23 files
  [09:30:08] [tool: Read] src/lib/di.ts (3KB)  ← ⚠️ file the user did not instruct
  [09:30:12] [agent response] "I will create FooBar.tsx using a DI container..."
  
  → User: "Ah, it pulled DI in on its own. Let me trace this."
  
  $ agent-output-tracer trace --session 2026-05-15-am1 \
    --output "DI container"
  
  Output mentions "DI" first at 09:30:12
  Causal trail:
    - user prompt at 09:30:00: "Implement a FooBar component" (no DI mention)
    - read CLAUDE.md at 09:30:03: ✗ no "DI" in content
    - read di.ts at 09:30:08: ✓ first source of "DI"
  
  Why was di.ts read?
    Glob "src/**/*.tsx" returned di.ts as result #14
    Agent picked it (reason not visible in hook data)
  
  Hypothesis: agent read di.ts speculatively after Glob, then 
              incorporated into design decision
  
  → User: "I see, it read an extraneous file from the Glob results.
           I'll write 'do not use DI' in CLAUDE.md, or make it explicit in the agent prompt."
```

This is the plugin's essential value. The user can **"look at the factual trail and judge for themselves"**. The plugin does not judge.

---

# 1. Plugin purpose and non-purposes

## 1.1 Purpose (Why this exists)

Provide a mechanism so that when a user feels something is off about agent output, they can reconstruct what happened **without further dialogue with the agent**, **using only the session data recorded by hooks**.

Specifically:

| User's question | Answer the plugin provides |
|---|---|
| "Why did the agent read this file?" | Shows the event where the file was read, the immediately preceding user prompt / agent action, and whether the file was a Glob result or an explicit reference |
| "When did the agent see this information?" | Event timestamp and source file of the tool result containing the given string |
| "Is the agent doing something different from the user's instructions?" | Side-by-side of user prompts and agent actions, highlighting access to things the user never mentioned |
| "Where in the session did behavior go wrong?" | Overall view of the session timeline, replay for the user to identify the suspicious point |
| "Where is the basis file for this output?" | Source of the string in the output (whether it exists inside a read file, or whether it's a possible hallucination) |

## 1.2 Non-purposes (Out of scope)

| Non-purpose | Reason |
|---|---|
| Automatic classification of the anomaly type | Once the user notices the anomaly that is sufficient; classification is the user's judgment |
| Auto-detection of specific issues like Context Rot | Proxy detection is inaccurate (see §0.5 rationale). Pattern detection is demoted to a subsidiary **anomaly hint** |
| Judging correctness of agent output | "Correctness" is undecidable from hook data alone; defer to human judgment |
| Block / modify agent behavior | Read-only forensic recorder. No intervention |
| Writing to the host repo | Contained to the plugin data dir |
| Observation of LLM internal state | Hooks only obtain external events; attention state etc. are invisible |
| Cross-session long-term behavior analysis | Focused on within-session forensics; long-term analysis is for external tools |
| Auto-correction / recommendation | A recorder, not an advisor |

## 1.3 Intended users

| User type | Use scenario |
|---|---|
| Developer | Agent behaves unexpectedly → debug |
| AI safety researcher | Empirical observation of agent behavior |
| Product team | Root-cause investigation of quality issues in agent-powered features |
| OS / multi-skill repo operators | Tracking agent behavior across mixed projects |
| Audit / compliance | Tracing the basis of agent output (regulatory requirement) |

## 1.4 What is this plugin's strength

This plugin's strength is **not** "we can detect Context Rot accurately". The fundamental limit of proxy detection makes that impossible in principle (see §0.5 rationale). The plugin's strength is **"the moment the user feels something is off, the entire session can be mechanically replayed / queried at zero added cost"**.

That is:

- **Human = anomaly detector** (human judgment is more accurate than any proxy)
- **Plugin = forensic recorder + query interface** (mechanically retrieves what the human wants to know)

This is the role split. It avoids the proxy problem of pattern auto-detection (rot symptoms ≠ rot) and is a design that leverages the user's judgment.

---

# 2. Design principles

## 2.1 Issue-agnostic (no kind-classification)

| Principle | Implementation |
|---|---|
| Do not classify the anomaly in advance | The plugin does not put a "hallucination detector" or "rot detector" as a main feature |
| Record all events uniformly | Tool calls, user prompts, agent responses are all stored in the same schema |
| Queries match the user's vocabulary | Natural-language-style queries like "Why was this file read?" "When did it see this info?" are exposed in the CLI |

## 2.2 User-driven (operates on user trigger)

| Principle | Implementation |
|---|---|
| No proactive notification from the plugin | Live alerts off by default. The plugin does not actively say "rot is happening" |
| Analyze only at user query time | Hooks only record; analysis is initiated by the user via the CLI |
| Provide a session list dashboard | `list` / `latest` commands to help the user find a session |

## 2.3 Mechanical (no dependency on agent compliance)

| Principle | Implementation |
|---|---|
| Do not rely on markers the agent emits | Self-contained using only events available from hooks |
| Capture all tool calls | Matcher covers all tools (`Read|Glob|Grep|Edit|Write|MultiEdit|Bash`) |
| Plugin stamps the timestamp | Does not depend on agent self-reporting |

## 2.4 Safe by default

| Principle | Implementation |
|---|---|
| Exception-tolerant | try/except in every hook; never block agent behavior |
| Read-only on observe | Only reads `tool_input` / `tool_response`, no modification |
| No host repo contamination | Data write target is only under `${CLAUDE_PLUGIN_DATA}` |
| Performance budget | PreToolUse < 10ms, PostToolUse < 15ms (including content capture) |
| Privacy / redaction | Automatically masks secret patterns (API keys etc.); auto-deletes when retention expires |

## 2.5 Engine-agnostic core

| Principle | Implementation |
|---|---|
| Convert hook events into normalized events | Per-engine adapters (`adapters/claude_code.py`, `adapters/codex.py`) |
| Detection / query operates on normalized events | Isolates engine differences |
| Adding a new engine only requires adding an adapter | Easy support for other future LLM tools |

---

# 3. Supported engines and hook spec

## 3.1 Claude Code (primary, official spec confirmed)

From Claude Code official docs (confirmed 2026-05-14 via claude-code-guide subagent):

### 3.1.1 Fields common to all hook events

> All hooks receive JSON with these fields:
> ```json
> {
>   "session_id": "abc123",
>   "transcript_path": "/path/to/transcript.jsonl",
>   "cwd": "/current/directory",
>   "permission_mode": "default|plan|acceptEdits|auto|dontAsk|bypassPermissions",
>   "hook_event_name": "EventName"
> }
> ```

### 3.1.2 The 5 hook types we adopt

For full forensic capture we adopt the following:

| hook | Role | What is captured |
|---|---|---|
| **`UserPromptSubmit`** | On user input | Full user prompt + timestamp |
| **`PreToolUse`** | Before tool invocation | tool_name + full tool_input + timestamp |
| **`PostToolUse`** | After tool success | tool_response + timestamp |
| **`Stop`** | On agent response completion | response_text + stop_reason |
| **`SessionEnd`** | On session end | Finalize session stats + trigger GC |

### 3.1.3 Hooks we do not adopt, and why

- `SessionStart`: The first event is treated as the session start (no independent hook needed)
- `StopFailure` / `PostToolUseFailure`: Error-class events are handled in a different phase
- `PermissionRequest`: Not observed (permission itself is a separate mechanism)

### 3.1.4 Hook control flow

All hooks return **exit 0 + empty stdout** (observation only, no blocking). On exception too, silent exit 0.

## 3.2 Codex CLI (official spec confirmed, implementation in Phase C)

### 3.2.1 Official docs (primary sources)

- Official hooks docs: https://developers.openai.com/codex/hooks
- Plugin build docs: https://developers.openai.com/codex/plugins/build
- Changelog: https://developers.openai.com/codex/changelog
- Advanced config (feature flag): https://developers.openai.com/codex/config-advanced
- Generated schemas (ground truth wire format): https://github.com/openai/codex/tree/main/codex-rs/hooks/schema/generated

### 3.2.2 Available hook events (8 official types)

From the official docs:

| Tier | Event name | Trigger timing | Plugin adoption |
|---|---|---|---|
| Session level | `SessionStart` | On session start (source enum: `startup` / `resume` / `clear`) | ◯ (used to detect session switching) |
| **(No session-end hook)** | — | — | Requires design change (see below) |
| Per-turn | `UserPromptSubmit` | On user input | ◎ (full user prompt obtainable) |
| Per-turn | `Stop` | On agent response completion | ◎ (obtains agent response + becomes the session-grouping anchor) |
| Per-tool | `PreToolUse` | Before tool invocation | ◎ (core) |
| Per-tool | `PostToolUse` | After tool completion (Bash / apply_patch / MCP only) | ◎ (with limitations, see below) |
| Per-tool | `PermissionRequest` | On permission request | △ (not adopted, out of observation scope) |
| Compaction | `PreCompact` | Before session compaction starts (0.129+) | △ (potential use in long-session context) |
| Compaction | `PostCompact` | After session compaction (0.129+) | △ (same as above) |

> "`PreToolUse`, `PermissionRequest`, `PostToolUse`, `UserPromptSubmit`, and `Stop` run at turn scope." (official hooks docs)

### 3.2.3 Common event input fields (from the official generated schema)

The input of all 8 events requires the following:

| field | type | content |
|---|---|---|
| `hook_event_name` | string (snake_case, constant) | Identifies each event |
| `session_id` | string | Session identifier (the format is only specified as "string" in the official spec; UUID is not declared) |
| `cwd` | string | Working directory |
| `model` | string | Model name in use |
| `permission_mode` | enum | `default` / `acceptEdits` / `plan` / `dontAsk` / `bypassPermissions` |
| `transcript_path` | string \| null | Session transcript |
| `turn_id` (only the 5 turn-scoped events) | string | Codex-specific extension |

Differences from the empirical observation:

- **The official spec has `hook_event_name` (snake_case) only**. `hookEventName` (camelCase) is used **only on the output side** (`hookSpecificOutput.hookEventName`). **The standalone notation `event` has no official basis** — the `event` branch in defensive code is unnecessary.
- **`tool_input.command` is canonical**; **`tool_input.cmd` has no official basis** — the defensive branch is a remnant of an old PR.

→ The Codex adapter can be implemented assuming only **`hook_event_name` + `tool_input.command`**.

### 3.2.4 PostToolUse limitations

> "`PostToolUse` runs after supported tools produce output, including Bash, `apply_patch`, and MCP tool calls. ... This doesn't intercept all shell calls yet... Similarly, this doesn't intercept `WebSearch` or other non-shell, non-MCP tool calls."

→ **Codex's Read equivalent (the internal non-MCP path) is highly likely not to fire PostToolUse**. On the Codex side, tool_response acquisition is **limited** compared to Claude Code. Design impact: tool result size measurement (Phase B feature) is functionally limited on the Codex side.

### 3.2.5 Absence of SessionEnd — design change

`SessionEnd` does **not** exist in the official generated schema directory or in the event list of the official docs. The session-end trigger cannot be obtained from Codex.

**Implementation policy (Phase C-5 landing point)**:

- Because `core/recorder.append_event` **rewrites `metadata.json` on every event**, `ts_end` / `tool_calls_total` / counters are always current. Even without an explicit session_end event, the latest state of a session is visible the moment the operator runs `replay --session latest`.
- We will not implement an active finalize loop that "synthesizes a pseudo session_end after Stop + N minutes idle". The recorder side is self-healing enough that the maintenance cost of additional code is not justified.
- If needed, downstream can compute idle judgment client-side by observing `metadata.ts_end` (query/state-at already provides this).

### 3.2.6 ask is not supported (matches empirical observation)

> "`permissionDecision: \"allow\"` and `\"ask\"`, legacy `decision: \"approve\"`, ... are parsed but not supported yet, so they fail open."

→ The Codex side is **deny only**. Since this plugin is read-only forensic, neither ask nor deny is used (only exit 0 + empty stdout). This spec doesn't directly affect plugin behavior, but it's a design consideration when running alongside other Codex hooks on the host repo side.

### 3.2.7 Plugin mechanism (official spec)

Codex official plugin mechanism:

```bash
# Marketplace plugin install
$ codex plugin marketplace add owner/repo
$ codex plugin marketplace add owner/repo --ref main
$ codex plugin marketplace add owner/repo --sparse PATH

# Local plugin
$ codex plugin marketplace add ./local-marketplace-root
```

**Plugin structure**:
- `.codex-plugin/plugin.json` manifest (equivalent to Claude Code's `.claude-plugin/plugin.json`)
- `hooks` field points to `./hooks/hooks.json`
- When `hooks` is omitted, `./hooks/hooks.json` is auto-loaded as default

**Plugin install destination**:
- `~/.codex/plugins/cache/$MARKETPLACE_NAME/$PLUGIN_NAME/$VERSION/`
- For a local plugin, `$VERSION` is `"local"`

**Marketplace placement**:
- repo: `$REPO_ROOT/.agents/plugins/marketplace.json`
- personal: `~/.agents/plugins/marketplace.json`
- Claude-compatible: `$REPO_ROOT/.claude-plugin/marketplace.json`

**Feature flag required**:

```toml
# ~/.codex/config.toml or project .codex/config.toml
[features]
codex_hooks = true   # In 0.129+, hooks = true is also acceptable (alias)
```

→ Without this, hooks are **silently ignored**. A required item in the plugin install procedure.

**Trusted project layer constraint**:

> "Project-local hooks load only when the project `.codex/` layer is trusted."

### 3.2.8 Status of Codex native env vars

The **Codex native environment variable** that is the full equivalent of Claude Code's `${CLAUDE_PLUGIN_ROOT}` / `${CLAUDE_PLUGIN_DATA}` **is not explicitly documented in the official docs**. The `openai/codex-plugin-cc` repo uses `${CLAUDE_PLUGIN_ROOT}`, but this comes from the Claude-compatible layer.

**Plugin implementation policy**:
- Use the Codex install path `~/.codex/plugins/cache/$MARKETPLACE_NAME/$PLUGIN_NAME/$VERSION/` directly, or resolve the plugin root via `$HOME` + path computation
- Data storage destination is `data/` under the plugin root, or `~/.codex/plugins/data/`, etc. (needs real-environment verify; finalized in Phase C-1)

### 3.2.9 Version dependencies

- The hook mechanism itself was merged around 0.114
- 0.128: marketplace install / plugin-bundled hooks consolidated
- 0.129: `PreCompact` / `PostCompact` added, `/hooks` TUI added, `hooks` feature flag alias
- 0.130: bundled hooks shown in plugin details

**Plugin's Codex version requirement**:
- Recommended: **>= 0.128** (plugin-bundled hooks support)
- If you also use compaction-related events: **>= 0.129**

### 3.2.10 Diff summary against empirical observation (pre-Phase-C checklist)

| Item | Empirical observation | Official spec | Action |
|---|---|---|---|
| Standalone `event` field notation | 3-way defensive branch | **Does not exist** | Adapter simplifies to assume only `hook_event_name` |
| `tool_input.cmd` | 2-way defensive branch | **Does not exist** | Adapter simplifies to assume only `tool_input.command` |
| `PreToolUse` existence | exists | exists ✓ | Matches |
| `PermissionRequest` existence | exists | exists ✓ | Matches |
| `PostToolUse` existence | unverified | exists (limited) | Codex side fires for Bash / apply_patch / MCP only |
| `Stop` existence | unverified | exists | Adopted, fires per turn end |
| `UserPromptSubmit` existence | unverified | exists (full text via `prompt` field) | Adopted |
| `SessionStart` existence | unverified | exists (`source` enum) | Adopted |
| `SessionEnd` existence | assumed | **does not exist** | Group by Stop + session_id, or pseudo-detect via SessionStart `source="clear"` |
| `session_id` field existence | unverified | exists (string, format unspecified) | Adopted |
| `turn_id` field | unverified | exists (Codex-specific, required for the 5 turn-scoped events) | Codex adapter attaches it as optional `turn_id` on the normalized_event (Phase C-9 landing). If turn-level forensics are needed, the assumption is to groupBy on `turn_id` from events.jsonl |
| `session_id` collision across the two engines | unforeseen | spec doesn't specify the format | Both engines conventionally issue UUID-class IDs, so the actual collision probability is effectively zero. Keep the current layout sharing `sessions/<session_id>/` without an engine prefix; if collision occurs, the operator splits with `--data-dir` (Phase C-8 landing) |
| Plugin mechanism | unverified | exists (`codex plugin marketplace add`) | Adopted, §10.2 install procedure updated |
| `${CLAUDE_PLUGIN_ROOT}` equivalent env | unverified | **not officially specified** | Resolve plugin root by path computation; Phase C-1 real-environment verify |
| Feature flag `codex_hooks = true` | unverified | **Required** (silently ignored if absent) | Mandated in install procedure |
| ask not supported | known | exists ✓ (fail open) | Matches, no impact (read-only forensic) |

## 3.3 Engine-agnostic interface

Normalize each engine's event to a unified schema:

```python
normalized_event = {
    "engine": "claude-code" | "codex" | ...,
    "event_type": "user_prompt" | "pre_tool" | "post_tool" | "agent_response" | "session_end",
    "session_id": str,
    "ts": ISO 8601 with millisecond precision,
    "cwd": str,
    
    # Main fields by event_type
    "user_prompt_text": str | None,  # user_prompt
    "tool_name": str | None,         # pre_tool / post_tool
    "tool_input": dict | None,       # pre_tool
    "tool_response": str | None,     # post_tool
    "agent_response_text": str | None,  # agent_response
    "stop_reason": str | None,       # agent_response
    
    # Common derived
    "paths": list[str],              # extracted from tool_input
    "command": str | None,           # Bash-class
    
    "raw_event": dict,               # the original event (for debug)
}
```

Each engine adapter (`adapters/claude_code.py`, `adapters/codex.py`) is responsible for the conversion.

---

# 4. Plugin package structure

```
~/work/agent-output-tracer/                         ← Independent git repo
├── .claude-plugin/
│   └── plugin.json                                  ← manifest
├── hooks/
│   ├── hooks.json                                    ← hook registration (Claude Code format)
│   ├── user_prompt_submit.py
│   ├── pre_tool_use.py
│   ├── post_tool_use.py
│   ├── stop.py
│   └── session_end.py
├── adapters/
│   ├── __init__.py
│   ├── claude_code.py                                ← Claude Code event → normalized
│   └── codex.py                                       ← Codex event → normalized (Phase C)
├── core/
│   ├── __init__.py
│   ├── normalizer.py                                  ← Generates normalized_event
│   ├── recorder.py                                    ← Appends to session JSONL
│   ├── indexer.py                                     ← Builds per-session search index
│   ├── redactor.py                                    ← Masks secret patterns
│   ├── path_utils.py
│   └── time_utils.py
├── query/                                              ← CLI main features
│   ├── __init__.py
│   ├── replay.py                                       ← Replays the timeline
│   ├── trace.py                                        ← Reverse-lookup from output
│   ├── why.py                                          ← Queries the reason of an event
│   ├── diff.py                                         ← user prompt vs agent action
│   ├── state_at.py                                     ← State at time T
│   ├── grep.py                                         ← Full-text search
│   ├── causal_graph.py                                 ← Generates a causal graph
│   ├── mentioned_but_not_read.py                       ← Extracts hallucination candidates
│   └── list.py                                         ← Lists sessions
├── analyzer/                                           ← Subsidiary feature (anomaly hint patterns, shown during replay)
│   ├── __init__.py
│   ├── anomaly_hints.py                                ← Emits hints at replay time
│   └── patterns.py                                     ← Generic anomaly patterns (repeated reads of the same file / long-session outlier / routing config thrash, etc.; see §11 Phase B-8)
├── cli/
│   ├── __init__.py
│   └── main.py                                         ← entry point dispatch
├── config/
│   ├── default.toml                                    ← Default config
│   └── schema.json
├── codex/                                              ← Codex setup (Phase C)
│   ├── config.toml.example
│   └── INSTALL_CODEX.md
├── tests/
│   ├── unit/
│   │   ├── test_normalizer.py
│   │   ├── test_recorder.py
│   │   ├── test_indexer.py
│   │   ├── test_redactor.py
│   │   ├── test_replay.py
│   │   ├── test_trace.py
│   │   ├── test_diff.py
│   │   └── test_grep.py
│   ├── integration/
│   │   ├── test_full_session_lifecycle.py
│   │   ├── test_trace_from_output.py
│   │   ├── test_diff_user_vs_agent.py
│   │   └── fixtures/
│   │       ├── claude_code_sessions/
│   │       └── codex_sessions/
│   └── conftest.py
├── data/                                                ← gitignored, tied to ${CLAUDE_PLUGIN_DATA}
│   └── sessions/<session_id>/
│       ├── events.jsonl                                 ← Append-only event history
│       ├── metadata.json                                ← Session metadata
│       └── index.json                                   ← Search index
├── docs/
│   ├── DESIGN.md                                        ← Final port of this doc
│   ├── COMMANDS.md                                      ← CLI details
│   ├── CONFIG.md                                        ← How to write config
│   ├── INSTALL.md                                       ← Install procedure
│   ├── PRIVACY.md                                       ← Redaction / retention
│   └── EXAMPLES.md                                      ← Debug workflow examples
├── README.md
├── LICENSE
├── CHANGELOG.md
├── pyproject.toml
├── .gitignore
└── .github/workflows/
    ├── test.yml
    └── lint.yml
```

## 4.1 Minimal example of `plugin.json`

```json
{
  "name": "agent-output-tracer",
  "version": "0.1.0",
  "description": "Universal AI agent session forensic debugger. Replay, trace, and query agent behavior when output looks wrong.",
  "author": {
    "name": "agent-output-tracer contributors"
  },
  "license": "MIT",
  "keywords": [
    "agent-debugging",
    "session-forensic",
    "ai-observability",
    "claude-code",
    "trace"
  ]
}
```

**Do not write a `hooks` field**: Claude Code auto-loads `<plugin_root>/hooks/hooks.json`. If you explicitly set `"hooks": "./hooks/hooks.json"` in `plugin.json`, loading fails with "Duplicate hooks file detected". The `hooks` field is only for referencing **additional hook files outside the standard location** (verified on real environment, discovered 2026-05-15 when starting dev mode). The Codex side is assumed to follow the same convention (re-verify in Phase C).

## 4.2 Example of `hooks/hooks.json`

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [{
          "type": "command",
          "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/user_prompt_submit.py\""
        }]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Read|Glob|Grep|Edit|Write|MultiEdit|Bash",
        "hooks": [{
          "type": "command",
          "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/pre_tool_use.py\""
        }]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Read|Glob|Grep|Edit|Write|MultiEdit|Bash",
        "hooks": [{
          "type": "command",
          "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/post_tool_use.py\""
        }]
      }
    ],
    "Stop": [
      {
        "hooks": [{
          "type": "command",
          "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/stop.py\""
        }]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [{
          "type": "command",
          "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/session_end.py\""
        }]
      }
    ]
  }
}
```

---

# 5. Data schema

## 5.1 The event entry in `events.jsonl`

Each hook appends in the following format (1 event = 1 line):

```json
{
  "v": 1,
  "ts": "2026-05-14T10:23:45.123+09:00",
  "session_id": "abc123",
  "engine": "claude-code",
  "event_type": "pre_tool",
  "tool_name": "Read",
  "tool_input": {
    "file_path": "/Users/.../foo.md"
  },
  "paths": ["/Users/.../foo.md"],
  "cwd": "/Users/.../project"
}
```

Additional fields by event_type:

```json
// user_prompt
{
  "event_type": "user_prompt",
  "user_prompt_text": "Implement the FooBar component..."
}

// post_tool
{
  "event_type": "post_tool",
  "tool_name": "Read",
  "tool_response": "...",
  "result_bytes": 12345,
  "result_excerpt": "..."  // leading N chars, configurable
}

// agent_response (Stop)
{
  "event_type": "agent_response",
  "stop_reason": "end_turn",
  "agent_response_text": "..."
}

// session_end
{
  "event_type": "session_end",
  "tool_calls_total": 42,
  "duration_seconds": 1234.5
}
```

## 5.2 `metadata.json`

```json
{
  "v": 1,
  "session_id": "abc123",
  "engine": "claude-code",
  "ts_start": "2026-05-14T10:20:00.000+09:00",
  "ts_end": "2026-05-14T10:45:30.000+09:00",
  "cwd": "/Users/.../project",
  "tool_calls_total": 42,
  "user_prompts_count": 3,
  "agent_responses_count": 5,
  "unique_files_read": 12,
  "total_bytes_read": 234567,
  "tags": []
}
```

## 5.3 `index.json`

An index for faster search:

```json
{
  "v": 1,
  "session_id": "abc123",
  "files_read": {
    "/Users/.../foo.md": [
      {"ts": "2026-05-14T10:23:45.123+09:00", "event_idx": 3},
      {"ts": "2026-05-14T10:30:12.456+09:00", "event_idx": 17}
    ]
  },
  "tools_used": {
    "Read": [3, 17, 21, 25],
    "Glob": [5, 8],
    "Bash": [11, 15]
  },
  "text_inverted_index": {
    // Simple keyword → event_idx mapping (Phase A is word-level, n-gram in Phase B)
    "FooBar": [1, 12, 25],
    "DI": [17, 25]
  }
}
```

---

# 6. Config spec

`${CLAUDE_PLUGIN_DATA}/config.toml`:

```toml
[plugin]
enabled = true
log_level = "info"

[capture]
# user_prompt capture
user_prompt = "full"        # full | excerpt | off

# tool_input capture granularity
tool_input = "full"          # full | excerpt | paths_only | off

# tool_response capture granularity
tool_response = "excerpt"    # full | excerpt | size_only | off
tool_response_excerpt_chars = 2000  # leading N chars on excerpt

# agent_response capture
agent_response = "full"      # full | excerpt | off

# auto GC at session_end
auto_gc_on_session_end = true

[retention]
# Retention period of session JSONL
sessions_full_days = 30      # retain full content
sessions_metadata_days = 365 # retain metadata only
auto_archive_format = "gzip" # gzip when older than 30 days

[redaction]
enabled = true
patterns = [
  # default: common secret patterns
  '(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*["\']?[\w\-]{16,}["\']?',
  'sk-[a-zA-Z0-9]{40,}',
  'ghp_[a-zA-Z0-9]{36,}',
  # User-added
]
replacement = "[REDACTED]"

[anomaly_hints]
# Hint display at replay time (anomaly hint patterns, implemented in §11 Phase B-8)
enabled = true
show_repeated_read = true
repeated_read_threshold = 3
show_long_session = true
show_cross_namespace_bleed = false  # host-specific config
show_routing_thrash = true
routing_paths = ["CLAUDE.md", "AGENTS.md"]

[engine.claude_code]
enabled = true

[engine.codex]
enabled = false  # enable in Phase C
```

---

# 7. Architecture

## 7.1 Layer 1: Capture (hooks)

The 5 hook handlers normalize each event and append to `events.jsonl`:

```python
# Pseudo-code for hooks/user_prompt_submit.py
import json, sys, os
from adapters.claude_code import normalize_event
from core.recorder import append_event

def main():
    try:
        event = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    try:
        normalized = normalize_event(event, event_type="user_prompt")
        if normalized:
            append_event(normalized)
    except Exception:
        pass

    sys.exit(0)

if __name__ == "__main__":
    main()
```

Other hooks have the same shape (just pass to recorder.append_event).

## 7.2 Layer 2: Storage

`core/recorder.py`:

```python
import json
import os
from pathlib import Path

def append_event(normalized_event: dict) -> None:
    session_id = normalized_event["session_id"]
    data_dir = Path(os.environ["CLAUDE_PLUGIN_DATA"])
    session_dir = data_dir / "sessions" / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    
    events_file = session_dir / "events.jsonl"
    
    # redaction
    redacted = apply_redaction(normalized_event)
    
    # append
    with events_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(redacted, ensure_ascii=False) + "\n")
    
    # update metadata (best-effort)
    update_metadata(session_dir, redacted)
```

## 7.3 Layer 3: Query interface (CLI main features)

Each query loads `events.jsonl`, accelerates search via the index, and outputs results in a human-readable form.

### 7.3.1 Pseudo-code for `replay`

```python
# query/replay.py
def replay(session_id: str, options: dict) -> None:
    events = load_events(session_id)
    metadata = load_metadata(session_id)
    
    print(f"Session: {session_id}")
    print(f"Started: {metadata['ts_start']}")
    print(f"Total events: {len(events)}")
    print()
    
    for event in events:
        ts = format_time(event["ts"])
        typ = event["event_type"]
        
        if typ == "user_prompt":
            print(f"[{ts}] [user] {truncate(event['user_prompt_text'], 80)}")
        elif typ == "pre_tool":
            print(f"[{ts}] [tool] {event['tool_name']}({format_input(event['tool_input'])})")
        elif typ == "post_tool":
            print(f"[{ts}]   ↳ result: {format_bytes(event['result_bytes'])}")
        elif typ == "agent_response":
            print(f"[{ts}] [agent] {truncate(event['agent_response_text'], 100)}")
        
        # anomaly hint (if enabled)
        if options.get("show_hints", True):
            hints = detect_hints(event, events)
            for hint in hints:
                print(f"          ⚠️ {hint}")
```

### 7.3.2 Pseudo-code for `trace`

```python
# query/trace.py
def trace(session_id: str, output_excerpt: str) -> None:
    events = load_events(session_id)
    
    # Identify the agent_response where output_excerpt first appeared
    first_mention = find_first_event(events, lambda e: 
        e["event_type"] == "agent_response" and output_excerpt in e["agent_response_text"]
    )
    
    if not first_mention:
        print(f"Not found: '{output_excerpt}' in any agent response")
        return
    
    # Display what happened up to that point
    prior_events = events[:events.index(first_mention)]
    
    print(f"Output '{output_excerpt}' first appeared at {first_mention['ts']}")
    print()
    print("Causal trail (prior events):")
    
    # The immediately preceding user_prompt
    last_user_prompt = find_last_event(prior_events, lambda e: e["event_type"] == "user_prompt")
    if last_user_prompt:
        mentions = output_excerpt in last_user_prompt.get("user_prompt_text", "")
        print(f"  - user prompt: {last_user_prompt['ts']}: "
              f"{'✓ mentioned' if mentions else '✗ not mentioned'}")
    
    # Look for read files containing output_excerpt
    print("  - files read prior to this output:")
    for pe in prior_events:
        if pe["event_type"] == "post_tool" and pe["tool_name"] == "Read":
            response = pe.get("tool_response", "") or pe.get("result_excerpt", "")
            mentions = output_excerpt in response
            indicator = "✓ contains" if mentions else "✗ does not contain"
            path = pe.get("paths", [""])[0]
            print(f"      [{pe['ts']}] {path}: {indicator}")
    
    # Hallucination candidate decision
    has_source = any(
        pe["event_type"] == "post_tool" and 
        output_excerpt in (pe.get("tool_response", "") or pe.get("result_excerpt", ""))
        for pe in prior_events
    )
    has_user_mention = last_user_prompt and output_excerpt in last_user_prompt.get("user_prompt_text", "")
    
    if not has_source and not has_user_mention:
        print()
        print(f"⚠️  HALLUCINATION CANDIDATE: '{output_excerpt}' has no source in "
              f"user prompts or tool results visible to agent")
```

### 7.3.3 Pseudo-code for `why`

```python
# query/why.py
def why(session_id: str, event_descriptor: str) -> None:
    """e.g., event_descriptor = 'Read(file_X) at 10:23:45'"""
    events = load_events(session_id)
    target = parse_event_descriptor(events, event_descriptor)
    
    if not target:
        print(f"Event not found: {event_descriptor}")
        return
    
    target_idx = events.index(target)
    prior = events[:target_idx]
    
    print(f"Event: {target['ts']} {target['tool_name']}({format_input(target['tool_input'])})")
    print()
    print("What came immediately before:")
    
    # Show the 3 immediately preceding events
    for pe in prior[-3:]:
        print(f"  - [{pe['ts']}] {format_event_brief(pe)}")
    
    # The immediately preceding user_prompt
    last_prompt = find_last_event(prior, lambda e: e["event_type"] == "user_prompt")
    print()
    print("Last user prompt before this event:")
    print(f"  [{last_prompt['ts']}] {last_prompt.get('user_prompt_text', '')[:200]}")
    
    # If there's a preceding Glob result containing this path / target
    target_path = (target.get("paths") or [""])[0]
    glob_origin = find_glob_that_returned(prior, target_path)
    if glob_origin:
        print()
        print(f"⚠️  This path appeared in a Glob result at {glob_origin['ts']}:")
        print(f"   {glob_origin['tool_input']}")
        print(f"   (agent picked this path from Glob results, no explicit user mention)")
```

### 7.3.4 Pseudo-code for `diff`

```python
# query/diff.py
def diff(session_id: str) -> None:
    events = load_events(session_id)
    
    user_prompts = [e for e in events if e["event_type"] == "user_prompt"]
    tool_calls = [e for e in events if e["event_type"] == "pre_tool"]
    
    # Extract references (file paths / proper nouns) included in user prompts
    user_mentions = set()
    for up in user_prompts:
        text = up.get("user_prompt_text", "")
        user_mentions.update(extract_references(text))
    
    # Extract paths the agent touched in tool calls
    agent_touches = set()
    for tc in tool_calls:
        agent_touches.update(tc.get("paths", []))
    
    # diff
    user_mentioned_but_agent_didnt = user_mentions - agent_touches
    agent_touched_without_user_mention = agent_touches - user_mentions
    
    print("User mentioned but agent did NOT access:")
    for ref in sorted(user_mentioned_but_agent_didnt):
        print(f"  - {ref}")
    
    print()
    print("Agent accessed without user mention:")
    for ref in sorted(agent_touched_without_user_mention):
        print(f"  - {ref}")
    
    print()
    print("(Note: agent may have legitimate reasons to read additional files, "
          "but each should be reviewable.)")
```

### 7.3.5 Pseudo-code for `state-at`

```python
# query/state_at.py
def state_at(session_id: str, time_str: str) -> None:
    target_ts = parse_time(time_str)
    events = load_events(session_id)
    events_until = [e for e in events if parse_time(e["ts"]) <= target_ts]
    
    # Build state
    files_read = {}
    total_bytes = 0
    user_prompts = []
    
    for e in events_until:
        if e["event_type"] == "post_tool" and e.get("tool_name") == "Read":
            for p in e.get("paths", []):
                files_read[p] = files_read.get(p, 0) + 1
            total_bytes += e.get("result_bytes", 0)
        elif e["event_type"] == "user_prompt":
            user_prompts.append(e.get("user_prompt_text", ""))
    
    print(f"State at {time_str}:")
    print(f"  Files read so far: {len(files_read)} unique, "
          f"{sum(files_read.values())} total reads")
    print(f"  Total bytes from Read: {total_bytes:,}")
    print(f"  User prompts so far: {len(user_prompts)}")
    print()
    print("Top read files:")
    for path, count in sorted(files_read.items(), key=lambda x: -x[1])[:10]:
        marker = " ⚠️ repeated" if count >= 3 else ""
        print(f"  {count}x  {path}{marker}")
```

### 7.3.6 Pseudo-code for `grep`

```python
# query/grep.py
def grep(session_id: str, pattern: str, ignore_case: bool = False) -> None:
    events = load_events(session_id)
    flags = re.IGNORECASE if ignore_case else 0
    regex = re.compile(pattern, flags)
    
    for e in events:
        # Search all string fields in the event
        searchable = collect_searchable_text(e)
        for field_name, text in searchable.items():
            if regex.search(text):
                print(f"[{e['ts']}] {e['event_type']}.{field_name}: "
                      f"{highlight_match(text, regex)[:200]}")
```

### 7.3.7 Pseudo-code for `causal-graph`

```python
# query/causal_graph.py
def causal_graph(session_id: str, output_path: str) -> None:
    events = load_events(session_id)
    
    # Generate a mermaid graph
    lines = ["```mermaid", "graph TD"]
    
    for i, e in enumerate(events):
        node_id = f"E{i}"
        label = format_event_short(e)
        lines.append(f"  {node_id}[\"{label}\"]")
    
    # Causal links (each event is connected to its immediate predecessor; specific patterns get extra edges)
    for i in range(1, len(events)):
        lines.append(f"  E{i-1} --> E{i}")
        
        # Link from a preceding Glob result to a later Read
        cur = events[i]
        if cur["event_type"] == "pre_tool" and cur.get("tool_name") == "Read":
            target_path = (cur.get("paths") or [""])[0]
            glob_origin_idx = find_glob_idx_that_returned(events[:i], target_path)
            if glob_origin_idx is not None:
                lines.append(f"  E{glob_origin_idx} -.->|returned this path| E{i}")
    
    lines.append("```")
    Path(output_path).write_text("\n".join(lines))
```

### 7.3.8 Pseudo-code for `mentioned-but-not-read`

```python
# query/mentioned_but_not_read.py
def mentioned_but_not_read(session_id: str) -> None:
    """Extract mentions in the agent response whose source is found neither in the read history nor in user prompts"""
    events = load_events(session_id)
    
    # Extract proper-noun / file-path candidates from agent responses
    candidates = set()
    for e in events:
        if e["event_type"] == "agent_response":
            candidates.update(extract_references(e.get("agent_response_text", "")))
    
    # Extract candidates without a source
    suspicious = []
    for candidate in candidates:
        has_user_source = any(
            candidate in e.get("user_prompt_text", "")
            for e in events if e["event_type"] == "user_prompt"
        )
        has_read_source = any(
            candidate in (e.get("tool_response", "") or e.get("result_excerpt", ""))
            for e in events if e["event_type"] == "post_tool"
        )
        if not has_user_source and not has_read_source:
            suspicious.append(candidate)
    
    print("Hallucination candidates (mentioned in agent response, no visible source):")
    for s in sorted(suspicious):
        print(f"  - {s}")
```

## 7.4 Layer 4: Export

```python
# query/export.py
def export_trace(session_id: str, output_path: str, format: str = "markdown") -> None:
    # A forensic report combining replay + causal graph + diff + mentioned-but-not-read
    pass
```

---

# 8. CLI command list (user-facing surface)

## 8.1 Main commands

| Command | Function | Output |
|---|---|---|
| `replay --session <id>` | Display the full timeline of a session | text, in event order |
| `trace --session <id> --output <text>` | Reverse-lookup the first occurrence of an output text and show the prior causal trail | text, causal trail |
| `why --session <id> --event <descriptor>` | Query why a specific event happened | text, preceding events |
| `diff --session <id>` | Diff between user mentions and agent actions | text, tabular |
| `state-at --session <id> --time <ts>` | Snapshot of session state at a specified time | text |
| `grep --session <id> --pattern <regex>` | Full-text search within a session | text, match list |
| `causal-graph --session <id> [--output <path>]` | Generate a mermaid causal graph | markdown, mermaid |
| `mentioned-but-not-read --session <id>` | Extract hallucination candidates | text |

## 8.2 Auxiliary commands

| Command | Function |
|---|---|
| `list [--last <N>]` | List recent sessions |
| `latest` | Output the latest session's id |
| `status` | Plugin-wide status |
| `export-trace --session <id> --output <path>` | Bulk-export a forensic report |
| `gc` | Manual GC of expired sessions |
| `config` | Show current config |
| `tag --session <id> --tag <name>` | Manually tag a session (for easier later lookup) |

## 8.3 Convenient notations for specifying a session

In every command, `--session` accepts:

- `latest` — the latest session
- `<session_id>` — full ID
- `<short_id>` — first 8-char prefix
- `<tag>` — the name set via the `tag` command
- `latest-N` — N sessions ago
- ISO date `2026-05-14` — that day's session (the latest if multiple)

## 8.4 Output format

```bash
$ agent-output-tracer replay --session latest --format text       # default
$ agent-output-tracer replay --session latest --format json       # for machine processing
$ agent-output-tracer replay --session latest --format markdown   # for reports
```

---

# 9. Safety design

## 9.1 Failure tolerance

For all hooks:

```python
def main():
    try:
        event = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # On exception, silent exit; never block agent behavior

    try:
        # Real handling
        ...
    except Exception:
        pass

    sys.exit(0)
```

## 9.2 No host repo contamination

| Constraint | Implementation |
|---|---|
| Restrict write target | Only under `${CLAUDE_PLUGIN_DATA}/sessions/`, enforced in code review |
| Forbid writes to host repo paths | Asserted in unit tests |
| Reading host repo content | Observation only, re-open forbidden |

## 9.3 Privacy / Redaction

`redactor.py` automatically masks:

- API key patterns: `sk-...`, `ghp_...`, `eyJh...` JWT, etc.
- key=value pairs containing password / token / secret
- User-added patterns (add regex in config)

Redaction is applied before writing to `events.jsonl`. The raw data is not retained inside the plugin either.

## 9.4 Retention / Auto GC

```python
# Triggered by SessionEnd hook (or manually via the `gc` command)
def gc():
    cutoff_archive = now - 30 days
    cutoff_delete = now - 365 days
    
    for session_dir in sessions_dir.iterdir():
        meta = load_metadata(session_dir)
        if meta["ts_end"] < cutoff_archive:
            # Strip full content (tool_response etc.), keep metadata + index
            strip_content(session_dir)
        if meta["ts_end"] < cutoff_delete:
            # Fully delete
            shutil.rmtree(session_dir)
```

## 9.5 Performance budget

| hook | budget |
|---|---|
| UserPromptSubmit | < 5ms (just a text append) |
| PreToolUse | < 10ms (event append + index update) |
| PostToolUse | < 15ms (excerpt extraction + redaction + append) |
| Stop | < 10ms (agent response append) |
| SessionEnd | < 200ms (metadata finalize + GC trigger) |

Measure with unit tests during implementation; if exceeded, consider going async.

## 9.6 Impact when the plugin is broken

| Situation | Impact |
|---|---|
| Hook exception | Silent fail, no impact on agent behavior |
| Hook script missing | Claude Code emits a warning, agent continues (treated as hook absent) |
| Data dir corrupted | Re-created on next session start; past session logs lost, new sessions continue |
| Broken config.toml | Fall back to default config |
| Storage capacity tight | Best-effort write silently skips (no agent impact), `status` shows a warning |

Last resort on fatal failure: `claude plugin disable agent-output-tracer` to disable immediately.

---

# 10. Install and uninstall

## 10.1 For Claude Code

### Local development install

```bash
$ git clone <repo-url> ~/work/agent-output-tracer
$ cd ~/work/agent-output-tracer
$ python3 -m venv .venv && source .venv/bin/activate
$ pip install -e .

# Persistent install
$ claude plugin install ~/work/agent-output-tracer

# Or local dev (for hot reload)
$ claude --plugin-dir ~/work/agent-output-tracer
```

### Production install (marketplace)

```bash
$ claude plugin install agent-output-tracer
```

## 10.2 For Codex (Phase C, using official plugin mechanism)

### Local development install

```bash
# 1. Clone the plugin repo
$ git clone <repo-url> ~/work/agent-output-tracer

# 2. Enable the feature flag in the host repo's .codex/config.toml (required)
#    or in ~/.codex/config.toml (user level)
$ cat >> .codex/config.toml <<'EOF'
[features]
codex_hooks = true   # In 0.129+, hooks = true is also acceptable (alias)
EOF

# 3. Install via local marketplace
$ codex plugin marketplace add ~/work/agent-output-tracer

# The plugin is installed into ~/.codex/plugins/cache/$MARKETPLACE_NAME/$PLUGIN_NAME/local/
```

### Marketplace install (future)

```bash
$ codex plugin marketplace add owner/agent-output-tracer
```

### Codex-specific additions to the plugin structure

Place `.codex-plugin/plugin.json` with the same content as `.claude-plugin/plugin.json` (Claude Code + Codex dual-distribution layout):

```
~/work/agent-output-tracer/
├── .claude-plugin/
│   └── plugin.json
├── .codex-plugin/
│   └── plugin.json           ← Same form as the Claude version, common name/version/hooks fields
├── hooks/hooks.json          ← Common definition for both engines (events like PostToolUse fire only on the engine side that supports them)
├── adapters/
│   ├── claude_code.py
│   └── codex.py              ← Implemented in Phase C
└── ...
```

### Trusted project constraint

> "Project-local hooks load only when the project `.codex/` layer is trusted."

→ User-level (`~/.codex/`) install is recommended. Project-level is also possible but requires project trust configuration.

## 10.3 Disable / uninstall

```bash
$ claude plugin disable agent-output-tracer          # Temporary disable
$ claude plugin uninstall agent-output-tracer --keep-data  # Uninstall keeping data
$ claude plugin uninstall agent-output-tracer        # Full removal
```

## 10.4 Operation check

```bash
$ agent-output-tracer status

agent-output-tracer v0.1.0
Status: enabled
Data dir: ~/.claude/plugins/data/agent-output-tracer/
Sessions captured: 23 (last 30 days)
Storage used: 14.2 MB
Latest session: 2026-05-14-pm3 (started 30 min ago)
```

---

# 11. Implementation plan (Phase A / B / C)

## Phase A: Claude Code basic forensics (minimal working)

| Sub-phase | Content | Deliverable |
|---|---|---|
| A-0 | Initialize repo, Python 3.11+ skeleton, `pyproject.toml`, CI workflow | git repo created |
| A-1 | `plugin.json` + `hooks/hooks.json`, verify plugin installs with empty hook scripts | install / hook wiring confirmed |
| A-2 | Establish normalized_event in `adapters/claude_code.py` + `core/normalizer.py`, unit tests | normalize TDD pass |
| A-3 | Implement events.jsonl append in `core/recorder.py`, implement `hooks/pre_tool_use.py` | session JSONL generated |
| A-4 | Add `hooks/user_prompt_submit.py` / `stop.py` / `session_end.py` | user prompt + agent response captured |
| A-5 | Secret pattern mask in `core/redactor.py` | redaction works |
| A-6 | Implement `query/replay.py`, `agent-output-tracer replay` shows session timeline | **Main feature 1** |
| A-7 | `query/list.py` + `query/latest.py` + session id resolution (latest / short_id / tag) | session navigation |
| A-8 | Implement `query/grep.py`, full-text search | **Main feature 2** |
| A-9 | Implement `query/state_at.py`, state snapshot at time T | Main feature 3 |
| A-10 | Integration tests, performance measurement, README v0.1.0 | reproducible install + basic forensics |

Time estimate: 3-4 weeks

## Phase B: Advanced forensic queries

| Sub-phase | Content |
|---|---|
| B-1 | Build per-session search index in `core/indexer.py`, accelerate grep |
| B-2 | Implement `query/trace.py`, output reverse-lookup + causal trail |
| B-3 | Implement `query/why.py`, query an event's reason |
| B-4 | Implement `query/diff.py`, diff between user and agent actions |
| B-5 | Implement `query/mentioned_but_not_read.py`, extract hallucination candidates |
| B-6 | Implement `query/causal_graph.py`, generate mermaid causal graph |
| B-7 | `query/export.py` for bulk forensic report export |
| B-8 | Implement `analyzer/anomaly_hints.py`, anomaly hint display at replay time. Detection patterns (generic forms not dependent on host repo structure, thresholds config-driven):<br>(a) Same file read in a single session ≥ N times (default 3)<br>(b) Routing config (CLAUDE.md / AGENTS.md, etc., set via config_paths) read in a single session ≥ N times (default 3)<br>(c) `tool_calls_total` of a session exceeds the 90th percentile of the last 30 days (long-session outlier)<br>(d) Sequential reads of wrapper-class and core-class paths (time delta < 60s, config drift symptom)<br>(e) Cross-namespace boundary reads (multiple different prefixes of `boundary_paths` setting read in the same session)<br>(f) Read of a protected path via Bash (combination of `cat`/`less`/`head` etc. with protected_globs)<br>(g) Parallel firing of same-domain skills (via `skill_groups` setting) |
| B-9 | Auto GC (30 days / 365 days) + archive feature |

Time estimate: 3-4 weeks

## Phase C: Codex support (spec finalized, implementation stage)

**C-0 is complete** (2026-05-14 to 15, official docs verified via general-purpose subagent, reflected in §3.2)

| Sub-phase | Content |
|---|---|
| ~~C-0~~ | ~~Verify Codex official hook docs~~ → **Complete**, result in §3.2 |
| C-1 | Implement `adapters/codex.py`: normalize the 8 hook events (SessionStart / PreToolUse / PostToolUse / UserPromptSubmit / Stop / PermissionRequest / PreCompact / PostCompact) |
| C-2 | Place `.codex-plugin/plugin.json`, adjust `hooks/hooks.json` to a form shared between both engines |
| C-3 | Add Codex `[features] codex_hooks = true` requirement + `codex plugin marketplace add` procedure to `docs/INSTALL.md` |
| C-4 | Real-environment verify of the Codex native env var (resolution method for the `${CLAUDE_PLUGIN_ROOT}` equivalent); fall back to path computation in the adapter if needed |
| C-5 | Handling for `SessionEnd` absence: Stop event + session_id grouping + idle timeout for pseudo session-end detection |
| C-6 | Handle the Codex PostToolUse limitation (fires only for Bash / apply_patch / MCP): explicitly note the limited functionality |
| C-7 | Codex integration test fixtures (using sample events fetched from the official schema directory) |
| C-8 | Confirm session_id consistency when both engines run side by side |
| C-9 | Consider using the `turn_id` field (Codex-specific turn identifier, useful for turn-level forensics) |
| C-10 | Make the Codex version requirement explicit (>= 0.128 recommended, >= 0.129 if you use compaction events) |

Time estimate: 2-3 weeks (C-0 shortened)

## Phase D: Advanced features (optional)

- Web UI viewer (browse the plugin data dir)
- AI agent integration (pass query results to another LLM for summarization)
- Pattern learning / user behavior fingerprinting
- Marketplace publication preparation

---

# 12. Test strategy

## 12.1 Unit tests

| Target | Coverage |
|---|---|
| `core/normalizer.py` | Per-engine event → normalized, edge cases |
| `core/recorder.py` | Append / consecutive writes / silent on failure |
| `core/indexer.py` | Index consistency, search accuracy |
| `core/redactor.py` | Secret pattern masking, false-positive suppression |
| `query/replay.py` | Event ordering, format output |
| `query/trace.py` | First-occurrence identification, causal trail construction |
| `query/diff.py` | Mention / touch set operations |
| `query/grep.py` | Regex match, case sensitivity |
| `analyzer/anomaly_hints.py` | Hint thresholds |

## 12.2 Integration tests

| Scenario | Verification |
|---|---|
| Claude Code event ingestion → events.jsonl produced | End-to-end |
| Full session of user prompts + tool calls + agent responses | All events reproduced in replay |
| Hallucination scenario (mention without a read source) | Detected by `mentioned-but-not-read` |
| Cross-namespace bleed | Anomaly hint shown |
| 1000 events / session | Within performance budget |
| Hook exception raised | No impact on agent behavior |
| When plugin is disabled | Hook does not fire |
| Codex event ingestion (Phase C) | Same level of capture as Claude Code |

## 12.3 Performance tests

```python
def test_capture_overhead():
    avg_ms = bench_full_session(num_events=1000)
    assert avg_ms < 15  # per-call budget
```

## 12.4 Safety tests

- Write attempt outside `${CLAUDE_PLUGIN_DATA}` → fail
- Behavior when redaction fails (does the secret leave a trace in logs?)
- Huge event JSON (10MB) → skip
- Intentionally broken config.toml → fall back to default

---

# 13. Limitations / unverified items

## 13.1 Items to verify before implementation starts

| Item | Resolution | Status |
|---|---|---|
| Actual paths of Claude Code `${CLAUDE_PLUGIN_ROOT}` / `${CLAUDE_PLUGIN_DATA}` | Phase A-1 real-environment verify | **✓ Complete** (2026-05-15, measured `~/.claude/plugins/data/agent-output-tracer-inline/` in dev mode. Whether the suffix is present in persistent install will be re-verified in Phase A-11) |
| Format of Claude Code PostToolUse `tool_response` for Read results | Phase A-3 real-environment verify | **✓ Complete** (dict type `{"type":"text","file":{...}}`, reflected in Appendix A.4) |
| Completeness of `response_text` from the Claude Code Stop hook | Phase A-4 real-environment verify | **✓ Complete** (actual field name is `last_assistant_message`, `stop_reason` never arrives; reflected in Appendix A.5) |
| Claude Code UserPromptSubmit event fields | Phase A-4 real-environment verify | **✓ Complete** (actual field name is `prompt`, reflected in Appendix A.2) |
| Fields of the Claude Code SessionEnd event | Phase A-3 real-environment verify | **✓ Complete** (`reason` field present, reflected in Appendix A.6. Also observed that `SessionEnd` may fire on its own) |
| Codex hook spec | Phase C-0 official docs | **Complete** (2026-05-14 to 15, reflected in §3.2) |
| Format of Codex `session_id` (UUID v4 or custom) | Phase C-1 real-environment verify | Pending |
| Codex native plugin data env var (`${CLAUDE_PLUGIN_ROOT}` equivalent) | Phase C-4 real-environment verify | Pending |
| Breaking changes between Codex schema minor versions | Phase C-10 changelog re-check | Pending |
| Whether PostToolUse fires for Codex's WebSearch / Read-equivalent tools | Phase C-6 real-environment verify | Pending (officially documented as non-firing) |

## 13.2 Design-level limitations

- **Hooks cannot observe the agent's internal context**: attention state / token-level focus are invisible
- **Cannot "accurately detect" rot**: anomaly hints are proxies, assistive to user judgment
- **Cross-session behavior**: forensics is independent per session; long-running stateful agents need a separate design
- **Correctness judgment of agent output**: undecidable from hook data alone; defer to the user / external reviewers
- **Acquisition of tool_response content**: large content is excerpt-only by default; full mode is a storage / performance trade-off
- **Accuracy of hallucination detection**: detectable when the source is visible; cannot be distinguished from the agent's implicit knowledge

## 13.3 Items that need tuning at operation time

- Capture granularity (excerpt char count, full / off for tool_response)
- Retention period (depends on the nature of the work)
- Redaction patterns (add host repo-specific secret formats)
- Anomaly hints thresholds
- Query performance for huge sessions (index design)

---

# 14. Public release strategy

## 14.1 For now (Phase A-B)

- Local install + GitHub install by individuals / small teams
- Public repo (`itosdad/agent-output-tracer`), shared with trusted users
- Collect feedback

## 14.2 Official Marketplace publication (option after Phase C)

Requirements when listed as a "registered marketplace" on the official Claude Code marketplace (items not confirmed in official docs are to be re-confirmed in Phase C-Late):

1. Required metadata in `plugin.json` complete
2. README with screenshots + workflow examples
3. CHANGELOG.md
4. GitHub Actions CI (test / lint)
5. Semantic versioning

## 14.3 Distribution channels (real-environment verified / 2026-05-15)

**Correct install flow** (confirmed against official docs, via claude-code-guide subagent):

```
/plugin marketplace add itosdad/agent-output-tracer
/plugin install agent-output-tracer@itosdad-agent-output-tracer
```

That is, "register a GitHub repo as a marketplace → install a plugin within it" — a **two-step flow**. The "one-line `claude plugin install <git-url>` install" does **not exist** as an official command (the description in the old §14.3 was a wrong guess; corrected).

To make this two-step flow possible, this repo simultaneously places **both** of the following at the root:

- `.claude-plugin/plugin.json` — plugin body definition
- `.claude-plugin/marketplace.json` — declaration that this repo is a personal marketplace containing exactly 1 plugin

(`marketplace.json` `plugins[0].source = "./"` points to the plugin in the same repo).

### Update flow

Official version resolution order:
1. `version` field in `plugin.json`
2. `version` field in the marketplace.json plugin entry (if it diverges from plugin.json, plugin.json silently wins, so consolidate on one)
3. git commit SHA

This plugin specifies `version` in `plugin.json` in semver explicitly (e.g., `"0.1.0"`) and bumps + git tags (`v0.1.0`) per release. User-side update is `/plugin update agent-output-tracer@itosdad-agent-output-tracer`.

### Relation to dev mode

Dev mode (`claude --plugin-dir ~/work/agent-output-tracer`) bypasses marketplace.json and references the source path directly. `/reload-plugins` reflects commits immediately, no version bump needed. Mutually exclusive with production operation (`/plugin marketplace add`).

---

# Appendix A: Claude Code hook event schema (real-environment verified, 2026-05-15)

The shape confirmed by real event captures (the "expected field" names in the official docs differed from the real environment in places, so this appendix is **rewritten based on the real-environment dump**. Verification source: raw_event observed in `~/.claude/plugins/data/agent-output-tracer-inline/sessions/<UUID>/events.jsonl`).

## A.1 Common fields

Every hook receives the following:

```json
{
  "session_id": "ba640ad4-5982-4601-8bed-69164fd10851",   // UUID v4
  "transcript_path": "/Users/.../.claude/projects/-Users-...-<project-slug>/<session_id>.jsonl",
  "cwd": "/Users/...",                                       // absolute path
  "hook_event_name": "UserPromptSubmit|PreToolUse|PostToolUse|Stop|SessionEnd"
}
```

`permission_mode` is delivered **only for turn-scoped hooks (PreToolUse / PostToolUse / Stop)** (e.g., `"default"`). It does not come on SessionEnd.

## A.2 UserPromptSubmit

```json
{
  ...common,
  "hook_event_name": "UserPromptSubmit",
  "prompt": "..."                                           // ← same field name as Codex
}
```

**Important**: The official docs expected `user_prompt`, but the real event uses `prompt`. This plugin's adapter handles both (`user_prompt` → `prompt` fallback).

## A.3 PreToolUse

```json
{
  ...common,
  "permission_mode": "default",
  "hook_event_name": "PreToolUse",
  "tool_name": "Read|Glob|Grep|Edit|Write|MultiEdit|Bash",
  "tool_input": {
    "file_path": "/path/..."                                // Read/Write/Edit/MultiEdit
    // or "pattern": "...", "path": "..."                   // Glob/Grep
    // or "command": "...", "description": "..."            // Bash
  },
  "tool_use_id": "toolu_01EibVnnMzShRvxNPTPieM8y"           // ← not in official docs
}
```

`tool_use_id` is the Claude API tool_use block id. This plugin only retains it in raw_event and does not use it in Phase A. Phase B `trace` / `why` can use it for strict pre↔post pairing.

## A.4 PostToolUse

```json
{
  ...common,
  "permission_mode": "default",
  "hook_event_name": "PostToolUse",
  "tool_name": "Read",
  "tool_input": {...},                                       // same as PreToolUse
  "tool_response": {                                         // ← **dict type** (not a string)
    "type": "text",
    "file": {
      "filePath": "/path/...",
      "content": "...",
      "numLines": 92,
      "startLine": 1,
      "totalLines": 92
    }
    // For Bash: {"stdout": "...", "stderr": "...", "interrupted": bool,
    //            "isImage": bool, "noOutputExpected": bool}
  },
  "tool_use_id": "toolu_01...",                              // same id as PreToolUse
  "duration_ms": 24                                          // ← not in official docs
}
```

Because `tool_response` arrives as a **dict**, this plugin's `_coerce_response` `json.dumps`-encodes it before recording (so that downstream grep / index treats it as a string). `duration_ms` is intended for use in Phase B anomaly hints (long-running tool detection).

## A.5 Stop

```json
{
  ...common,
  "permission_mode": "default",
  "hook_event_name": "Stop",
  "stop_hook_active": false,                                 // ← bool. "Whether the Stop hook is currently active"
  "last_assistant_message": "..."                            // ← same field name as Codex
}
```

**Important**: The official docs expected `response_text` / `stop_reason: "end_turn|tool_use|max_tokens"`, but the real event uses `last_assistant_message` and `stop_reason` is **not delivered**. Instead, `stop_hook_active: bool` is delivered (little direct use for the plugin). This plugin's adapter operates with `response_text` → `last_assistant_message` fallback. `stop_reason` is always None on the normalized event.

## A.6 SessionEnd

```json
{
  ...common (session_id, transcript_path, cwd, hook_event_name),
  "hook_event_name": "SessionEnd",
  "reason": "prompt_input_exit"                              // ← not in official docs
}
```

`reason` is the kind of session end. Empirically observed values:
- `"prompt_input_exit"` — normal end such as `/exit`
- (Others like `"clear"`, `"logout"` likely exist but were not observed in Phase A. Additional verify in Phase B)

Note: **`SessionEnd` can fire by itself** — when `hooks/hooks.json` fails to load, the other hooks (UserPromptSubmit / PreTool / PostTool / Stop) don't fire, but a case was observed where SessionEnd does fire on `/exit` (leaving a single line in events.jsonl for an empty session). Likely the Claude Code plugin loader judges each hook independently.

---

# Appendix A.7: Behaviors specific to dev mode (`--plugin-dir`)

Real-environment verified behaviors:

- **Data dir name gets a `-inline` suffix**: `~/.claude/plugins/data/agent-output-tracer-inline/` (for persistent install it should be without the suffix, but re-verify in Phase A-11)
- **`${CLAUDE_PLUGIN_DATA}` resolves to**: `~/.claude/plugins/data/<plugin_name>[-inline]/`
- **session_id format**: UUID v4 (`ba640ad4-5982-4601-8bed-69164fd10851`) — for Codex compatibility, "assume only string" remains the correct stance
- **transcript_path naming**: `~/.claude/projects/<slug with cwd slash→hyphen conversion>/<session_id>.jsonl`

---

# Appendix B: Codex hook event schema (official spec confirmed, 2026-05-14 to 15 verify)

From the official generated schema (https://github.com/openai/codex/tree/main/codex-rs/hooks/schema/generated) and the official docs (https://developers.openai.com/codex/hooks):

## B.1 Common input fields (required for all 8 events)

```json
{
  "hook_event_name": "PreToolUse|PostToolUse|SessionStart|UserPromptSubmit|Stop|PermissionRequest|PreCompact|PostCompact",
  "session_id": "string",
  "cwd": "/path/...",
  "model": "model name",
  "permission_mode": "default|acceptEdits|plan|dontAsk|bypassPermissions",
  "transcript_path": "/path/... or null",
  "turn_id": "string"  // required only for the 5 turn-scoped events (PreToolUse / PostToolUse / UserPromptSubmit / Stop / PermissionRequest)
}
```

## B.2 Additional fields per event

### PreToolUse

```json
{
  ...common,
  "tool_name": "Bash|apply_patch|...",
  "tool_input": {
    "command": "..."   // ← canonical; `cmd` has no official basis
  }
}
```

### PostToolUse

```json
{
  ...common,
  "tool_name": "Bash|apply_patch|MCP_tool_name",
  "tool_input": {...},
  "tool_response": <JSON value>  // tool-specific output; for MCP it's the MCP call result
}
```

**Important limitation**: Codex's Read equivalents / non-shell, non-MCP tools like WebSearch **do not fire PostToolUse**:

> "This doesn't intercept all shell calls yet... Similarly, this doesn't intercept `WebSearch` or other non-shell, non-MCP tool calls." (official hooks docs)

### UserPromptSubmit

```json
{
  ...common,
  "prompt": "full user prompt text"
}
```

### Stop

```json
{
  ...common,
  "stop_hook_active": bool,
  "last_assistant_message": "..."
}
```

### SessionStart

```json
{
  ...common,
  "source": "startup|resume|clear"
}
```

### PermissionRequest

Complex schema; not adopted by this plugin, omitted. See the generated schema directory for details.

### PreCompact / PostCompact (0.129+)

Session compaction lifecycle events. Use in Phase D of this plugin is under consideration.

## B.3 Defensive reads used by the plugin (simplified version)

Since the official spec confirms that the `event` notation / `cmd` field **do not exist**, defensive code is simplified to:

```python
# Simplified (the correct form after official spec verification)
event_name = event.get("hook_event_name", "unknown")
command = tool_input.get("command", "")
```

The empirically observed `event` / `cmd` branches are **unnecessary, recommended for removal**.

## B.4 output (hook → response back to Codex)

Current format (PreToolUse):

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",   // ← output side is camelCase
    "permissionDecision": "deny",
    "permissionDecisionReason": "..."
  }
}
```

`agent-output-tracer` is read-only forensic, so it only uses **exit 0 + empty stdout**; the output-side schema is unused.

## B.5 Priority of multiple hooks

> "Multiple matching command hooks for the same event are launched concurrently, so one hook cannot prevent another matching hook from starting."
> "If multiple matching hooks return decisions, any `deny` wins."

→ The plugin returns no decision, so there is no problem running alongside other hooks.

---

# Appendix C: Debug workflow examples

## C.1 Hallucination investigation

```
[user]: "The agent told me it 'used a DI container in the design', but our
         project's policy is not to use DI. Why did it say this?"

$ agent-output-tracer trace --session latest --output "DI container"

Output 'DI container' first appeared at 2026-05-14T10:30:12.456+09:00
Causal trail (prior events):
  - user prompt at 10:30:00: ✗ no 'DI' mentioned
  - files read prior to this output:
      [10:30:03] CLAUDE.md: ✗ does not contain
      [10:30:08] src/lib/di.ts: ✓ contains  ← source!

→ user: "Ah, it read di.ts on its own. Why?"

$ agent-output-tracer why --session latest --event "Read(src/lib/di.ts)"

Event: 10:30:08 Read(file_path=src/lib/di.ts)
What came immediately before:
  - [10:30:05] Glob(pattern='src/**/*.tsx') returned 23 results
  - [10:30:08] (the Read above)

⚠️ This path appeared in a Glob result at 10:30:05:
   Glob pattern: src/**/*.tsx
   (agent picked this path from Glob results, no explicit user mention)

→ user: "The Glob returned an unrelated file and the agent read it.
         Next time I'll narrow down the Glob pattern."
```

## C.2 Wrong tool investigation

```
[user]: "On an SEO project, the agent invoked search-console-interpreter,
         but it should have been serp-reverse-engineer, right?"

$ agent-output-tracer why --session today \
  --event "Skill(search-console-interpreter)"

Event: 14:22:30 Task tool invoked with subagent_type='search-console-interpreter'
What came immediately before:
  - [14:22:25] user_prompt: "I want to do SERP analysis for a new keyword"
  - [14:22:27] agent thinking (Read CLAUDE.md)
  - [14:22:30] (the invocation above)

⚠️ User prompt mentioned 'SERP analysis' but agent invoked 'search-console-interpreter'
   (interprets GSC data, not SERP results)

$ agent-output-tracer grep --session today --pattern "serp"

[14:22:25] user_prompt.text: "I want to do **SERP** analysis for a new keyword"
(no other 'serp' mentions in session)

→ user: "The agent confused SERP and GSC. The routing rules may be
         ambiguous; I'll make it explicit in CLAUDE.md."
```

## C.3 Cross-namespace bleed investigation

```
[user]: "I was supposed to be working on Project A, but the agent referenced
         Project B files."

$ agent-output-tracer diff --session latest

User mentioned but agent did NOT access:
  - projects/A/spec.md
  
Agent accessed without user mention:
  - projects/A/config.yaml          ← legitimate (near A/spec.md)
  - projects/B/utils.ts             ← ⚠️ unexpected
  - projects/B/types.ts             ← ⚠️ unexpected

→ user: "Check why Project B was read"

$ agent-output-tracer why --session latest --event "Read(projects/B/utils.ts)"

Event: 11:45:30 Read(projects/B/utils.ts)
What came immediately before:
  - [11:45:25] Glob(pattern='projects/**/utils.ts')

⚠️ Glob pattern crosses project boundaries.
   Consider scoping Glob to projects/A/ to avoid cross-project bleed.
```

## C.4 Session quality drop investigation

```
[user]: "The session's early answers were good, but the second half went off-target."

$ agent-output-tracer replay --session latest --show-hints

[10:00:00] [user] "Implement FooBar"
[10:00:05] [tool] Read CLAUDE.md (12KB)
[10:00:08] [tool] Read src/foo.ts (5KB)
[10:00:15] [agent] "Here is the implementation plan..."

[10:05:00] [user] "Write tests too"
[10:05:03] [tool] Read CLAUDE.md (12KB)    ⚠️ 2nd read (30 sec ago)
[10:05:12] [agent] "Test plan..."

[10:10:00] [user] "Documentation as well"
[10:10:01] [tool] Read CLAUDE.md (12KB)    ⚠️ 3rd read in 10 min (lost-in-middle hint)
[10:10:05] [tool] Read src/foo.ts (5KB)    ⚠️ 2nd read
[10:10:18] [agent] "Documentation plan..."  ← user's "off-target second half" starts here?

→ user: "Indeed, the context has bloated from this point on.
         Reading CLAUDE.md 3 times by then may have squeezed the attention budget.
         Next time on long tasks I'll split the session."
```

---

# Appendix D: Glossary

| Term | Definition |
|---|---|
| **Session** | Unit from one agent start to its end. Identified by session_id |
| **Event** | A single action within a session (user prompt / tool call / agent response, etc.) |
| **Normalized event** | A dict converted from engine-specific event JSON into the plugin's internal unified schema |
| **Forensic recorder** | A mechanism that fully records sessions; provides data for cause tracing |
| **Causal trail** | The series of immediately preceding events leading up to a given event, a trace of the causal chain |
| **Anomaly hint** | A heads-up shown during replay. A subsidiary output of pattern auto-detection |
| **Hallucination candidate** | A mention that appears in an agent response but for which no source is found in either user prompts or read history |
| **Redaction** | The process of masking secret patterns before writing to the log |
| **Issue-agnostic** | An approach that does not classify the anomaly's type in advance |
| **Engine adapter** | The conversion layer that turns each engine's event format into the unified schema |
| **Excerpt** | A fragment cut to the leading N characters of long content such as tool_response |

---

# Handoff notes (for the next session / another agent)

## What was decided in this session

1. **Plugin name**: `agent-output-tracer` (the name expresses the issue-agnostic debugger function)
2. **Placement**: `~/work/agent-output-tracer/` (independent git repo)
3. **Main feature**: **forensic / debug functionality**, not detection. When the user notices something off, they can replay / trace / query the session
4. **Issue-agnostic**: Does not classify the type of anomaly; only provides debug capability
5. **Mechanical recorder, not dependent on agent compliance**
6. **Anomaly hint patterns**: Subsidiary, shown during replay; not the main feature (specific patterns in §11 Phase B-8)
7. **No host repo contamination**: contained to the plugin data dir
8. **Engine support**: Claude Code is primary, Codex is Phase C
9. **5 hooks adopted**: UserPromptSubmit / PreToolUse / PostToolUse / Stop / SessionEnd
10. **Content capture**: default is excerpt + paths; full mode is opt-in

## First things to do when implementation starts

1. `git init` in `~/work/agent-output-tracer/`
2. Draft `pyproject.toml` (Python 3.11+, minimal dependencies)
3. Start from **Phase A-1**: make plugin install succeed with `plugin.json` + empty `hooks/hooks.json`
4. From Phase A-2 onward, proceed TDD: build `core/normalizer.py` driven by unit tests
5. Phase A-3 to A-6 sequentially (recorder → user prompt / stop → redactor → replay)
6. After Phase A completes, **the `replay` command working** is the mandatory milestone (the most important main feature)

## Notes

- In this doc, repo-specific concepts like "host repo", "OS", "Director OS" are **excluded from the plugin itself**. Everything is config-driven
- Behavior of `${CLAUDE_PLUGIN_ROOT}` / `${CLAUDE_PLUGIN_DATA}` is to be real-environment verified in Phase A-1
- The Codex official docs were unverified at doc creation time; Phase C-0 needs a preceding verify
- **Do not claim "we can detect rot"**: detection ≠ provision. This plugin is a forensic recorder; judgment is the user's
- The output quality of `replay` determines most of the plugin's value. Spend time on Phase A-6
- Enable redaction from the start (prevents secret-leak incidents)

## Primary sources already verified

| Source | URL | Verified | Verification method |
|---|---|---|---|
| Claude Code hooks official | https://code.claude.com/docs/en/hooks.md | 2026-05-14 | claude-code-guide subagent |
| Claude Code plugins official | https://code.claude.com/docs/en/plugins.md | 2026-05-14 | Same as above |
| Claude Code plugins reference | https://code.claude.com/docs/en/plugins-reference.md | 2026-05-14 | Same as above |
| Claude Code settings | https://code.claude.com/docs/en/settings.md | 2026-05-14 | Same as above |

## Unverified — to be confirmed in Phase A-1 / C-0

| Item | Importance |
|---|---|
| Resolution path of `${CLAUDE_PLUGIN_ROOT}` / `${CLAUDE_PLUGIN_DATA}` | High (Phase A-1) |
| Format of PostToolUse `tool_response` for Read results | High (Phase A-3) |
| Completeness of Stop hook `response_text` | Medium (Phase A-4) |
| Name of the prompt field on UserPromptSubmit | Medium (Phase A-4) |
| Detailed fields of SessionEnd | Medium (Phase A-3) |
| Codex CLI hooks official docs | Medium (Phase C-0) |
| Existence of a Codex UserPromptSubmit equivalent | Medium (Same as above) |

---

# Revision history

## 2026-05-14 (initial version)

- Established as an issue-agnostic forensic debugger plugin (plugin name `agent-output-tracer`)
- During design, the proxy detection approach (pattern auto-detection) was rejected, converging on a role split of forensic recorder + user-driven query (rationale in §0.5)
- 5 hooks adopted: UserPromptSubmit / PreToolUse / PostToolUse / Stop / SessionEnd
- 8 main CLI commands defined: replay / trace / why / diff / state-at / grep / causal-graph / mentioned-but-not-read
- Pattern detection (P-X series) demoted to a subsidiary anomaly hint
- Phase A / B / C staged implementation plan
- Safety design (failure tolerance / no host contamination / privacy redaction / auto GC / performance budget)

## 2026-05-14 to 15 (Phase C-0 complete) — Codex official hook docs verified

**Trigger**: User instruction "What is the Codex official hook docs verify?" "Verify now."

**Action**: Verified the OpenAI Codex CLI official docs as a primary source via the general-purpose subagent. Retrieved and saved the official docs with defuddle (`shared-assets/temporary/defuddle-openai-codex-hooks.md` and so on).

**Main findings**:

1. **Codex official hooks docs exist**: https://developers.openai.com/codex/hooks (and config-advanced / changelog / plugins/build / generated schemas)
2. **8 available hook events**: SessionStart / PreToolUse / PermissionRequest / PostToolUse / UserPromptSubmit / Stop / PreCompact / PostCompact (**SessionEnd does not exist**)
3. **`session_id` field confirmed** (required on all events)
4. **`turn_id` field exists**: required on the 5 turn-scoped events (Codex-specific extension, absent in Claude Code)
5. **Items contradicting the empirical observation**:
   - Standalone `event` notation has **no official basis** (defensive code unnecessary)
   - `tool_input.cmd` has **no official basis** (only `command`)
6. **`SessionEnd` absence → design change**: in Codex, treat session completion pseudo-grouping via Stop event + session_id, or detect switching via SessionStart `source="clear"`
7. **PostToolUse limitations**: fires only for Bash / apply_patch / MCP; Read / WebSearch equivalents do not fire (explicit in the official docs)
8. **Plugin mechanism officially confirmed**: install via `codex plugin marketplace add <path or repo>`, placed in `~/.codex/plugins/cache/...`
9. **Feature flag `[features] codex_hooks = true` required** (silently ignored if absent; mandated in install procedure)
10. **Version recommendation**: >= 0.128 (plugin-bundled hooks), >= 0.129 if using compaction events

**Doc revisions**:

| Location | Before | After |
|---|---|---|
| frontmatter `verification_dates` | Codex official docs unverified | Added "Codex official hooks docs verify complete (2026-05-14 to 15)" |
| §3.2 Codex CLI section | Thin description based on empirical observation | Detailed content with official spec confirmed (8 events, common fields, PostToolUse limitations, SessionEnd absence handling, plugin mechanism, feature flag, version requirements, summary of differences from empirical observation) |
| §10.2 Codex install | Only a sample `config.toml.example` | `codex plugin marketplace add` official procedure + feature flag required + trusted project constraint |
| §11 Phase C | C-0 to C-5, written as verify-not-complete | **C-0 complete**, remaining C-1 to C-10 expanded as spec-confirmed |
| §13.1 verify status | Codex hook spec: Phase C-0 official docs | **Complete** + remaining items (session_id format / native env var / version compatibility) enumerated |
| Appendix B | 1 schema example based on real measurements + defensive code | **Official spec confirmed**: B.1 to B.5 with common fields / per-event schema / simplified defensive code / output format / multiple-hooks priority |

**Remaining tasks (require real-environment verify before Phase C starts)**:

- Exact format of Codex `session_id` (UUID v4 or custom)
- Resolution of the Codex native plugin data env var (`${CLAUDE_PLUGIN_ROOT}` equivalent)
- History of breaking changes between Codex schema minor versions

**Official docs retrieved (gitignored `shared-assets/temporary/`)**:

- `defuddle-openai-codex-hooks.md` (486 lines, wordCount 2188)
- `defuddle-openai-codex-hooks.json`
- `defuddle-openai-codex-plugins-build.md`
- `defuddle-openai-codex-changelog.md`

These can be ported into the plugin repo (`~/work/agent-output-tracer/`) when implementation starts, within the retention period.

## Background (5-stage design convergence + Codex official verify complete)

Summary record of the design judgment evolution leading to this plugin (the specific rejected-alternative docs were deleted at the time this doc was finalized, and this doc is re-organized to stand alone):

1. Early stage: predictive guard on the host repo side (hard deny / chapter splits, etc.) → withdrawn due to mismatch in design intent
2. Soft-signal preventive approach (pragma) → replaced after it was clarified that hard enforcement is possible with existing permissions deny
3. Switched policy from prevention-centric to detection-centric (drafted a host repo-coupled detection design)
4. Switched again from host repo-coupled to a fully separated plugin design (drafted as a pattern auto-detection plugin)
5. **Considering the essential limit of detection design (the proxy problem: proxy ≠ rot itself), pivoted again to a forensic debugger (initial version of this doc)**
6. **Phase C-0 complete**: Verified Codex official hooks docs, rewrote §3.2 / Appendix B / §10.2 / §11 / §13.1 on the basis of the official spec

Each stage is an accumulation of self-correction triggered by constructive review. By eliminating overstatements ("can accurately detect", "can judge rot from patterns", etc.) one by one and reducing to honest capability, the current design was reached. This doc is the most mature form.
