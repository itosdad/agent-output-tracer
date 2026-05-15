# Install

`agent-output-tracer` ships as a plugin for both **Claude Code** and **Codex
CLI**. The runtime hooks themselves are pure Python stdlib (3.9+ compatible)
so they run with whatever `python3` is on the user's `PATH`. The CLI tool
(`agent-output-tracer ...`) targets **Python 3.11+**.

## Claude Code — install from GitHub (recommended)

This repo is configured to serve as a one-plugin personal marketplace, so the
two-step Claude Code marketplace flow works directly against it.

In a Claude Code session, run:

```
/plugin marketplace add itosdad/agent-output-tracer
/plugin install agent-output-tracer@itosdad-agent-output-tracer
```

What this does:

1. `/plugin marketplace add` clones the repo, reads
   `.claude-plugin/marketplace.json`, and registers the catalog.
2. `/plugin install <name>@<marketplace>` installs the listed plugin.

Verify with `/plugin` — `agent-output-tracer` should be listed as enabled
with 5 hooks (UserPromptSubmit / PreToolUse / PostToolUse / Stop /
SessionEnd) registered.

To update later (after the upstream repo cuts a new release):

```
/plugin update agent-output-tracer@itosdad-agent-output-tracer
```

Version is resolved from `plugin.json` (`version: 0.1.0` etc.); the project
bumps it whenever there's something users should re-fetch.

### Install the CLI (`agent-output-tracer` binary, optional)

The plugin captures sessions without the CLI. The CLI is needed only for
the user-facing `replay` / `grep` / `state-at` / `list` / `latest` commands.

```bash
pipx install git+https://github.com/itosdad/agent-output-tracer.git@v0.1.0
# or, for local development:
git clone https://github.com/itosdad/agent-output-tracer ~/work/agent-output-tracer
cd ~/work/agent-output-tracer
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Claude Code — local-path / dev mode

For working on the plugin itself, skip the marketplace flow and load the
repo directly. Useful when iterating on `hooks/` or `query/` code: hot
reload with `/reload-plugins`, no version bump needed.

```bash
git clone https://github.com/itosdad/agent-output-tracer ~/work/agent-output-tracer
cd ~/work/agent-output-tracer
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

claude --plugin-dir ~/work/agent-output-tracer
```

After edits in `~/work/agent-output-tracer/`, run `/reload-plugins` inside
the Claude Code session to pick the new code up without restarting.

### 4. Verify

Start a Claude Code session that triggers at least one tool call, exit it
with `/exit`, then locate the captured events:

```bash
find ~/.claude -name 'events.jsonl' 2>/dev/null
```

You should see one path per session, e.g.:

```
~/.claude/plugins/data/agent-output-tracer/sessions/<UUID>/events.jsonl
```

The directory above `sessions/` is your `${CLAUDE_PLUGIN_DATA}`. Pass it to
the CLI:

```bash
export CLAUDE_PLUGIN_DATA=~/.claude/plugins/data/agent-output-tracer
agent-output-tracer list
agent-output-tracer replay --session latest
```

The `replay` timeline should show your prompt, the tool calls it triggered
(with byte counts), the agent's response, and a `[session_end]` marker.

#### Dev mode caveat (`--plugin-dir`)

When the plugin is loaded via `claude --plugin-dir <path>` rather than
installed, the data directory name has an `-inline` suffix:

```
~/.claude/plugins/data/agent-output-tracer-inline/sessions/<UUID>/
```

This is a Claude Code convention to keep dev-mode runs separate from
installed-plugin runs. Same schema inside; only the directory name differs.

#### Session id format

Session ids are Claude Code-issued UUID v4 strings, e.g.
`ba640ad4-5982-4601-8bed-69164fd10851`. The CLI accepts the full id, a unique
prefix of ≥4 chars (`agent-output-tracer replay --session ba64`), or shortcuts
like `latest` / `latest-N` / `YYYY-MM-DD`.

### 5. Uninstall / disable

```bash
claude plugin disable agent-output-tracer            # temporary
claude plugin uninstall agent-output-tracer          # remove plugin + data
claude plugin uninstall agent-output-tracer --keep-data
```

## Codex CLI

### Version requirement

| feature | min Codex version |
|---|---|
| plugin-bundled hooks | **0.128** |
| `PreCompact` / `PostCompact` capture | **0.129** |
| `/hooks` TUI | 0.129 |

This plugin captures `PreCompact` / `PostCompact` when present but degrades
gracefully — sessions on 0.128 just won't see those event rows.

### 1. Enable the feature flag (required)

Without this, Codex silently ignores `hooks/hooks.json`. There is no
error message; events simply never fire.

```bash
mkdir -p ~/.codex
cat >> ~/.codex/config.toml <<'EOF'
[features]
codex_hooks = true   # 0.129+ also accepts the alias `hooks = true`
EOF
```

### 2. Install via marketplace (recommended)

```
codex plugin marketplace add itosdad/agent-output-tracer
codex plugin marketplace add itosdad/agent-output-tracer --ref main   # pin to a branch
```

Local repo install (development):

```
codex plugin marketplace add ~/work/agent-output-tracer
```

Codex resolves the plugin into
`~/.codex/plugins/cache/$MARKETPLACE_NAME/agent-output-tracer/$VERSION/`
(`$VERSION = "local"` for local-repo installs).

### 3. Trust the project (project-local hooks only)

If you're loading hooks at the project layer rather than user-global,
Codex requires the `.codex/` directory to be trusted:

```
codex trust add .   # run inside the host repo
```

User-global install (the default for marketplace add) skips this step.

### 4. Verify

Start a Codex session, type a prompt that triggers any tool call, then:

```bash
find ~/.codex -name 'events.jsonl' 2>/dev/null
# or, if CODEX_PLUGIN_DATA is exported:
find "$CODEX_PLUGIN_DATA" -name 'events.jsonl'
```

You should see one path per session, e.g.:

```
~/.codex/plugins/data/agent-output-tracer/sessions/<session_id>/events.jsonl
```

CLI usage is identical to the Claude Code flow — point `--data-dir` at the
plugin data root:

```bash
agent-output-tracer --data-dir ~/.codex/plugins/data/agent-output-tracer list
agent-output-tracer --data-dir ~/.codex/plugins/data/agent-output-tracer replay --session latest
```

### Codex-specific captures

| event | Codex hook_event_name | normalized event_type |
|---|---|---|
| Session opened | `session_start` | `session_start` (Claude Code does not subscribe) |
| User prompt | `user_prompt_submit` | `user_prompt` |
| Pre tool | `pre_tool_use` | `pre_tool` |
| Post tool (Bash / `apply_patch` / MCP only) | `post_tool_use` | `post_tool` |
| Agent response | `stop` | `agent_response` |
| Compaction begin (0.129+) | `pre_compact` | `compact_pre` |
| Compaction end (0.129+) | `post_compact` | `compact_post` |

Codex's `permission_request` event is observed by Codex but **not**
recorded (forensic replay doesn't need it; design §3.2.2).

### Codex caveats

- **No `session_end` event**: Codex doesn't emit one. `metadata.json` is
  rewritten on every appended event, so `tool_calls_total` / `ts_end` /
  byte counters stay current without a finalize step.
- **PostToolUse limited**: only fires for `Bash`, `apply_patch`, and MCP
  tool calls. Internal Read-equivalents won't show a `post_tool` row, so
  the `result_bytes` / `tool_response` forensic surface is thinner than
  on Claude Code. Pre/post pairing is best-effort.
- **Env var resolution**: the runtime resolves the plugin data dir in
  this order: `--data-dir` arg → `CLAUDE_PLUGIN_DATA` env → `CODEX_PLUGIN_DATA`
  env → `~/.codex/plugins/data/agent-output-tracer/` (if it exists). Codex
  currently uses the Claude-compat layer's `${CLAUDE_PLUGIN_ROOT}` to
  resolve the hook script path in `hooks.json`; if a future Codex release
  ships a native `${CODEX_PLUGIN_ROOT}`, just export `CODEX_PLUGIN_DATA`
  to point at the data dir and everything else keeps working.

## Troubleshooting

- **No `_install_verify.jsonl` after a session**: confirm the plugin is
  enabled (`claude plugin list`), and that `${CLAUDE_PLUGIN_DATA}` resolves
  (the hook records it for you on every fire — if even one line ever
  appeared, the env var is fine).
- **`python3: command not found`**: install Python 3 system-wide. macOS
  Monterey+ ships 3.9 by default, which is enough for the hooks.
- **Hooks fire but `_install_verify.jsonl` stays empty**: the hook scripts
  may not have write permission on `${CLAUDE_PLUGIN_DATA}`. The script will
  exit 0 silently in this case (agent must never be blocked). Check
  `ls -la "$CLAUDE_PLUGIN_DATA"` for write bits.
