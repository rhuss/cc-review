#!/usr/bin/env bash
set -euo pipefail

# Install cc-review commands for OpenCode.
# Copies command files to .opencode/plugins/cc-review/ in the target project.
# Usage: ./install.sh [--project-dir <path>]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_DIR="."

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-dir) PROJECT_DIR="$2"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

TARGET="$PROJECT_DIR/.opencode/plugins/cc-review"
mkdir -p "$TARGET/command"

# Copy command files
for cmd in "$SCRIPT_DIR/command"/*.md; do
  [ -f "$cmd" ] || continue
  cp "$cmd" "$TARGET/command/"
done

# Create a pointer to the core directory so commands can resolve it
echo "$PLUGIN_DIR/core" > "$TARGET/.core-path"

echo "cc-review commands installed for OpenCode at $TARGET"
echo "Core path: $PLUGIN_DIR/core"
