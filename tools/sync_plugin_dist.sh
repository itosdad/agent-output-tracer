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

case "$MODE" in
  sync|"")
    rm -rf "$DIST"
    for src in "${sources[@]}"; do sync_one "$src"; done
    echo "synced $DIST/ from canonical sources"
    ;;
  --check)
    tmp=$(mktemp -d)
    trap 'rm -rf "$tmp"' EXIT
    cp -R "$DIST" "$tmp/dist-before"
    rm -rf "$DIST"
    for src in "${sources[@]}"; do sync_one "$src"; done
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
