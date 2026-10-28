---
runbook_version: 1
feature: 007-inbox-action-alignment
status: drafted
mode: light
steps_total: 4
step_results: pending,pending,pending,pending
drafted_at: 134e7da
drafted_fingerprint: 9ea978945663f727311026dd1f27b6224e7b608fa39d626e501b04b6401c350e
tested_at:
tested_fingerprint:
updated: 2026-10-28
---

# Try it: Inbox PR Action Alignment

<!-- runbook-status -->
> **Status:** drafted · 0 of 4 steps · Mode: light · Drafted at 134e7da · 2026-10-28
<!-- /runbook-status -->

## What you're testing

This journey checks how the read-only inbox distinguishes first or substantial review from continued triage on existing review feedback. It then follows each action through its bulk command, where the PR role and proposed work are shown separately. A PR can qualify for both actions; handling one does not clear the other.

## Test environment

- No fixtures. Use a repository with open PRs, at least one eligible for review and one with existing cc-review feedback eligible for triage. The commands need the cc-review plugin and an authenticated GitHub CLI session. Applying a triage plan or posting a review can change a real PR; choose Skip when you only want to inspect the flow.

## Steps

### Step 1 of 4: Confirm repository access (US1)

**Why this step:** The inbox uses the current repository context and authenticated GitHub account to collect PR activity.

**Needs:** A checkout of the repository you want to inspect.

**Run:**

```bash
gh auth status && gh repo view --json nameWithOwner,url
```

**What you should see:** GitHub CLI reports an authenticated account and the repository owner/name and URL for the intended repository.

**If you see something else:** Sign in with `gh auth login` or switch to the intended repository before continuing.

**Result:**

### Step 2 of 4: Inspect the PR inbox (US1)

**Why this step:** The inbox shows current review and triage eligibility from shared PR evidence without changing the repository or PRs.

**Needs:** Step 1 of 4; the `inbox` command must be available from the installed cc-review plugin.

**Run:**

```text
inbox --type pr
```

**What you should see:** The PR report states its scope and coverage. Each PR explains whether review, triage, or both apply, along with evidence and any uncertainty. Review is for a new or substantial review; triage continues owned feedback or handles feedback on your PR.

**If you see something else:** Check that the repository has PRs in the inbox scope and review any collection warnings or incomplete-context notes before treating the list as exhaustive.

**Result:**

### Step 3 of 4: Continue existing PR feedback (US2)

**Why this step:** Bulk triage continues eligible feedback while keeping author and reviewer roles visible and separate.

**Needs:** Step 2 of 4; at least one PR with eligible existing feedback.

**Run:**

```text
triage --bulk --limit 10
```

**What you should see:** The selection and decision summary includes each PR's role, selection reason, proposed action, and execution status. Reviewer triage verifies existing cc-review findings and does not offer a fix commit. Incomplete or changed activity is left for reassessment.

**If you see something else:** Check the selection exclusions, role and coverage warnings, and run state under `.cc-review/bulk/` before deciding whether the PR needs a new triage run.

**Result:**

### Step 4 of 4: Review PRs independently (US2)

**Why this step:** Bulk review handles new or substantial review work independently from triage, even when both actions apply to one PR.

**Needs:** Step 2 of 4; at least one open PR eligible for review.

**Run:**

```text
review --bulk --limit 10
```

**What you should see:** The review selection and decision summary shows its own scope, proposed action, and status. A triage action from Step 3 of 4 does not by itself satisfy this review action. Skip any PR whose review you do not want to post.

**If you see something else:** Check the review selection reason, draft status, requested-review state, and the run's recorded scope before concluding that triage suppressed review.

**Result:**

## Not covered here

- Issues and Discussions are outside this PR-only feature.
- Incremental diff-scoped review after a PR head changes is a separate proposal in brainstorm #09 and is not computed by this feature.

## Coverage

- US1: inspect the read-only inbox and its independent review and triage eligibility.
- US2: follow eligible PRs into bulk triage and bulk review while preserving their separate actions.
- Not covered: issue and Discussion actions, and delta-scoped incremental re-review (separate proposal #09).

## Results
