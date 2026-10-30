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

## Assessing an Issue

Run `issue 42`, `issue 42 --repo owner/project`, or `issue https://github.com/owner/project/issues/42` through your harness. Use the issue skill in Codex and the issue command in Claude Code or OpenCode.

The workflow evaluates whether the issue demonstrates a concrete need, fits the project's documented direction, and warrants implementation. It can recommend against proceeding. Missing use-case evidence earns a focused question before any solution plan; uncertain project direction earns a question to the maintainer. An offered contribution usually gets a bounded welcome once the need and fit are established.

The result contains maintainer reasoning and a separate public reply draft, shaped with prose when available or the bundled maintainer voice otherwise. No comment is posted, code changed, or issue mutated.

Python 3.9+, jq, and authenticated gh are required. Only GitHub.com issues are supported. Collection includes the opening body and latest 50 comments with visible text/history limits. A matching local origin enables focused guidance/code inspection; otherwise project-context limitations remain explicit.

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

## Follow-up Reviews

Both single-PR and bulk review automatically use incremental scope when your own latest completed cc-review run provides trustworthy, compatible coverage. They review every change since that baseline, including requested fixes. Other reviewers' runs do not establish your baseline.

The report names the mode, baseline, reviewed content, verification outcomes and actual tool coverage. The full PR remains available as context. In incremental mode, ordinary new findings stay within the delta; a new critical problem in unchanged code needs concrete evidence. Command reviewers without incremental support may read the full PR, which is disclosed, and their output is filtered by the same finding policy.

Earlier unresolved findings from all your cc-review runs are checked explicitly. Partial fixes remain open in their original threads, including when a new reviewer does not rediscover them. Review and reviewer triage use the same exact activity and verification rules to avoid duplicate replies/resolutions. Triage does not advance a code-review baseline or clear separate changed-code work.

Follow-ups use your earlier manual reviews and cc-review discussions, including relevant resolved threads, summary-only feedback and author replies. Manually written review findings in PR comments are identified from their context; casual participation does not count as an earlier review. This history provides continuity even without a trustworthy code baseline, while code scope still falls back to full review when required.

Author explanations and promised fixes are checked against current code. Existing concerns continue in their conversations, with links; a justified reversal of earlier advice is explained. New follow-up findings need concrete material impact. Minor preferences, optional polish and speculative improvements are suppressed even in changed code, while real regressions in requested fixes remain reportable. The existing Critical-only exception for new unchanged-code findings still applies in incremental mode.

Reports distinguish addressed concerns, existing open material concerns, new material findings, prior nonblocking suggestions and limitations. **No outstanding material concerns** is a valid conclusion only when history, required coverage and verification are complete and no substantive concerns or questions remain. A completed assessment can still report outstanding concerns. Neither a clean conclusion nor a history classification automatically approves, merges or authorizes thread resolution. Large or incomplete histories disclose their limits instead of implying earlier concerns were cleared.

These rules apply to single and bulk follow-ups, full fallbacks and explicit `--full`. Before publication, both head and conversation evidence must still match; changed evidence requires reassessment or withholding stale actions. Posting continues to use existing approval and unattended policies.

Force a full review when needed:

```text
review --pr 42 --full
review --bulk --full
```

First reviews, legacy run markers without explicit completion evidence, changed reviewer coverage/settings and unavailable or unreliable comparison history trigger an explained full review. A completed no-findings review can become a baseline after approved publication; a local-only run, missing verification, failed required reviewer or dirty/unpinned PR checkout cannot create pinned completion evidence. Unresolved findings do not by themselves make a review incomplete.

A proven rebase-only update requires no new code review or review post. Pending thread work remains independent. A renewed review request receives verification and an unchanged-contribution acknowledgment rather than an automatic full review. Substantive conflict resolutions and additional changes are reviewed; uncertain equivalence triggers full fallback.

Existing approval and unattended policies still govern every remote action. Scope preparation does not post, resolve, change branches or alter the user's index. Prepared completion evidence is checked against the current PR head and conversations before publication.

Missing current head/base objects are fetched before comparison, including when you are already on the PR branch. Unavailable older baseline objects still cause full fallback. A labeled incomplete personal attempt stays actionable even if GitHub clears its review request; a later completed personal review supersedes it. Approved partial notices never establish completed coverage.

## Repository Inbox

Use `/inbox --type pr` to see open PRs and whether your next action is review, triage, or both. Review covers a first or substantial code review. Triage continues eligible feedback already owned by you on another author's PR, or comments on your own PR. A PR can stay eligible for both actions; completing one does not satisfy the other. The inbox is read-only and labels missing or bounded review-thread context as incomplete instead of treating it as a verified empty result.

Inbox collection is bounded to 100 discoveries per reason, 20 activity entries, and 10 replies per displayed thread. The report shows when those limits or service errors leave coverage incomplete. Draft PRs can appear in the inbox and remain eligible for triage; ordinary bulk review skips drafts.

The inbox reads reviewer activity from `$XDG_STATE_HOME/cc-review/reviewer-activity/`, or `~/.local/state/cc-review/reviewer-activity/` by default. It does not create or update this cache. The existing author triage state remains at `.cc-review/.triage-state.json`.

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

Triage fetches review threads via the GitHub GraphQL API, classifies each comment by author (bot vs human), and handles them according to the bot profiles in your config. It can continue your owned feedback on another author's PR as reviewer triage. That path checks the current code and exact thread, prepares a reply for approval when needed, and never commits or pushes code. Author triage on your own PR keeps its existing fix workflow.

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

Author triage tracks handled comments in `.cc-review/.triage-state.json` (git-ignored by default). Reviewer follow-up outcomes are stored per account under `$XDG_STATE_HOME/cc-review/reviewer-activity/`, or `~/.local/state/cc-review/reviewer-activity/` by default. Exact thread, root, head, and conversation activity prevent duplicate replies or resolutions across triage and review; a new head or reply makes the activity eligible again. Questions, deferred work, and incomplete verification remain visible and are not marked handled.

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

`/triage --bulk` takes open PRs with eligible author feedback or reviewer-owned follow-up threads. `--search` narrows that list further. Drafts are included for triage. `--all-open` is not available for triage.

These rules hold for every selector:

- Draft PRs are skipped by ordinary bulk review unless the search explicitly selects them (`is:draft` or `draft:true`). Triage includes drafts because existing feedback can still need action.
- `/review --bulk` normally skips a PR reviewed at its current head, except for a renewed personal/team request or `--full`. Marked incomplete runs do not clear review work. A marker by the PR's author does not suppress another reviewer; your own marker on your own PR retains its existing selection behavior. Triage selection remains independent.
- The search always stays inside the current repository and its open PRs, so `repo:`, `org:`, `user:`, `is:closed`, `is:merged` and `state:` are rejected.
- `--limit <n>` caps the run (10 by default). The PRs that haven't been updated for the longest time come first.

Selection can retain uncertain changed-head candidates without computing their entire delta. Execution establishes incremental/full scope and can then report a proven unchanged contribution and skip new code review. The inbox remains read-only and lightweight.

Some combinations are rejected before anything runs: `--all-open` with `--search`, `--bulk` with `--pr`, `--spec` with `--bulk`, `--output` with bulk review (each PR's report goes to its run directory), and a `--limit` that isn't a positive whole number.

The usual review options apply to every PR: `--full`, `--config`, `--profile`, reviewer selection (`--only`, `--no-<reviewer>`, `--external`, `--no-external`), `--no-meta-review`, `--max-rounds`, `--hints`, `--sequential` and `--parallel`. `--no-fix` removes "apply fixes". Resume uses recorded scope options; start a new run to change `--full`. For triage, `--config`, `--profile` and `--idea-inbox` retain their behavior.

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

When the run stopped in the middle of its analysis, resuming asks how far to go: continue with all remaining PRs, finish only the PR that was being analyzed and then decide, or decide right away on what is already analyzed. With either shortcut, the PRs it didn't get to are left alone. Nothing is posted on them, so your next bulk run picks them up again. (An unattended run doesn't ask and simply continues.)

When you resume a run, it picks up where it stopped:

- It uses the same options as when it was started. You can't change them on resume.
- PRs that are already done stay done.
- Nothing is pushed, posted or resolved twice.
- A PR that got new commits since it was analyzed is analyzed again.
- A PR that failed is tried again. After three failures it is given up on, so the run can still finish.

You can only have one unfinished run per command (one for review, one for triage). If you start a new bulk run while an old one is still open, cc-review asks what to do:

- **Resume** the old run.
- **Abandon** it and start fresh. The old run's state files stay on disk, but its leftover PR checkouts are deleted (its `summary.md` lists which ones).
- **Cancel** and do nothing.

An unattended run can't ask this question. It stops with an error instead and tells you to add `--resume`.

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
