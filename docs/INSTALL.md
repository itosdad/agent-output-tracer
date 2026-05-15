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

Start a Claude Code session that triggers at least one tool call, then check
the plugin data directory:

```bash
# In Claude Code's resolved plugin data dir:
ls "$CLAUDE_PLUGIN_DATA/" 2>/dev/null || \
  echo "Look under ~/.claude/plugins/data/agent-output-tracer/ (or similar)"

cat "$CLAUDE_PLUGIN_DATA/_install_verify.jsonl" | head -3
```

You should see one line per hook fire (UserPromptSubmit / PreToolUse /
PostToolUse / Stop / SessionEnd) with `session_id`, `hook_event_name`, and the
resolved `plugin_root_env` / `plugin_data_env`.

**Phase A-1 behavior**: the plugin only writes `_install_verify.jsonl`. Real
session recording lands in Phase A-3. The verify file is what confirms the
hook plumbing is connected.

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
