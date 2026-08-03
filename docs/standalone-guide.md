# Standalone Quick Start

Get cc-review running without spec-kit or cc-spex.

## Prerequisites

- Git repository with changes on a branch
- `gh` CLI installed and authenticated (`gh auth login`)
- An AI coding agent with subagent support (Claude Code, Codex, or OpenCode)
- Optional: `coderabbit`, `copilot`, or `codex` CLIs for external tool integration

## Install for Claude Code

```bash
git clone https://github.com/rhuss/cc-review.git ~/.cc-review
~/.cc-review/adapters/claude-code/install.sh --global
```

## First Review

```bash
# Create a branch with changes
git checkout -b my-feature
# ... make changes ...
git add -A && git commit -m "my changes"

# Run review
/review
```

The review dispatches 6 agents, merges findings, and reports a gate outcome (PASS/FAIL). If Critical or Important findings exist, the fix loop attempts to resolve them.

Output goes to `./review-findings.md` by default.

## Review a Specific PR

```bash
/review --pr 42
```

## Configuration

```bash
mkdir -p .cc-review
cp ~/.cc-review/config/config-template.yml .cc-review/config.yml
```

Edit `.cc-review/config.yml` to customize external tools, fix loop rounds, and test commands.

## Review Hints

Create `.cc-review/review-hints.md` to teach agents about your project's patterns:

```markdown
## Framework Patterns

- The `ApiClient.send()` method retries 3 times internally. Don't flag
  missing retry logic around send() calls.
- All database queries go through `QueryBuilder` which handles connection
  pooling. Direct connection creation is a bug.
```

## PR Comment Triage

```bash
/triage           # Triage current branch's PR
/triage --pr 42   # Triage a specific PR
```

Triage fetches all review threads, classifies bot vs human comments, applies valid bot fixes, and presents human comments for interactive review.

## Troubleshooting

**"No test command detected"**: The fix loop skips tests if it can't find a test command. Add `test_command: "your-test-cmd"` to `.cc-review/config.yml`.

**External tools not running**: Check `external_tools` in your config. Tools must be installed (`which coderabbit`, `which copilot`, `which codex`).

**Goal alignment skipped**: The goal alignment agent needs a PR with a body and/or linked issues. Without PR context, it's skipped automatically.
