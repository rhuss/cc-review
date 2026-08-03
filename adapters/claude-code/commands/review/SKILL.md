---
name: review
description: Multi-agent code review with autonomous fix loop
argument-hint: "[--pr <number>] [--spec <path>] [--hints <path>] [--output <path>] [--no-fix] [--no-external] [--parallel] [--sequential]"
---

# Review

Locate cc-review core and delegate to `core/commands/review.md`.

## Core Resolution

Find the cc-review core directory by checking these paths in order:
1. `../../../../core` (relative to this file, for development installs)
2. `.cc-review/core` (project-local install)
3. `~/.cc-review/core` (user-global install)

Read the first path that contains `commands/review.md`. If none found, report:
"cc-review core not found. Run the install script or set up .cc-review/core."

## Execution

Read and execute `core/commands/review.md` from the resolved core path.

Pass through all arguments from the user's invocation:
- `--pr <number>`: Target PR number
- `--spec <path>`: Specification file path
- `--hints <path>`: Review hints file
- `--output <path>`: Output report path
- `--no-fix`: Skip autonomous fix loop
- `--no-external`: Skip external tool integration
- `--parallel`: Run review agents in parallel
- `--sequential`: Run review agents sequentially
