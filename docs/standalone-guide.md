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

You don't need to check the PR out first. If your current branch is something else, cc-review checks the PR out into `.cc-review/pr-worktrees/pr-42`, reviews that copy, and removes it when it's done. Your working tree is left alone. In that case the fix options only show up if you are the PR's author, and accepted fixes are committed and pushed straight to the PR branch. If someone pushed to the PR while the review ran, nothing is pushed and the review is not posted.

A PR from a fork is someone else's code, and an external CLI reviewer (codex, copilot) started inside that checkout could pick up the fork's own `AGENTS.md` or `.github/copilot-instructions.md`. So command reviewers are skipped there and show up as `skipped (untrusted checkout)`; the prompt reviewers still run. The same holds for fork PRs in a bulk review. To let a tool run anyway, opt it in:

```yaml
allow_untrusted_checkout:
  codex: true
```

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

## Bulk Review and Triage

Both commands can work through several PRs in one go. Add `--bulk`:

```
/review --bulk
/triage --bulk
```

Each PR is checked out into its own temporary worktree, so your current branch, index and uncommitted changes are never touched. PRs are handled one at a time, and a PR that fails (a deleted branch, an unreachable fork) is marked as failed while the run moves on to the next one.

### Which PRs get picked

`/review --bulk` takes the open PRs that ask for your review, either directly or through one of your teams. It also takes PRs you reviewed with cc-review before that have new commits since. Two options change that:

| Option | Selects |
|--------|---------|
| `--all-open` | every open PR in the repository |
| `--search '<query>'` | the open PRs of this repository that match a GitHub search, for example `--search 'label:needs-review'` |

`/triage --bulk` takes your own open PRs that have at least one unresolved review thread. `--search` narrows that list further. `--all-open` is not available for triage.

These rules hold for every selector:

- Draft PRs are skipped unless the search asks for them with `draft:true` or `is:draft`.
- `/review --bulk` skips a PR that already has a cc-review review at its current head commit. A cc-review marker posted by the PR's own author doesn't count, so nobody can opt their PR out of review that way. The one exception is your own marker on your own PR, which counts. (`/triage --bulk` does not apply this rule; it goes by unresolved threads.)
- The search always stays inside the current repository and its open PRs, so `repo:`, `org:`, `user:`, `is:closed`, `is:merged` and `state:` are rejected.
- `--limit <n>` caps the run (10 by default). The PRs that haven't been updated for the longest time come first.

Two combinations are rejected outright: `--all-open` with `--search`, and `--bulk` with `--pr`.

### Deciding what happens

By default a bulk run analyzes every PR first and asks nothing until all of them are done (the docs and messages call this deferred mode). Then it shows one table with a row per PR: the finding counts (or, for triage, the valid, rejected and deferred bot suggestions and the human comments), the path of the full report, and a proposed action. You can accept all proposals at once, change the action for single PRs, skip everything, or stop and decide later.

For bulk review you can choose per PR:

- post the review
- go through the findings one by one first, then post the ones you keep
- apply the fixes and push them (only on your own PRs, and only when a finding comes with a concrete fix or is Critical or Important)
- apply the fixes, then post what remains
- post a short "no findings" note so later runs skip the PR
- skip it

For bulk triage you either apply a PR's prepared work (push the fix commit, post the drafted replies, resolve the handled threads) or skip it. Human comments are shown one by one in the same step, and you approve, edit or skip each reply.

If a PR gets new commits while the other PRs are still being analyzed, it is analyzed once more before the table shows up. Should it move yet again, it is marked stale and gets no action.

Before anything is pushed or posted, cc-review checks that the PR head hasn't moved since the analysis. If it has, that PR is marked stale and left alone, and the next run picks it up again.

### Unattended runs

`--unattended` (or `interactive: false` in the config) runs the whole thing without a single question and applies a fixed policy:

- Reviews are posted as plain comments and never block a PR. PRs without findings get the "no findings" note.
- Unattended review never changes code.
- Triage pushes the prepared bot fixes, posts the bot replies and resolves the handled threads.
- Human comments are left alone and listed under "Needs attention" in the summary.

### Resuming

Every run keeps its state in `.cc-review/bulk/<run-id>/`. The directory is git-ignored and cc-review never deletes it. `state.md` in there shows the progress at any time, and `summary.md` holds the result once the run ends. Each PR also gets a subdirectory with its report.

If a run is interrupted (you closed the session, GitHub rate-limited you, you stopped at the decision step), continue it with:

```
/review --bulk --resume
/triage --bulk --resume 20261025-091500-triage
```

A resumed run keeps the options it was started with. PRs whose head moved since their analysis are analyzed again, finished PRs stay finished, and anything already pushed, posted or resolved is not done a second time. A PR that failed is tried again, but only up to three failed attempts in all; after that it stays failed and the run can finish without it. There is at most one unfinished run per command. Starting a new one while another is open asks whether to resume it, abandon it or cancel. Abandoning keeps the old run's state but removes the worktrees it still held; its `summary.md` lists them. An unattended run can't ask, so it stops with an error that tells you to add `--resume`.

### Scheduled jobs

For a nightly job, use:

```
/review --bulk --resume --unattended
```

If an unfinished unattended run exists, this continues it. Otherwise it starts a new run with the flags you passed. So a run that hit a GitHub rate limit picks up the next night where it stopped.

CI is not checked after bulk triage pushes fixes. The summary lists each pushed PR with a hint to run `/triage --pr <n>` when you want the CI repair loop for it.

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
