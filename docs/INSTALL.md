# Install

`agent-output-tracer` ships in three independent layers. Install only
the layers you need.

| Layer | Owner | Purpose |
|---|---|---|
| **Plugin** | Claude Code / Codex CLI | Records every session via hooks → events.jsonl |
| **CLI** | Python venv or pipx | Reads recorded data: `aot replay` / `grep` / `trace` / etc. |
| **TUI (optional extra)** | Same Python install as CLI | `aot tui` — side-channel forensic UI |

## Prerequisites

| Need | Python | Notes |
|---|---|---|
| Run the plugin hooks (record sessions) | **3.9+** | Whatever `python3` is on `PATH` works; macOS system Python qualifies |
| Run the CLI (`aot replay`, …) | **3.11+** | `pipx` typically uses your default `python3`; check with `pipx environment` |
| Run the TUI (`aot tui`) | **3.10+** | Bound by `textual`'s minimum |

The plugin layer has zero third-party deps. The CLI layer has zero
third-party deps in its default install. The TUI extra brings
`textual` + `watchdog` (and their transitives).

---

## Plugin — Claude Code

### Marketplace install (recommended)

In a Claude Code session, run:

```
/plugin marketplace add itosdad/agent-output-tracer
/plugin install agent-output-tracer@itosdad-agent-output-tracer
```

What happens:

1. `/plugin marketplace add` clones the repo, reads
   `.claude-plugin/marketplace.json`, registers the catalog.
2. `/plugin install <name>@<marketplace>` enables the plugin and wires
   its hooks.

Verify with `/plugin` — `agent-output-tracer` should be listed as
enabled with **8 hooks** registered:
`SessionStart` / `UserPromptSubmit` / `PreToolUse` / `PostToolUse` /
`Stop` / `SessionEnd` / `PreCompact` / `PostCompact`.

### Dev mode (`--plugin-dir`)

For working on the plugin itself, skip the marketplace flow and load
the repo directly — hot-reload with `/reload-plugins`, no version bump
needed.

```bash
git clone https://github.com/itosdad/agent-output-tracer ~/work/agent-output-tracer
cd ~/work/agent-output-tracer
claude --plugin-dir ~/work/agent-output-tracer
```

After source edits, run `/reload-plugins` inside Claude Code to pick
up the new code without restarting.

**Caveat — `-inline` suffix:** dev-mode runs land under
`~/.claude/plugins/data/agent-output-tracer-inline/sessions/<UUID>/`,
NOT `agent-output-tracer/sessions/`. The schema is identical; only
the directory name differs. Convention is enforced by Claude Code to
keep dev experiments out of your installed-plugin data.

### Update

```
/plugin update agent-output-tracer@itosdad-agent-output-tracer
```

The new version is resolved from `.claude-plugin/plugin.json`. The
project bumps it whenever there's something users should re-fetch.

### Disable / uninstall

```bash
claude plugin disable agent-output-tracer            # temporary
claude plugin uninstall agent-output-tracer          # remove plugin AND its data
claude plugin uninstall agent-output-tracer --keep-data
```

---

## Plugin — Codex CLI

### Version requirement

| Feature | Min Codex version |
|---|---|
| plugin-bundled hooks | **0.128** |
| `PreCompact` / `PostCompact` capture | **0.129** |
| `/hooks` TUI inside Codex | 0.129 |

This plugin captures `PreCompact` / `PostCompact` when present but
degrades gracefully — sessions on 0.128 just won't see those event
rows.

### 1. Enable the feature flag (required)

Without this, Codex **silently** ignores `hooks/hooks.json`. There is
no error; events simply never fire.

```bash
mkdir -p ~/.codex
cat >> ~/.codex/config.toml <<'EOF'
[features]
codex_hooks = true   # 0.129+ also accepts `hooks = true` as an alias
EOF
```

### 2. Install via marketplace

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

User-global install (the default of `codex plugin marketplace add`)
skips this step.

### Update

```
codex plugin marketplace update itosdad-agent-output-tracer
```

### Uninstall

```
codex plugin remove agent-output-tracer
```

---

## CLI (`agent-output-tracer` / `aot`)

The plugin captures sessions on its own. The CLI is what you point at
the captured data to read it back: `aot replay`, `aot trace`,
`aot find`, etc. Install once — it's engine-agnostic.

Two console scripts are installed: `agent-output-tracer` (canonical
name) and `aot` (short alias). They are interchangeable.

### End-user install (pipx, recommended)

```bash
pipx install 'git+https://github.com/itosdad/agent-output-tracer.git@v0.6.0'
```

### Editable / dev install

```bash
git clone https://github.com/itosdad/agent-output-tracer ~/work/agent-output-tracer
cd ~/work/agent-output-tracer
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

`[dev]` adds `pytest`, `pytest-cov`, and `ruff` for running the test
suite.

### Update

pipx:
```bash
pipx upgrade agent-output-tracer
# or pin to a specific tag:
pipx install --force 'git+https://github.com/itosdad/agent-output-tracer.git@v0.6.0'
```

Editable install:
```bash
cd ~/work/agent-output-tracer
git pull
pip install -e ".[dev]"   # only needed if pyproject changed
```

### Uninstall

```bash
pipx uninstall agent-output-tracer
# or, for editable:
pip uninstall agent-output-tracer
```

---

## Optional extra: `[tui]` — side-channel TUI

The `aot tui` command opens a textual-based interactive UI that
follows `events.jsonl` live, in its own pane. Best run alongside
Claude Code / Codex in a tmux split or iTerm pane.

**Without this extra installed, every other CLI command keeps working**;
only `aot tui` is gated. Running `aot tui` without the extra prints
the standard 3-line error pointing at the install command.

### Add the extra to an existing install

pipx (replaces the existing install with the extra wired in):
```bash
pipx install --force \
  'git+https://github.com/itosdad/agent-output-tracer.git@v0.6.0#egg=agent-output-tracer[tui]'
```

Or inject `textual` / `watchdog` into the existing pipx env:
```bash
pipx inject agent-output-tracer textual watchdog
```

Editable / venv install:
```bash
cd ~/work/agent-output-tracer
source .venv/bin/activate
pip install -e ".[tui]"          # TUI only
pip install -e ".[dev,tui]"      # tests + TUI
```

### Verify the extra resolved

```bash
python -c "from tui import is_available; print(is_available())"
# → True means textual import succeeded
aot tui --help                   # subcommand help renders
```

### Launch

```bash
aot tui                          # opens against `latest` session
aot tui --session a3f2           # specific session
aot tui --data-dir ~/.codex/plugins/data/agent-output-tracer
```

Keybindings (subset; more land incrementally):

| Key | Action |
|---|---|
| `j` / `↓` | Next event in timeline |
| `k` / `↑` | Previous event |
| `g` / `G` | Jump to top / bottom |
| `s` | Session picker (switch sessions) |
| `r` | Reload session list + timeline |
| `o` | Toggle live follow on the current session |
| `/` | Filter timeline by substring |
| `q` / `Esc` | Quit |

### Recommended runtime layout

iTerm split:
```
Cmd+D (vertical split) → right pane:
$ aot tui
Left pane stays in Claude Code / Codex for the actual session.
```

tmux:
```bash
tmux new-session -s aot
# Ctrl+b " (horizontal split) or % (vertical split)
# In one pane:
$ aot tui
```

### Remove the extra

pipx:
```bash
pipx uninject agent-output-tracer textual
pipx uninject agent-output-tracer watchdog
```

Editable / venv:
```bash
pip uninstall textual watchdog
```

The `pyproject.toml` entry stays — you can re-install the extra any
time with the same command.

---

## Plugin data directory

The plugin writes everything under one directory per engine. Both the
hooks and the CLI resolve this directory in the same order:

1. `--data-dir <path>` (CLI flag, highest priority)
2. `CLAUDE_PLUGIN_DATA` env (set automatically by Claude Code)
3. `CODEX_PLUGIN_DATA` env (set manually — Codex doesn't auto-export)
4. `~/.codex/plugins/data/agent-output-tracer/` (fallback when neither env is set and the directory exists)

Typical absolute paths:

| Engine | Path |
|---|---|
| Claude Code (installed) | `~/.claude/plugins/data/agent-output-tracer/` |
| Claude Code (dev mode) | `~/.claude/plugins/data/agent-output-tracer-inline/` |
| Codex (installed) | `~/.codex/plugins/data/agent-output-tracer/` |

To point the CLI at a specific engine's data when both are installed:

```bash
# implicit (use CLAUDE_PLUGIN_DATA from the shell)
export CLAUDE_PLUGIN_DATA=~/.claude/plugins/data/agent-output-tracer
aot list

# explicit
aot --data-dir ~/.codex/plugins/data/agent-output-tracer list
```

### Verify the first session

After a Claude Code / Codex session that triggered at least one tool
call:

```bash
find ~/.claude ~/.codex -name 'events.jsonl' 2>/dev/null
```

You should see one path per session, e.g.:

```
~/.claude/plugins/data/agent-output-tracer/sessions/<session_id>/events.jsonl
```

Then:

```bash
aot list
aot replay --session latest
```

A clean replay timeline confirms the whole pipeline (engine hook →
adapter → recorder → CLI) is wired.

---

## Engine-specific data shape

### Claude Code

The plugin subscribes to 5 hook events and records them under the
normalized `event_type` listed below:

| Claude Code hook | normalized `event_type` |
|---|---|
| `UserPromptSubmit` | `user_prompt` |
| `PreToolUse` | `pre_tool` |
| `PostToolUse` | `post_tool` |
| `Stop` | `agent_response` |
| `SessionEnd` | `session_end` |

`SessionStart` / `PreCompact` / `PostCompact` are registered for the
Codex side; Claude Code may fire them but the Claude adapter
intentionally drops them (the schema for those events isn't useful in
the Claude Code data we record).

### Codex CLI

| Codex `hook_event_name` | normalized `event_type` |
|---|---|
| `session_start` | `session_start` |
| `user_prompt_submit` | `user_prompt` |
| `pre_tool_use` | `pre_tool` |
| `post_tool_use` | `post_tool` (Bash / `apply_patch` / MCP only) |
| `stop` | `agent_response` |
| `pre_compact` | `compact_pre` (≥ 0.129) |
| `post_compact` | `compact_post` (≥ 0.129) |

Codex's `permission_request` event is observed by Codex but **not**
recorded (forensic replay doesn't need it).

### Codex-specific caveats

- **No `session_end` event**: Codex doesn't emit one. `metadata.json`
  is rewritten on every appended event, so `ts_end` and counters stay
  current without a finalize step.
- **PostToolUse limited**: only fires for `Bash`, `apply_patch`, and
  MCP tool calls. Internal Read-equivalents won't show a `post_tool`
  row, so the `result_bytes` / `tool_response` surface is thinner
  than on Claude Code. Pre/post pairing is best-effort.

### Session id format

Session ids are engine-issued (typically UUID v4 strings, e.g.
`ba640ad4-5982-4601-8bed-69164fd10851`). The CLI accepts:

- the full id
- a unique prefix of ≥ 4 chars (`aot replay --session ba64`)
- `latest` / `latest-N` shortcuts
- `YYYY-MM-DD` for the most recent session on that date

---

## Troubleshooting

### Plugin appears installed but nothing is recorded

1. Confirm the plugin shows up in the engine:
   - Claude Code: `/plugin` should list it as enabled
   - Codex: `codex plugin list` should include it AND
     `~/.codex/config.toml` must have `[features] codex_hooks = true`
2. Trigger a tool call and check the data dir:
   ```bash
   find ~/.claude ~/.codex -name 'events.jsonl' 2>/dev/null
   ```
3. If nothing appears, run `aot doctor` for a structured self-check
   (runtime / data dir / sessions / hooks wiring).

### `python3: command not found` from hooks

Install Python 3 system-wide. macOS Monterey+ ships 3.9 by default,
which is enough for the hooks. The CLI requires 3.11+ separately.

### Hooks fire but events.jsonl never appears

The hook process may not have write permission on the plugin data
directory. Hooks exit 0 silently in that case (the agent must never
be blocked). Check:

```bash
ls -la "$CLAUDE_PLUGIN_DATA"
```

and ensure your user has write bits on the resolved directory.

### `aot tui` errors with "requires optional dependencies"

The `[tui]` extra isn't installed. Run the install step in
[Optional extra: `[tui]`](#optional-extra-tui--side-channel-tui).

### `aot tui` launches but crashes immediately

Check `aot doctor` first. Common causes:
- terminal doesn't support 256-color / unicode well — try a different
  terminal (iTerm2, Alacritty, kitty)
- `textual` version too old: `pip install --upgrade 'textual>=0.50'`

### CLI reads a different data dir than expected

The CLI may be hitting a stale `CLAUDE_PLUGIN_DATA` from your shell.
Force the right one with `--data-dir`:

```bash
aot --data-dir ~/.claude/plugins/data/agent-output-tracer list
```

`aot doctor` prints which directory it resolved and how.
