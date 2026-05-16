#!/usr/bin/env bash
# Sync canonical plugin sources at the repo root into ./plugin-dist/.
#
# Why this exists:
#   Codex 0.130's plugin resolver rejects `marketplace.json` entries whose
#   `source` resolves to an empty path. Our plugin's actual code (hooks/,
#   adapters/, core/) lives at the repo root because the CLI / TUI side
#   imports the same packages, so we can't just move the plugin into a
#   subdirectory without rewriting every CLI import path.
#   Instead, ./plugin-dist/ holds a self-contained copy of just the
#   plugin's footprint, and both .claude-plugin/marketplace.json and
#   .codex-plugin/marketplace.json point to it. Claude is happy with
#   the non-root path; Codex is happy that the path is non-empty.
#
# Run this whenever you edit hooks/, adapters/, core/, or either
# `plugin.json`. CI verifies the dist is in sync (see .github/workflows).
#
# Usage:
#   bash tools/sync_plugin_dist.sh           # sync (default)
#   bash tools/sync_plugin_dist.sh --check   # exit 1 if dist drifts

set -euo pipefail

cd "$(dirname "$0")/.."

DIST=plugin-dist
MODE="${1:-sync}"

sources=(
  "hooks"
  "adapters"
  "core"
  ".claude-plugin/plugin.json"
  ".codex-plugin/plugin.json"
)

sync_one() {
  local src=$1
  local dst="$DIST/$src"
  if [[ -d "$src" ]]; then
    mkdir -p "$dst"
    rsync -a --delete --exclude='__pycache__' "$src"/ "$dst"/
  else
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
  fi
}

# Codex 0.130 looks for hooks at the plugin root (`./hooks.json`), not in
# the `hooks/` subdir (which is Claude's convention). It also runs hook
# commands with CWD = plugin root, so it doesn't substitute the
# `${CLAUDE_PLUGIN_ROOT}` env var that Claude's hooks.json relies on.
# Generate a Codex-shaped variant of the same hook configuration by
# rewriting that env var to `.` and placing the result at
# `plugin-dist/hooks.json`. The Python scripts referenced by both
# variants are identical (they recover the plugin root via `__file__`).
emit_codex_hooks_json() {
  python3 -c '
import json, sys
src, dst = sys.argv[1], sys.argv[2]
with open(src) as f:
    data = json.load(f)
def rewrite(obj):
    if isinstance(obj, dict):
        return {k: rewrite(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [rewrite(v) for v in obj]
    if isinstance(obj, str):
        return obj.replace("${CLAUDE_PLUGIN_ROOT}", ".")
    return obj
with open(dst, "w") as f:
    json.dump(rewrite(data), f, indent=2)
    f.write("\n")
' "hooks/hooks.json" "$DIST/hooks.json"
}

case "$MODE" in
  sync|"")
    rm -rf "$DIST"
    for src in "${sources[@]}"; do sync_one "$src"; done
    emit_codex_hooks_json
    echo "synced $DIST/ from canonical sources"
    ;;
  --check)
    tmp=$(mktemp -d)
    trap 'rm -rf "$tmp"' EXIT
    cp -R "$DIST" "$tmp/dist-before"
    rm -rf "$DIST"
    for src in "${sources[@]}"; do sync_one "$src"; done
    emit_codex_hooks_json
    if ! diff -r "$tmp/dist-before" "$DIST" >/dev/null 2>&1; then
      echo "drift detected: $DIST/ is out of sync with canonical sources" >&2
      diff -r "$tmp/dist-before" "$DIST" >&2 || true
      # Restore the on-disk state so we don't surprise the user
      rm -rf "$DIST"
      cp -R "$tmp/dist-before" "$DIST"
      exit 1
    fi
    echo "ok: $DIST/ is in sync"
    ;;
  *)
    echo "usage: $0 [--check]" >&2
    exit 2
    ;;
esac
