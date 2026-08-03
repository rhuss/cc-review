#!/usr/bin/env bash
set -euo pipefail

# Install cc-review as a spec-kit extension.
# Usage: ./install.sh [--dev]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEV_FLAG=""

if [[ "${1:-}" == "--dev" ]]; then
  DEV_FLAG="--dev"
fi

if ! command -v specify &>/dev/null; then
  echo "Error: 'specify' CLI not found. Install spec-kit first." >&2
  exit 1
fi

specify extension add "$SCRIPT_DIR" $DEV_FLAG

echo "cc-review extension installed via spec-kit."
echo "Commands available: speckit.cc-review.review, speckit.cc-review.triage"
