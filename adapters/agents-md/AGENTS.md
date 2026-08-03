# cc-review: Multi-Agent Code Review

## Agent: code-reviewer

**Description:** Runs multi-agent code review with specialized review agents
(correctness, security, performance, style, architecture) and an autonomous
fix loop that applies suggested changes.

**Available commands:**

### review
Multi-agent code review with autonomous fix loop.
To invoke: read and follow the instructions in `core/commands/review.md`
from the cc-review install directory (`.cc-review/core/` or the repository root).

Options: `--pr`, `--spec`, `--hints`, `--output`, `--no-fix`, `--no-external`,
`--parallel`, `--sequential`

### triage
PR comment triage that classifies bot vs human comments and handles them.
To invoke: read and follow the instructions in `core/commands/triage.md`.

Options: `--pr`, `--spec`, `--no-coverage-fix`, `--idea-inbox`

**Core location:** `.cc-review/core/` (project-local) or `~/.cc-review/core/` (global)

**Install:** Run `adapters/agents-md/install.sh` to add this fragment to AGENTS.md.
