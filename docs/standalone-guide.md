# Standalone Guide

Quick start for using cc-review without spec-kit or any other framework.

## Prerequisites

- Git repository with a remote named `origin`
- [GitHub CLI](https://cli.github.com/) (`gh`) installed and authenticated
- An AI coding agent that supports slash commands: Claude Code, Codex, or OpenCode
- `jq` and `yq` available on PATH (used by config resolution and triage state)

## Installation

### Claude Code

```bash
git clone https://github.com/rhuss/cc-review.git ~/cc-review

# Install globally (available in all projects)
~/cc-review/adapters/claude-code/install.sh --global

# Or install for a single project
cd /path/to/your/project
~/cc-review/adapters/claude-code/install.sh
```

The install script creates symlinks from your `.claude/commands/` directory to the adapter's SKILL.md files. The adapter resolves the cc-review core at runtime by checking:

1. Relative path from the symlink target (development installs)
2. `.cc-review/core` in the project root
3. `~/.cc-review/core` in your home directory

If you prefer manual setup, symlink the command directories directly:

```bash
mkdir -p .claude/commands
ln -s ~/cc-review/adapters/claude-code/commands/review .claude/commands/review
ln -s ~/cc-review/adapters/claude-code/commands/triage .claude/commands/triage
```

### Codex / OpenCode

```bash
~/cc-review/adapters/agents-md/install.sh
```

This appends the cc-review agent section to your project's `AGENTS.md`. The agent reads core command files at runtime from `.cc-review/core/` or `~/.cc-review/core/`.

## First Review

1. Create a feature branch and make some changes:

```bash
git checkout -b my-feature
# ... edit files ...
git add -A && git commit -m "implement feature"
```

2. Run the review:

```
/review
```

cc-review will:
- Determine changed files by diffing against the main branch
- Dispatch 6 review agents sequentially (Correctness, Architecture, Security, Production Readiness, Test Quality, Goal Alignment)
- Check for external tools (CodeRabbit, Codex CLI) and include their findings
- Merge and deduplicate all findings
- Run the autonomous fix loop for Critical/Important findings (up to 3 rounds)
- Write a report to `review-findings.md`
- Print a console summary with per-agent statistics

3. Read the report:

The output includes a summary table, individual findings with file locations and fix suggestions, and the gate outcome (PASS or FAIL).

## Reviewing a PR

If your changes are already in a pull request:

```
/review --pr 42
```

This uses the PR's diff instead of the branch diff and extracts goals from the PR description for the Goal Alignment agent.

## Configuration

### Project-level config

```bash
mkdir -p .cc-review
cp ~/cc-review/config/config-template.yml .cc-review/config.yml
```

Edit `.cc-review/config.yml` to customize:

```yaml
# Disable CodeRabbit, enable Copilot
external_tools:
  coderabbit: false
  copilot: true
  codex: true

# Custom test command (skip auto-detection)
test_command: "make test-unit"
test_timeout_seconds: 120

# Reduce fix loop rounds
max_fix_rounds: 2

# Write reports to a subdirectory
output_dir: "reports"
```

### User-level config

For settings that apply across all projects, place the config at `~/.cc-review/config.yml`. Project-level config takes precedence over user-level config.

## Review Hints

Review hints give all 6 agents project-specific knowledge that is not apparent from reading the code. This is useful for framework quirks, intentional patterns, or known limitations.

Create `.cc-review/review-hints.md`:

```markdown
## Framework Patterns

- This project uses sqlx with compile-time query checking. The `query!` and
  `query_as!` macros verify SQL at build time, so SQL injection through these
  macros is not possible. Only flag SQL injection for raw `query()` calls.

## Intentional Patterns

- The `retry_with_backoff` function intentionally swallows errors on the final
  attempt and returns a generic timeout error. This is by design, not a bug.

## Known Limitations

- The WebSocket handler does not implement graceful shutdown. This is tracked
  in issue #87 and should not be flagged as a production readiness finding.
```

The hints file path defaults to `.cc-review/review-hints.md`. Override with `--hints`:

```
/review --hints docs/review-context.md
```

## Triage

After pushing a PR and receiving bot or human review comments:

```
/triage
```

Or target a specific PR:

```
/triage --pr 42
```

Triage fetches all review threads via the GitHub GraphQL API, classifies each comment by author (bot vs human), and handles them according to the bot profiles in your config.

Default bot profiles:

| Bot | Behavior |
|-----|----------|
| `coderabbitai[bot]` | `self_resolves: true` (CodeRabbit resolves its own threads when you push fixes) |
| `copilot[bot]` | `auto_resolve: true` (auto-apply and resolve) |
| `devin-ai-integration[bot]` | `auto_resolve: true` (auto-apply and resolve) |

Human comments are presented for interactive review. Out-of-scope ideas can be captured to an idea inbox file:

```
/triage --idea-inbox brainstorm/ideas.md
```

### Triage State

Triage tracks which comments have been handled in `.cc-review/.triage-state.json` (git-ignored by default). Running triage again skips already-handled comments, so you can run it incrementally as new reviews arrive.

## Troubleshooting

### "cc-review core not found"

The adapter could not locate the core directory. Ensure one of these paths exists:

- The cloned repository is intact (for development installs via symlink)
- `.cc-review/core/` exists in your project root (copy or symlink `core/` there)
- `~/.cc-review/core/` exists in your home directory

### External tools not detected

cc-review checks for external tool CLIs on your PATH. If a tool is installed but not detected:

- Verify with `which coderabbit`, `which copilot`, or `which codex`
- Check that the tool is enabled in config (CodeRabbit and Codex are enabled by default; Copilot is disabled by default)

### Goal Alignment agent skipped

The Goal Alignment agent requires a PR to extract goals from. If you run `/review` without `--pr` and no PR exists for the current branch, the agent is skipped. Create a PR first or pass `--pr`.

### Test command not detected

cc-review auto-detects test commands from `Makefile` (target `test:`), `go.mod`, `package.json`, or `pyproject.toml`/`setup.py`. If your project uses a different test runner, set `test_command` in config:

```yaml
test_command: "cargo test"
```

### GraphQL errors during triage

GitHub API responses sometimes contain unescaped control characters. cc-review includes `core/scripts/sanitize-gh-json.py` to handle this. Ensure Python 3 is available on PATH.
