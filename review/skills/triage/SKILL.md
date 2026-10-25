---
name: triage
description: PR comment triage - classify and handle bot and human review comments
argument-hint: "[--pr <number>] [--spec <path>] [--config <path>] [--profile <name>] [--no-coverage-fix] [--idea-inbox <path>] [--bulk] [--search <query>] [--limit <n>] [--unattended] [--resume [<run-id>]]"
---

# Triage

Locate cc-review core and delegate to `core/commands/triage.md`.

## Core Resolution

Find the cc-review core directory by checking these paths in order:
1. `./core` relative to this plugin's root directory
2. `.cc-review/core` in the current project
3. `~/.cc-review/core` in the user's home directory

Read the first path that contains `commands/triage.md`. If none found, report:
"cc-review core not found. Install the plugin or set up .cc-review/core."

## Execution

Read and execute `core/commands/triage.md` from the resolved core path.
Set `CC_REVIEW_CORE_DIR` to the absolute resolved core path (the directory
that contains `commands/triage.md`) in every shell block of the command.

Pass through all arguments from the user's invocation:
- `--pr <number>`: Target PR number
- `--spec <path>`: Specification file path
- `--config <path>`: Explicit config file path
- `--profile <name>`: Profile preset name (ci, thorough, quick)
- `--no-coverage-fix`: Skip automatic coverage fixes
- `--idea-inbox <path>`: File path for capturing out-of-scope ideas
- `--bulk`: Triage all your open PRs with unresolved threads in one run
- `--search <query>`: Restrict the bulk selection with a PR search
- `--limit <n>`: Maximum number of PRs in a bulk run
- `--unattended`: Bulk run without prompts, using the fixed policy
- `--resume [<run-id>]`: Continue an unfinished bulk run
