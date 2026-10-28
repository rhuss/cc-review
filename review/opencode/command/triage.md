# Triage

PR triage that continues author feedback and owned reviewer feedback on existing threads.

## Core Resolution

Find the cc-review core directory by checking these paths in order:
1. The cc-review plugin directory's `core/` (if installed via opencode marketplace)
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
- `--bulk`: Triage eligible open PRs with author or reviewer-owned feedback in one run
- `--search <query>`: Restrict the bulk selection with a PR search
- `--limit <n>`: Maximum number of PRs in a bulk run
- `--unattended`: Bulk run without prompts, using the fixed policy
- `--resume [<run-id>]`: Continue an unfinished bulk run

A PR may need both review and triage. Review assesses a first or substantial code review; triage continues eligible feedback on an existing review. Reviewer triage verifies exact owned threads and never commits or pushes code. Draft PRs remain eligible for triage even though ordinary bulk review skips drafts.
