---
name: review
description: Multi-agent code review with autonomous fix loop
argument-hint: "[--pr <number>] [--spec <path>] [--hints <path>] [--output <path>] [--config <path>] [--profile <name>] [--no-fix] [--no-external] [--no-coderabbit] [--no-copilot] [--no-codex] [--parallel] [--sequential]"
---

# Review

Locate cc-review core and delegate to `core/commands/review.md`.

## Core Resolution

Find the cc-review core directory by checking these paths in order:
1. `./core` relative to this plugin's root directory
2. `.cc-review/core` in the current project
3. `~/.cc-review/core` in the user's home directory

Read the first path that contains `commands/review.md`. If none found, report:
"cc-review core not found. Install the plugin or set up .cc-review/core."

## Execution

Read and execute `core/commands/review.md` from the resolved core path.

Pass through all arguments from the user's invocation:
- `--pr <number>`: Target PR number
- `--spec <path>`: Specification file path
- `--hints <path>`: Review hints file
- `--output <path>`: Output report path
- `--config <path>`: Explicit config file path
- `--profile <name>`: Profile preset name (ci, thorough, quick)
- `--no-fix`: Skip autonomous fix loop
- `--no-external`: Skip external tool integration
- `--no-coderabbit` / `--no-copilot` / `--no-codex`: Disable individual tools
- `--parallel`: Run review agents in parallel
- `--sequential`: Run review agents sequentially
