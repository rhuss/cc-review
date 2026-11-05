# Review your changes

<!-- Sources:
cc-review:README.md:127-131
cc-review:README.md:133-137
cc-review:README.md:139
cc-review:README.md:145-149
cc-review:README.md:151-161
cc-review:README.md:167-189
cc-review:README.md:224-236
cc-review:review/core/commands/review.md:916-938
cc-review:review/config/profiles/quick.yml:1-25
cc-review:review/config/profiles/thorough.yml:1-26
cc-review:review/config/profiles/ci.yml:1-30
-->

A review before you push catches the Critical and Important issues while the change is still on your machine, so you hand reviewers a cleaner pull request. The `/cc-review:review` command dispatches every enabled reviewer at your changes, merges the findings, and runs the fix loop over the issues worth acting on. This page covers how to start a review, how to narrow it, and how to read what it reports. For the mechanism behind each step, see [How it works](../how-it-works/index.md).

## Review the current branch

Start here when the change lives on your working branch and you have not opened a pull request yet.

1. Make sure your branch holds the changes you want reviewed, then run:

   ```
   /cc-review:review
   ```

   This reviews all changed files on the current branch against main, dispatches every enabled reviewer, merges their findings, and runs the fix loop.

2. Read the report when the run finishes. By default cc-review writes it to `./review-findings.md` in the repository root.

Check: the review wrote its report to the default path.

```bash
ls review-findings.md
```
<!-- expect: exit 0 -->

## Review a pull request

Run a review against an open pull request when the change is already pushed, for your own PR or someone else's.

1. Review the diff of a specific PR by number:

   ```
   /cc-review:review --pr 42
   ```

2. When you run `--pr` from a branch other than the PR's own, cc-review checks the PR out into a separate worktree under `.cc-review/pr-worktrees/` and reviews it there, so your current working tree stays as it is. You do not need to switch branches first.

## Choose how deep to go

cc-review ships three profile presets you select with `--profile`. Each one sets which reviewers run, the confidence threshold, the severities that block the gate, and the number of fix rounds.

```
/cc-review:review --profile thorough
```

- **`quick`** runs only the correctness and security reviewers, with no command (external tool) reviewers and a single fix round. Only Critical findings block its gate.
- **`thorough`** runs all bundled reviewers except Gator with stricter thresholds and up to five fix rounds. Critical, Important, and Minor findings all block its gate.
- **`ci`** runs all bundled reviewers except Gator and Greptile (Greptile spends credits on every run), produces verbose output, asks no interactive questions, and does not post to the PR. Critical and Important findings block its gate.

## Narrow or skip work

These flags trim a run when you want a report only, want to leave the external tools out, or want to target a subset of reviewers.

- `--no-fix` skips the autonomous fix loop, so cc-review reports the findings without changing your code.
- `--no-external` disables all command (external tool) reviewers and runs only the bundled agents.
- `--only <reviewer,...>` dispatches only the reviewers you name, for example `--only correctness,security`. Any discovered reviewer name works here.
- `--spec <path>` cross-checks the implementation against a specification file; the goal alignment reviewer verifies that each functional requirement (FR-NNN) is implemented.

You can combine them. This produces a report only, from the bundled reviewers, with no fixes applied:

```
/cc-review:review --no-fix --no-external
```

## Read the report and the gate

cc-review presents the report for a person to read, not as a log. It opens with a verdict: one short paragraph on whether the change is ready to merge, how many issues you should address first, and the one or two themes behind them. It also names any reviewer that could not run, for example a tool over its usage limit. After the verdict, every Critical and Important finding gets its own section that explains where the problem is, what the code does today, and what goes wrong.

The gate is the pass-or-fix decision at the end. cc-review counts the findings whose severity blocks the gate (Critical and Important by default). When that count is zero the gate passes; when it is above zero the gate fails unless the fix loop clears those findings within the maximum rounds. Lower-severity notes do not affect the gate.

> [!NOTE]
> The severities that block the gate come from the active profile. `quick` blocks on Critical alone, while `thorough` also blocks on Minor, so the same change can pass one profile and fail another.

## Review several PRs, and follow up

Run a bulk review to cover more than one pull request in a single pass:

```
/cc-review:review --bulk
```

This reviews the open PRs that request your review, plus the PRs you already reviewed with cc-review that have new commits since. Each PR is analyzed in its own worktree, and at the end you get one table to decide per PR: post the review, apply the suggested fixes, post a short no-findings note, or skip.

When you review the same PR again, cc-review runs a follow-up: it reviews only the delta since your latest completed cc-review run, including the code you changed to fix earlier findings, rather than re-reporting the whole diff.

> [!NOTE]
> This page covers the commands you run. For how the reviewers, the two critics, and the fix loop produce the report, read [How it works](../how-it-works/index.md). For the full flag list, see the [Reference](../reference/index.md).

> [!NOTE]
> These commands were verified against cc-review <!-- guide:attr cc-review-version -->1.4.0<!-- /guide:attr -->.
