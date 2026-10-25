# Quickstart: Validating Bulk Review and Bulk Triage

## Prerequisites

- A scratch GitHub repository you can push to, with `origin` pointing at it, `gh auth status` OK.
- cc-review installed from this branch.
- A second GitHub account (or a collaborator) to open PRs that request your review, or use `--all-open` / `--search` on your own PRs.

## Automated checks

```bash
make test                        # all tests
bash tests/run.sh bulk           # bulk-state / bulk-select / pr-worktree / bulk-apply tests
bash tests/run.sh shim           # shim flag pass-through
```

Expected: `N passed, 0 failed`.

## Scenario 1: Bulk review, deferred (US1)

1. Open PRs A, B, C in the scratch repo, each changing one file. Request your review on A and B. Leave C unrequested.
2. In your local clone, check out an unrelated branch and leave an uncommitted change. Record `git status --porcelain` and `git branch --show-current`.
3. Run `/review --bulk`.
4. Expect:
   - A and B are analyzed and C is not.
   - No prompt appears during analysis.
   - A decision table lists A and B with counts and report paths under `.cc-review/bulk/<run-id>/pr-<n>/review-findings.md`.
5. Choose "Change actions per PR": post on A, skip on B.
6. Expect:
   - A gets a review whose summary contains `cc-review:run-id:<run-id>/pr-<A>`.
   - The review's commit equals A's head (`gh api repos/{o}/{r}/pulls/<A>/reviews --jq '.[-1].commit_id'`).
   - B gets nothing.
7. Check that `git status --porcelain` and the branch are unchanged (apart from nothing, since `.cc-review/bulk/` is ignored).
8. Run `/review --bulk` again. Expect A to be excluded as "reviewed-at-head" and B to be selected again.

## Scenario 2: Re-review after new commits (US1 scenario 6, FR-004)

Push a commit to A, then run `/review --bulk`. Expect A to be selected even though GitHub dropped your review request.

## Scenario 3: Resume (US3)

1. Run `/review --bulk --all-open` with 3 PRs. Interrupt the session after the first PR shows `analyzed` in `state.md`.
2. Push a commit to the second PR.
3. Run `/review --bulk --resume`. Expect:
   - The run id is printed.
   - PR 1 is not re-analyzed, while PRs 2 and 3 are analyzed.
   - The table shows all three.
4. Interrupt during apply after the first post. Resume, and expect no duplicate review on that PR.

## Scenario 4: Unattended (US4)

Run `/review --bulk --all-open --unattended`. Expect:
- No prompts.
- Every PR with findings gets a `COMMENT` review.
- PRs without findings get the no-findings marker review.
- No PR branch changes.
- `summary.md` exists.

## Scenario 5: Bulk triage (US2)

1. On two of your own PRs, add bot-style review comments (or let CodeRabbit/Copilot comment) and one human comment on one of them.
2. Run `/triage --bulk`. Expect:
   - Only PRs with unresolved threads are selected.
   - Fixes are committed in worktrees, with no pushes or replies yet.
   - The decision table appears, then the human comment prompt.
3. Apply one PR and skip the other. Expect:
   - The applied PR gets a push, replies, and resolved threads.
   - The skipped PR is untouched.
   - `.cc-review/.triage-state.json` in your repo records the replies.
4. With your own PR branch checked out locally and one unpushed local commit, run `/triage --bulk`. Expect that PR to be marked "local commits not pushed" with only replies offered.

## Scenario 6: Single PR not checked out (US6)

On `main`, run `/review --pr <A>` where A changes a file that differs from `main`. Expect the findings to reference A's version (for example, a line that exists only in A), and the working tree to stay unchanged.

## Scenario 7: Validation errors

```text
/review --bulk --pr 3            → Error: --bulk and --pr cannot be combined; --pr names a single PR
/review --bulk --all-open --search x → Error: --all-open and --search are mutually exclusive
/triage --bulk --all-open        → Error: --all-open is not supported by triage; ...
/review --bulk --limit 0         → Error: --limit must be a positive integer, got '0'
/review --bulk --search 'repo:x/y' → Error: --search may not contain 'repo:'; ...
```

## Scenario 8: One failing PR does not stop the run (SC-004)

1. Open 5 PRs and run `/review --bulk --all-open --limit 5`.
2. While the first PR is analyzed, delete the head branch of the fourth PR on GitHub (`git push origin --delete <branch>`).
3. Expect:
   - The fourth PR ends as `failed` with a checkout reason in `state.md`.
   - The other 4 PRs are analyzed and appear in the decision table.
   - The summary names the failed PR and says a resume retries it.

## Scenario 9: Ten PRs in one session (SC-005)

Open 10 PRs and run `/review --bulk --all-open --limit 10` in one session. Expect:
- The run finishes (status `finished` after the decision step) without the session running out of context.
- `state.md` lists all 10 PRs with counts, report paths and a decision.
- The bulk-select timing check passes: `bash tests/run.sh bulk_select_50` (50 PRs selected in under 10 s).

## Scenario 10: Unattended triage with failures (SC-007)

1. Prepare three of your own PRs with bot comments. Add a human comment to the first one.
2. Make the second one fail: push a commit to it from another clone after selection, or revoke push access for the session, so its apply hits a stale head or a denied push.
3. Close the third PR while the run analyzes the first.
4. Run `/triage --bulk --unattended`. Expect:
   - Zero prompts from start to end.
   - The first PR gets its bot fixes pushed and its bot replies posted; the human comment stays unanswered and is listed under "Needs attention" in `summary.md`.
   - The second PR ends as `stale` or `cannot-push`, with nothing posted.
   - The third PR ends as `closed`.
   - `summary.md` lists all three with their outcomes.
