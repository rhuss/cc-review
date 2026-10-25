---
name: review
description: Multi-agent code review with autonomous fix loop
argument-hint: "[--pr <number>] [--spec <path>] [--hints <path>] [--output <path>] [--config <path>] [--profile <name>] [--no-fix] [--max-rounds <n>] [--no-external] [--external] [--no-<reviewer>] [--only <reviewer,...>] [--no-meta-review] [--sequential] [--parallel] [--bulk] [--all-open] [--search <query>] [--limit <n>] [--unattended] [--resume [<run-id>]]"
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
Set `CC_REVIEW_CORE_DIR` to the absolute resolved core path (the directory
that contains `commands/review.md`) in every shell block of the command.

Pass through all arguments from the user's invocation:
- `--pr <number>`: Target PR number
- `--spec <path>`: Specification file path
- `--hints <path>`: Review hints file
- `--output <path>`: Output report path
- `--config <path>`: Explicit config file path
- `--profile <name>`: Profile preset name (ci, thorough, quick)
- `--no-fix`: Skip autonomous fix loop
- `--max-rounds <n>`: Maximum fix rounds
- `--no-external` / `--external`: Disable or enable all command (external tool) reviewers
- `--no-<reviewer>`: Disable one discovered reviewer by name (for example `--no-codex`)
- `--only <reviewer,...>`: Dispatch only the listed reviewers
- `--no-meta-review`: Skip the meta-review pass
- `--sequential`: Run reviewers one at a time instead of in parallel
- `--parallel`: Run reviewers in parallel (the default; accepted for compatibility)
- `--bulk`: Review several PRs in one run (see `core/commands/bulk.md`)
- `--all-open` / `--search <query>`: Bulk selectors (all open PRs, or a PR search)
- `--limit <n>`: Maximum number of PRs in a bulk run
- `--unattended`: Bulk run without prompts, using the fixed policy
- `--resume [<run-id>]`: Continue an unfinished bulk run
