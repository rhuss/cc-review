---
runbook_version: 1
feature: 014-bulk-issue-assessment
status: passed
mode: light
steps_total: 6
step_results: passed,passed,passed,passed,passed,passed
drafted_at: c897426
drafted_fingerprint: 543f5bf5a82d523f3283308290084c1825a0dae84053093f7ece870a12ba0f3e
tested_at: 707d68b
tested_fingerprint: a8036d7794984394c5fbfb79040e7cfc47dd2be2448e753c4a561efd1bb7e23f
updated: 2026-11-23
---

# Try it: Bulk issue assessment with optional draft-PR fixes

<!-- runbook-status -->
> **Status:** passed · 6 of 6 steps (6 passed) · Mode: light · Tested at 707d68b · 2026-11-23
<!-- /runbook-status -->







## What you're testing

`issue --bulk` picks open issues nobody has handled yet, assesses each one in a fresh context, asks you once per issue whether to post the reply, and can turn small confirmed problems into draft pull requests. The journey goes from the offline checks of the deterministic helpers, through a read-only selection against this repository, to an interactive batch where you skip every post so nothing is written.

## Test environment

No fixtures. The steps need `python3` (3.9+), `jq`, an authenticated `gh`, and Claude Code with this branch's plugin installed (step 5).

## Steps

### Step 1 of 6: Run the feature's offline tests (US2)

**Why this step:** Selection, skip rules, paging, posting, resume and fix containment are scripts with fixture tests that need no network and no model.

**Needs:** nothing

**Run:**

```
python3 -B tests/test_issue_bulk.py
```

**What you should see:** A unittest summary ending in `OK` with about 131 tests run.

**If you see something else:** A failure names the test class (for example `SelectionTests` or `FixTests`); the branch is not ready.

**Result:** passed (agent). Expected `OK` with about 131 tests; actual: `Ran 131 tests in 221.773s` / `OK`.

### Step 2 of 6: Watch argument validation refuse a widening search (US2)

**Why this step:** The search can narrow the batch by labels and keywords, but it must never change the repository, the issue state or the order.

**Needs:** nothing

**Run:**

```
python3 -B review/core/scripts/issue_bulk.py validate --bulk --search 'label:bug is:closed'; echo "exit=$?"
```

**What you should see:** `Error: --search must not contain repo:, org:, ... or sort:; ...` followed by `exit=2`, and no GitHub call.

**If you see something else:** A JSON line instead of an error means forbidden qualifiers pass validation.

**Result:** passed (agent). Expected the qualifier error and `exit=2`; actual: `Error: --search must not contain repo:, ... or sort:; ...` and `exit=2`.

### Step 3 of 6: Select untouched issues from this repository, read-only (US2)

**Why this step:** This is the selection a real batch starts with, including skip reasons and paging, without creating a run or writing anything to GitHub.

**Needs:** authenticated `gh`

**Run:**

```
python3 -B review/core/scripts/issue_bulk.py select --repo rhuss/cc-review --limit 5 --scan 30 --out "${TMPDIR:-/tmp}/issue-bulk-selection.json"
```

**What you should see:** One JSON line with `scanned`, `selected` (up to 5), `skipped`, `ceiling_reached` and `exhausted`.

**If you see something else:** `Error:` with an authentication hint means `gh auth login` is needed; a network error must not produce the output file.

**Result:** passed (agent). Expected one JSON line with counts; actual: `{"scanned": 5, "selected": 5, "skipped": 0, "ceiling_reached": false, "exhausted": false}`.

### Step 4 of 6: Read who was selected and why others were skipped (US2)

**Why this step:** Every scanned issue must show up as selected or skipped with a reason, so nothing drops out silently.

**Needs:** Step 3

**Run:**

```
jq '{scanned, ceiling_reached, selected: [.selected[].number], skipped: [.skipped[] | {number, reason}]}' "${TMPDIR:-/tmp}/issue-bulk-selection.json"
```

**What you should see:** The newest open issues without a maintainer reply in `selected` (your own upstream reports count as untouched), and any issue with a maintainer PR listed under `skipped` with reason `maintainer_pr`. The number of selected plus skipped issues equals `scanned`.

**If you see something else:** An issue you already answered appearing in `selected` points at a skip-rule gap.

**Result:** passed (agent). Expected untouched issues selected and selected plus skipped equal to scanned; actual: `{"scanned":5,"ceiling_reached":false,"selected":[41,40,39,38,37],"skipped":[]}` (the maintainer's own upstream reports, none with a maintainer PR).

### Step 5 of 6: Install this branch's plugin (US1)

**Why this step:** The interactive command runs from the installed plugin, so Claude Code must load this branch's version.

**Needs:** nothing

**Run:**

```
make install
```

**What you should see:** The marketplace is added or updated and `cc-review` is (re)installed without errors.

**If you see something else:** A validation error from `claude plugin` names the manifest problem.

**Result:** passed (agent). Expected a clean reinstall; actual: marketplace updated, `Successfully installed plugin: cc-review@cc-review-plugin-development (scope: user)`; the marketplace source is this worktree and the installed copy contains `issue-bulk.md`.

### Step 6 of 6: Run an interactive batch and skip every post (US1)

**Why this step:** This exercises assessment workers, the one-prompt-per-issue approval and the final report, while choosing Skip keeps GitHub untouched.

**Needs:** Step 5, a new Claude Code session in a checkout of rhuss/cc-review

**Do:**

1. In a new Claude Code session inside a checkout of rhuss/cc-review, run `/cc-review:issue --bulk --limit 2`.
2. For each issue, read the full reply draft shown in the message, then answer the prompt with Reply: Skip and, when offered, Follow-up: Leave it.
3. Read the final report.

**What you should see:** Two issues assessed, each shown once with the full comment text and a two-question prompt (Reply and, where it applies, Follow-up); the report lists both as skipped by you, plus the coverage block with scanned and skipped counts. No comment, label or pull request appears on GitHub.

**If you see something else:** A post without your approval, or a prompt that does not show the full text, is a blocker.

**Result:** passed (maintainer). Two issues were assessed and shown with the full comment and skipped; nothing was posted. Observation: the approval was asked in plain text because the maintainer's global draft-approval rule overrode the dropdown; the approval step now shows the draft, runs a separate tool call, then asks (commit 0d2ae4b), and the global rule allows that pattern.

## Not covered here

- Posting replies and opening draft pull requests on GitHub: this writes under your account, so try it in a disposable repository (quickstart.md, "End-to-end in a disposable test repository"). The fix path, containment checks and resume behavior are covered by the offline tests in step 1.

## Coverage

- US1 (assess and answer a batch): steps 5 and 6, posting itself left to a disposable repository.
- US2 (transparent selection): steps 1 to 4.
- US3 (fixes as draft PRs), US4 (linked PR handoff), US5 (resume): offline tests in step 1 only; live runs need a disposable repository.

## Results

6 steps: 6 passed, 0 failed, 0 skipped. The helpers select only untouched open issues with stated skip reasons, refuse searches that would widen scope, and the interactive batch assesses each issue and asks once per issue without writing to GitHub when every post is skipped. Posting and draft-PR fixes were exercised by the offline tests only.
