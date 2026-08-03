# Review

Multi-agent code review with autonomous fix loop.

## Core Resolution

Find the cc-review core directory by checking these paths in order:
1. The cc-review plugin directory's `core/` (if installed via opencode marketplace)
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
- `--no-fix`: Skip autonomous fix loop
- `--no-external`: Skip external tool integration
- `--parallel`: Run review agents in parallel
- `--sequential`: Run review agents sequentially
