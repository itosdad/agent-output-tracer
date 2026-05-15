# Install

`agent-output-tracer` ships as a plugin for both **Claude Code** and **Codex
CLI**. The runtime hooks themselves are pure Python stdlib (3.9+ compatible)
so they run with whatever `python3` is on the user's `PATH`. The CLI tool
(`agent-output-tracer ...`) targets **Python 3.11+**.

## Claude Code

### 1. Clone

```bash
git clone <repo-url> ~/work/agent-output-tracer
cd ~/work/agent-output-tracer
```

### 2. (optional) Install the CLI

Required for the user-facing `agent-output-tracer replay / grep / ...`
commands. Not required for the hook capture path to work.

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

### 3. Install the plugin

```bash
claude plugin install ~/work/agent-output-tracer
```

Or, for hot-reload development:

```bash
claude --plugin-dir ~/work/agent-output-tracer
```

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

> Codex support lands in Phase C. The directory layout is in place
> (`.codex-plugin/plugin.json`) but the adapter is not yet implemented and
> hook capture under Codex will not produce useful events until then.

When Phase C is complete:

```bash
# 1. Enable the feature flag (required; without it hooks are silently ignored)
cat >> ~/.codex/config.toml <<'EOF'
[features]
codex_hooks = true
EOF

# 2. Install via local marketplace
codex plugin marketplace add ~/work/agent-output-tracer
```

Codex plugin installs under
`~/.codex/plugins/cache/$MARKETPLACE_NAME/agent-output-tracer/local/`.

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
