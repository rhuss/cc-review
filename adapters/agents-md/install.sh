#!/usr/bin/env bash
set -euo pipefail

# Install cc-review AGENTS.md fragment into the project or user config.
# Usage: ./install.sh [--global] [--project-dir <path>]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRAGMENT="$SCRIPT_DIR/AGENTS.md"
PROJECT_DIR="."

while [[ $# -gt 0 ]]; do
  case "$1" in
    --global) PROJECT_DIR="$HOME"; shift ;;
    --project-dir) PROJECT_DIR="$2"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

TARGET="$PROJECT_DIR/AGENTS.md"

if [[ -f "$TARGET" ]]; then
  if grep -q "cc-review: Multi-Agent Code Review" "$TARGET"; then
    echo "cc-review section already present in $TARGET"
    exit 0
  fi
  echo "" >> "$TARGET"
  cat "$FRAGMENT" >> "$TARGET"
  echo "Appended cc-review section to $TARGET"
else
  cp "$FRAGMENT" "$TARGET"
  echo "Created $TARGET with cc-review section"
fi
