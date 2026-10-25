# Brainstorm: Bulk Review and Bulk Triage

**Date:** 2026-10-25
**Status:** active

## Problem Framing

Both commands work on exactly one PR. `review` takes `--pr <n>` or auto-detects the current branch; `triage` resolves one PR and asks the user to pick when several candidates exist. A reviewer with a queue of requested reviews, or an author with several PRs collecting bot comments, has to run the command once per PR and switch branches by hand.

A related latent problem: `review --pr <n>` gets the changed file list from `gh pr diff`, but reviewer agents read file contents from the local working tree. Reviewing a PR that is not checked out reads the wrong code. Any bulk mode has to check each PR out, and fixing that also fixes the single-PR case.

There is a useful hook already: posted reviews carry a `<!-- cc-review:run-id: -->` marker (review Step 7.5d), so "already reviewed by cc-review" is detectable.

## Approaches Considered

### A: Selector flags on existing commands + shared bulk orchestrator
- Pros: no new commands, SKILL.md shims stay unchanged across all three harnesses; one place for selection, worktree handling, state and resume; reuses the single-PR flow per PR unchanged; worktree isolation fixes the wrong-tree problem.
- Cons: `review.md` and `triage.md` grow another entry branch; argument parsing has to keep bulk and single-PR flags apart.

### B: Separate `review-all` / `triage-all` commands
- Pros: clean argument surface per command.
- Cons: two more shims per harness (six files); still needs a shared core for selection and resume, or duplicates it.

### C: Sequential checkout in the main working tree, no subagents
- Pros: smallest implementation.
- Cons: mutates the user's working tree and fails on a dirty tree; the main context fills after a few PRs (review.md alone is ~56 KB of instructions plus findings per PR).

## Decision

Approach A. `review` and `triage` gain a `--bulk` mode backed by one shared orchestrator in `core/`. The orchestrator selects PRs, creates one git worktree per PR, and runs the existing single-PR flow inside it, one subagent per PR so the main context only holds per-PR summaries.

## Key Requirements

**PR selection (review)**
- Default: open PRs where the user is a requested reviewer (`review-requested:@me`) and cc-review has not posted a review since the PR's current head commit.
- `--all-open`: every open PR in the repo without an up-to-date cc-review review (maintainer view).
- `--search '<gh query>'`: arbitrary GitHub search query as the selector, still filtered by the "not yet reviewed at this head" rule.

**PR selection (triage)**
- The user's own open PRs that have unresolved review threads (bot or human).
- Fixes are committed and pushed per PR branch, as single-PR triage does today.

**Interaction modes (both commands)**
- Deferred (default): run analysis for every PR without pausing, write all intermediate results to a bulk state document, then present one consolidated table where the user picks per-PR actions (post, fix, skip) in a single pass.
- Unattended (`--unattended`): apply a fixed policy with no prompts and finish with a summary report.

**Resumability (deferred mode)**
- The bulk state document (human-readable Markdown plus machine-readable JSON, under `.cc-review/bulk/<run-id>/`) records the selected PRs, each PR's head SHA at analysis time, per-PR status (pending, analyzed, actioned, failed) and the findings or triage assessment.
- `--resume [<run-id>]` picks up an interrupted run: skips PRs already analyzed at the same head SHA, re-analyzes PRs whose head moved, continues with pending ones, then goes to the decision step.

**Isolation**
- Each PR is checked out in its own git worktree; the user's working tree is never touched. Worktrees are removed after the PR is done (kept on failure for inspection).
- One PR failing (checkout conflict, gh error, reviewer crash) marks that PR failed in the state document and does not stop the run.

## Open Questions

- Default cap on PRs per run (`--limit`), and what happens when the selection exceeds it.
- Sequential or parallel per-PR subagents, and if parallel, what concurrency limit (rate limits on gh and external reviewers like CodeRabbit).
- Unattended review policy: post findings as comments only, or also auto-fix on the user's own PRs? Never auto-fix someone else's PR seems a safe floor.
- "Reviewed since head commit" needs the head SHA in the cc-review marker; does the marker change format, and how are older markers without a SHA treated?
- Should single-PR `review --pr <n>` also switch to worktree checkout when the PR is not the current branch, or only warn?
- Where does bulk mode read per-repo config when worktrees live outside the repo root (`.cc-review/` layering)?
- Retention policy for `.cc-review/bulk/` state directories.
