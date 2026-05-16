# OBSERVATIONS

A place to accumulate findings from real-environment verification. Observations already reflected in the design doc / code / docs are recorded with these four items:
- when
- what was confirmed
- primary sources (where raw events are stored, the session_id of the verify session, etc.)
- which doc / file it was reflected into

This is the starting point when you want to track something reproducibly.

---

## 2026-05-15 — Phase A dev mode real-environment verify

### Context

First launch via `claude --plugin-dir ~/work/agent-output-tracer`. Explicitly declaring the `hooks` field in `plugin.json` caused a "Duplicate hooks file detected" error, so the initial load failed; after the fix commit, reload confirmed all hooks fire.

### Primary sources

- `~/.claude/plugins/data/agent-output-tracer-inline/sessions/ba640ad4-5982-4601-8bed-69164fd10851/events.jsonl` (9 events, a session with 2 turns of Read + Bash)
- The corresponding `metadata.json`
- `~/.claude/plugins/data/agent-output-tracer-inline/sessions/9afc8a3e-db72-4381-9d67-393f8fdcbf27/events.jsonl` (only 1 event, a standalone SessionEnd from the failed load)

### Observations

1. **The UserPromptSubmit field name is `prompt` (NOT `user_prompt`)**
   - The old wording in design doc Appendix A was speculative and differed from reality
   - Reflected in: `docs/DESIGN.md` Appendix A.2, comment on the UserPromptSubmit branch in `adapters/claude_code.py`

2. **The Stop field name is `last_assistant_message` (NOT `response_text`)**
   - `stop_reason` is not sent. Instead there is `stop_hook_active: bool`
   - Reflected in: `docs/DESIGN.md` Appendix A.5, comment on the agent_response branch in `adapters/claude_code.py`
   - As a result, the `(end_turn)` label in replay output never appears for Claude Code (it becomes None)

3. **PostToolUse's `tool_response` is a dict**
   - Example: `{"type": "text", "file": {"filePath": ..., "content": ..., "numLines": ...}}`
   - For Bash: `{"stdout": ..., "stderr": ..., "interrupted": bool, ...}`
   - `_coerce_response` already handled dict → JSON.dumps conversion, so there was no behavioral issue
   - Reflected in: `docs/DESIGN.md` Appendix A.4

4. **PostToolUse carries `tool_use_id` / `duration_ms`**
   - Not documented in the design doc
   - `tool_use_id` has the form `toolu_01...` (the Claude API tool_use block id)
   - Planned use: strict pre↔post correlation in Phase B's `trace` / `why`
   - Reflected in: `docs/DESIGN.md` Appendix A.3 / A.4

5. **SessionEnd has a `reason` field**
   - Observed value: `"prompt_input_exit"` (normal termination via `/exit`)
   - Other enum values such as `clear` / `logout` are likely (unobserved)
   - Reflected in: `docs/DESIGN.md` Appendix A.6

6. **The dev mode data dir has an `-inline` suffix**
   - `~/.claude/plugins/data/agent-output-tracer-inline/`
   - Whether the suffix is present in a persistent install will be re-verified in Phase A-11
   - Reflected in: `docs/INSTALL.md` Verify section, `docs/DESIGN.md` Appendix A.7

7. **session_id is a UUID v4**
   - Form: `ba640ad4-5982-4601-8bed-69164fd10851`
   - For Codex compatibility, keep the assumption "only that it is a string"
   - Reflected in: `docs/INSTALL.md` Session id format section

8. **The `"hooks"` field in `plugin.json` must not be declared explicitly**
   - Claude Code auto-loads `hooks/hooks.json`
   - Declaring it explicitly causes "Duplicate hooks file detected" and manifest load fails
   - Reflected in: `docs/DESIGN.md` §4.1; the field was removed from `.claude-plugin/plugin.json` / `.codex-plugin/plugin.json`

9. **Even when plugin load fails, SessionEnd alone may still fire**
   - With a hooks.json load error the other hooks did not fire, but on `/exit` only SessionEnd fired and left an empty session dir behind
   - Possibly the Claude Code plugin loader makes its decision independently per hook
   - Reflected in: a note at the end of `docs/DESIGN.md` Appendix A.6

10. **The adapter's forgiving design saved us**
    - The dual handling of `user_prompt` || `prompt` and `response_text` || `last_assistant_message` was written "for Codex compatibility", but Claude Code itself uses the same field names
    - As a result, it absorbed the gap from skipping real-environment verification. Lucky shot, but Phase A-2's TDD happened to give us the right guard
    - Reflected in: comments on the relevant fallback sites in `adapters/claude_code.py` were rewritten from "Codex compatibility" to "Claude Code's actual field names"

### Open

- Whether the data dir for a persistent install (`claude plugin install <path>`) gets the `-inline` suffix — to be re-verified in Phase A-11 by running `claude plugin install ~/work/agent-output-tracer`
- The complete enum of possible SessionEnd `reason` values — reproduce conditions for `clear` / `logout` etc. in separate sessions
- Whether `permission_mode` is also sent on SessionEnd / UserPromptSubmit — it was missing on SessionEnd / UserPromptSubmit in the real-environment dump; re-verify under a different permission_mode

---

---

## 2026-05-15 — Verify of the install flow during Phase A-11 GitHub publication prep

### Context

Preparing to publish the GitHub repo `itosdad/agent-output-tracer`. Design doc §14.3 said "GitHub repo direct (`claude plugin install <git-url>`)", but verification against the official docs revealed **that command does not exist**. Quotes from the official docs were obtained via the claude-code-guide subagent.

### Primary sources

- https://code.claude.com/docs/en/discover-plugins.md §Install plugins
- https://code.claude.com/docs/en/plugin-marketplaces.md §Marketplace schema / Plugin sources / Version resolution
- https://code.claude.com/docs/en/plugins-reference.md §Version management

### Observations

1. **`claude plugin install <git-url>` does not exist**
   - The official install flow is **two stages**: `/plugin marketplace add owner/repo` → `/plugin install plugin-name@marketplace-name`
   - Reflected in: corrected `docs/DESIGN.md` §14.3; rewrote the GitHub install section of `docs/INSTALL.md` to the marketplace flow

2. **For a plugin in the same repo, the source can be the relative path `"./"`**
   - `marketplace.json`'s `plugins[].source` is a `string | object` union
   - The minimal form for pointing at a plugin in the same repo is `"source": "./"` (resolves to the repo root, NOT to under `.claude-plugin/`)
   - Reflected in: newly added `.claude-plugin/marketplace.json`

3. **Minimum required fields for marketplace.json**
   - top-level: `name` (kebab-case) / `owner` (object, `name` required) / `plugins` (array)
   - Required for a plugins entry: `name` / `source`
   - Reflected in: `.claude-plugin/marketplace.json`

4. **Version resolution order is `plugin.json` > `marketplace.json` > git SHA**
   - If you write a version in both, plugin.json silently wins (there is a warning in the official docs)
   - This plugin's policy is to manage version in `plugin.json` only
   - Reflected in: `docs/DESIGN.md` §14.3 Update flow

### Open

- **Whether a marketplace-less direct install (`/plugin add owner/repo` etc.) exists** — unconfirmed in the official docs. Real-environment verify in Phase A-11 is recommended, but the current marketplace flow already achieves the goal, so this is low priority

---

## 2026-05-16 — Claude Code started sending `permission_mode` on all events, causing engine misdetection

### Context

The `hooks/_runner.py::_detect_engine` introduced in v0.7.0 used the heuristic "the `permission_mode` field is present = Codex". At the time that field existed only in the Codex schema. But during the v0.16.x period Claude Code also started carrying `permission_mode: "auto"` on all events, so every Claude Code event was being **misdetected as Codex engine → normalized through the codex adapter**.

### Primary sources

- `~/.claude/plugins/data/agent-output-tracer-itosdad-agent-output-tracer/sessions/781ff3fa-9a21-4107-ad31-d089ecd1ee56/events.jsonl`
- `raw_event` keys for all 40 `agent_response` events:
  `['cwd', 'hook_event_name', 'last_assistant_message', 'permission_mode', 'session_id', 'stop_hook_active', 'transcript_path']`
- `hook_event_name` is CamelCase `Stop` → Claude Code, yet still carries `permission_mode`

### Observations

1. **Not visibly broken, but the engine field was pinned to codex for every record**
   - Both adapters read `last_assistant_message`, so `agent_response_text` was populated
   - But `metadata.engine = "codex"` was burned in at the first event, breaking theme auto-detect,
     anomaly counters, and the per-engine breakdown of the tool mix

2. **The truly robust discriminator is the casing of `hook_event_name`**
   - Codex: snake_case (`stop`, `pre_tool_use`)
   - Claude Code: CamelCase (`Stop`, `PreToolUse`)
   - Judging by field presence breaks when the engine changes its spec, but historically neither engine has moved the casing
   
3. **Reflected: in v0.16.1, casing was promoted to the primary signal and `permission_mode` was demoted to a tail fallback**
   - `hooks/_runner.py::_detect_engine`
   - `tests/integration/test_codex_hook_scripts.py::test_engine_detection_claude_payload_with_permission_mode`

---

## 2026-05-16 — Stale `metadata.engine` throws off the Timeline theme

### Context

Even after the v0.16.1 engine detector fix, sessions recorded before it still had `engine: "codex"` burned into `metadata.json` from the misdetection. `core/recorder.py` writes metadata.engine exactly once at the first event and never updates it afterward, so after the fix the metadata.engine of old sessions remains permanently wrong.

`tui/screens/timeline.py::_sync_theme_to_engine` was reading metadata.engine, so every time a Claude Code session's Timeline was opened, the theme was forced back to Codex on every reload, overwriting the user's choice even when they had picked salmon via `t`.

### Observations

1. **metadata is first-write-wins. Wrong values persist**
   - There is currently no path that rebuilds or migrates it after the fact
   - The same class of issue can latently affect fields other than engine

2. **Theme judgment should be made from events, not from metadata**
   - Added `tui/screens/timeline.py::_majority_engine(events)`; it decides the engine by majority vote over the events array and is not affected by stale metadata
   - Reflected in: v0.16.2

3. **The `user_theme_override` flag is a separate matter**
   - Introduced in v0.15.0 to protect manual `t` switching. Orthogonal to this fix

---

## 2026-05-16 — TUI alignment symptom of centering content vertically on screen

### Context

On screens with short content such as Stats / Doctor / Trace / Search / Config, the body was being displayed vertically centered in the viewport. Full-height screens like Timeline had no issue.

### Observations

1. **Textual's Container defaults to vertical centering for short content**
   - Unless you explicitly specify `align: left top`, it is placed in the viewport center
   - For long content `height: 1fr` takes effect, so the issue does not surface

2. **Reflected: in v0.16.2, `align: left top; content-align: left top;` was made explicit on `AOTScreen > .body` and the nested
   `Vertical` wrapper in `tui/themes/base.tcss`**

---

### Operating rules

- If real-environment verification finds "this differs from the design doc / code", add one block here
- Specify the reflection target (doc / code path) so that later you can trace "where was this observation reflected?"
- Always record primary sources (events.jsonl, metadata.json, session_id, etc.) for reproducibility
- For "Open" items, write down the next verify trigger (a Phase number or a condition)
- This is a log, not the source of truth. The source of truth is `README.md` / `docs/TUI.md` / the code itself
  (`docs/DESIGN.md` / `docs/DESIGN_FORENSIC_UX.md` are historical baselines)
