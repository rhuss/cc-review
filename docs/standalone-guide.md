# Standalone Guide

Quick start for using cc-review without spec-kit or any other framework.

## Prerequisites

- Git repository with a remote named `origin`
- [GitHub CLI](https://cli.github.com/) (`gh`) installed and authenticated
- An AI coding agent that supports slash commands: Claude Code, Codex, or OpenCode
- `jq` and `yq` available on PATH (used by config resolution and triage state)

## Installation

The `review/` directory of the repository is the plugin. Each harness installs it with its own mechanism; see the README for details.

### Claude Code

```bash
git clone https://github.com/rhuss/cc-review.git ~/cc-review
claude plugin marketplace add ~/cc-review
claude plugin install cc-review@cc-review-plugin-development
```

### Codex

```bash
codex plugin marketplace add ~/cc-review
codex plugin install cc-review@cc-review-plugin-development
```

### OpenCode

```bash
~/cc-review/review/opencode/install.sh --project-dir .
```

All three shims resolve the cc-review core at runtime: the plugin's own `core/` directory first, then `.cc-review/core` in the project root, then `~/.cc-review/core` in your home directory.

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
- Discover every reviewer plugin (bundled, `~/.cc-review/reviewers/`, `.cc-review/reviewers/`) and dispatch the enabled ones in parallel; the bundled set is Correctness, Architecture, Security, Production Readiness, Test Quality, Goal Alignment (needs a PR), and the opt-in gator reviewer. See `docs/reviewer-plugins.md` to add your own.
- Run the enabled command reviewers whose tool is installed (CodeRabbit and Codex by default) and include their findings
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

This uses the PR's diff instead of the branch diff and extracts goals from the PR description for reviewers that request the `goals` context block (the bundled Goal Alignment reviewer).

## Configuration

### Project-level config

```bash
mkdir -p .cc-review
cp ~/cc-review/config/config-template.yml .cc-review/config.yml
```

Edit `.cc-review/config.yml` to customize:

```yaml
# Disable CodeRabbit, enable Copilot and the opt-in gator reviewer
reviewers:
  coderabbit: false
  copilot: true
  codex: true
  gator: true

# Custom test command (skip auto-detection)
test:
  command: "make test-unit"
  timeout_seconds: 120

# Reduce fix loop rounds
max_fix_rounds: 2

# Write reports to a subdirectory
output:
  dir: "reports"
```

### User-level config

For settings that apply across all projects, place the config at `~/.cc-review/config.yml`. Project-level config takes precedence over user-level config.

## Review Hints

Review hints give every prompt reviewer project-specific knowledge that is not apparent from reading the code. This is useful for framework quirks, intentional patterns, or known limitations.

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

### A command reviewer shows "skipped (not available)"

Command reviewers wrap external CLIs and run the plugin's `detect` check on your PATH. If a tool is installed but reported as not available:

- Verify with `which coderabbit`, `which copilot`, or `which codex`
- A reviewer turned off in config shows `disabled`, not `skipped`
- `skipped (not authenticated)` means the tool's `auth_check` failed; the text after the colon, when present, is the last line the check printed (a network error looks different from a missing login). Log in to the tool first
- `detection timed out` means the check did not answer within 15 seconds; the tool's state is unknown
- `skipped (untrusted project command reviewer ...)` is a command reviewer from the project's `.cc-review/reviewers/`; add the `<name> <sha256>` line from the reason to `~/.cc-review/trusted-reviewers` to let it run

### A reviewer shows "skipped (requires: pr)"

Reviewers that declare `requires: [pr]` (the bundled Goal Alignment reviewer) need a PR to work from. If you run `/review` without `--pr` and no PR exists for the current branch, they are skipped. Create a PR first or pass `--pr`.

### Test command not detected

cc-review auto-detects test commands from `Makefile` (target `test:`), `go.mod`, `package.json`, or `pyproject.toml`/`setup.py`. If your project uses a different test runner, set `test.command` in config:

```yaml
test:
  command: "cargo test"
```

### GraphQL errors during triage

GitHub API responses sometimes contain unescaped control characters. cc-review includes `core/scripts/sanitize-gh-json.py` to handle this. Ensure Python 3 is available on PATH.
