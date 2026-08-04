# Triage

PR comment triage that classifies bot vs human review comments and handles them.

## Core Resolution

Find the cc-review core directory by checking these paths in order:
1. The cc-review plugin directory's `core/` (if installed via opencode marketplace)
2. `.cc-review/core` in the current project
3. `~/.cc-review/core` in the user's home directory

Read the first path that contains `commands/triage.md`. If none found, report:
"cc-review core not found. Install the plugin or set up .cc-review/core."

## Execution

Read and execute `core/commands/triage.md` from the resolved core path.

Pass through all arguments from the user's invocation:
- `--pr <number>`: Target PR number
- `--spec <path>`: Specification file path
- `--config <path>`: Explicit config file path
- `--profile <name>`: Profile preset name (ci, thorough, quick)
- `--no-coverage-fix`: Skip automatic coverage fixes
- `--idea-inbox <path>`: File path for capturing out-of-scope ideas
