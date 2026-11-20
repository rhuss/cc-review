# Review your changes

<!-- Sources:
cc-review:README.md:128-150
cc-review:README.md:152-168
cc-review:README.md:170-196
cc-review:README.md:230-243
cc-review:README.md:252-257
cc-review:README.md:269-270
cc-review:review/core/commands/review.md:9-16
cc-review:review/core/commands/review.md:26-40
cc-review:review/core/commands/review.md:165-202
cc-review:review/core/commands/review.md:938-973
cc-review:review/core/commands/review.md:983-1015
cc-review:review/core/commands/review.md:1017-1073
cc-review:review/core/commands/review.md:1171-1196
cc-review:review/core/commands/review.md:1447-1460
cc-review:review/core/commands/review.md:1563-1611
cc-review:review/core/commands/review.md:1616-1657
cc-review:review/core/commands/review.md:1805-1814
cc-review:review/core/commands/unattended.md:9-34
cc-review:review/config/profiles/quick.yml:1-25
cc-review:review/config/profiles/thorough.yml:1-26
cc-review:review/config/profiles/ci.yml:1-30
-->

A review before you push catches the Critical and Important issues while the change is still on your machine, so you hand reviewers a cleaner pull request. The `/cc-review:review` command dispatches every enabled reviewer at your changes, merges the findings, and runs the fix loop over the issues worth acting on. This page covers how to start a review, how to narrow it, how to read what it reports, and what gets posted to a pull request. For the mechanism behind each step, see [How it works](../how-it-works/index.md).

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

3. To review the PR without questions, add `--unattended`:

   ```
   /cc-review:review --pr 42 --unattended
   ```

   This applies the fixed unattended policy: cc-review prepares and checks the draft, publishes a plain comment only, and withholds publication when a check fails. It never approves or requests changes, and it makes no code changes.

## Fixes and PR ownership

The autonomous fix loop applies its edits to the tree under review, but whether those edits reach the pull request depends on your push access: cc-review can push fixes only to a PR you can push to. It offers to apply fixes only when the PR is your own; on another author's PR it offers to post the review and nothing more. When it does fix your own PR, it commits the edits in the PR worktree and pushes them to the PR branch, never with force.

A push can still be refused. You may lack push permission on the branch, as with a fork PR, the branch may have moved since the review started, or the push may fail for another reason. In each case cc-review does not push the fixes and does not post a review, because the findings would then describe code that is not on the PR. It reports the problem in plain words, keeps the fix worktree so the commit is not lost, and tells you the worktree path. The review itself still runs on a PR you do not own, so you can read and post its findings; only the fixes cannot land there.

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

## What gets posted, and when

Nothing reaches the pull request before you have seen it. cc-review writes the review as a local draft and shows you a preview: the summary, every inline comment with its file and line, and any replies it proposes in earlier threads. You approve it, ask for a change (reword a comment, drop one, or turn a request for changes into a plain comment), or skip it. What you approve is posted unchanged.

At post time, cc-review checks the PR again. Nothing is posted when the PR head moved since the analysis, when a review from this run is already on the PR, or when somebody else commented in the meantime. Bots and the accounts in `pr_posting.ignore_authors` do not count as somebody else. When another person did comment, cc-review shows you the new comments and asks whether to post anyway, skip, or re-run the review later. The same check runs before every approved thread reply or resolution. The run closes with one of five outcomes: `posted`, `skipped`, `withheld`, `stale`, or `failed`, each with its reason in the console summary.

Every comment keeps the same structure: its severity, why it matters, the suggested fix, and its source. A script checks each draft for that structure before the preview. The summary's Review Details line states how the findings came about: whether you went through them one by one, which test commands the run executed, and that failure scenarios come from reading the code. It never claims a check that did not happen.

## Review several PRs, and follow up

Run a bulk review to cover more than one pull request in a single pass:

```
/cc-review:review --bulk
```

This reviews the open PRs that request your review, plus the PRs you already reviewed with cc-review that have new commits since. Each PR is analyzed in its own worktree, and at the end you get one table to decide per PR: post the review, apply the suggested fixes (your own PRs only), post a short "no findings" note, or skip. Reviews you chose to post are drafted first; you see the previews one after another and approve, edit, or skip each before anything is posted. You can stop during the previews and continue later with `--resume`.

Instead of the default set, name the PRs yourself with `--prs 41,42`, take every open PR with `--all-open`, or select them with `--search`. Unattended, `--bulk --resume --unattended` runs without asking anything and posts each review as a plain comment; a draft that still fails the check, or a PR whose conversation changed since the analysis, is withheld.

When you review the same PR again, cc-review runs a follow-up: it reviews only the delta since your latest completed cc-review run, including the code you changed to fix earlier findings, rather than re-reporting the whole diff. Earlier concerns are verified explicitly and kept in their threads until they are addressed; their absence from a new review never proves a fix.

> [!NOTE]
> This page covers the commands you run. For how the reviewers, the two critics, and the fix loop produce the report, read [How it works](../how-it-works/index.md). For the full flag list, see the [Reference](../reference/index.md).

> [!NOTE]
> These commands were verified against cc-review <!-- guide:attr cc-review-version -->1.9.0<!-- /guide:attr -->.
