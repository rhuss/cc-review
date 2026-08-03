#!/usr/bin/env bash
set -euo pipefail

# Install cc-review commands into Claude Code commands directory.
# Usage: ./install.sh [--global] [--project-dir <path>]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ADAPTER_COMMANDS="$SCRIPT_DIR/commands"
GLOBAL=false
PROJECT_DIR="."

while [[ $# -gt 0 ]]; do
  case "$1" in
    --global) GLOBAL=true; shift ;;
    --project-dir) PROJECT_DIR="$2"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

if $GLOBAL; then
  TARGET="$HOME/.claude/commands"
else
  TARGET="$PROJECT_DIR/.claude/commands"
fi

# Verify core is accessible from the adapter
if [[ ! -d "$SCRIPT_DIR/../../core/commands" ]]; then
  echo "Warning: cc-review core not found at expected path." >&2
  echo "Commands will resolve core at runtime via fallback paths." >&2
fi

mkdir -p "$TARGET"

for cmd_dir in "$ADAPTER_COMMANDS"/*/; do
  cmd_name="$(basename "$cmd_dir")"
  if [[ -f "$cmd_dir/SKILL.md" ]]; then
    mkdir -p "$TARGET/$cmd_name"
    ln -sf "$cmd_dir/SKILL.md" "$TARGET/$cmd_name/SKILL.md"
    echo "Linked: $cmd_name -> $TARGET/$cmd_name/SKILL.md"
  fi
done

echo "cc-review commands installed to $TARGET"
