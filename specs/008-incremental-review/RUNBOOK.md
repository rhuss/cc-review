---
runbook_version: 1
feature: 008-incremental-review
status: passed
mode: light
steps_total: 4
step_results: passed,passed,passed,passed
drafted_at: 5061e77
drafted_fingerprint: 8dfd7f86b487a8c4f0a92417ab05d55adeb03528f9d9ebf8d21dd6f3608504ad
tested_at: 4891db9
tested_fingerprint: 8dfd7f86b487a8c4f0a92417ab05d55adeb03528f9d9ebf8d21dd6f3608504ad
updated: 2026-10-28
---

# Try it: Incremental PR Review

<!-- runbook-status -->
> **Status:** passed · 4 of 4 steps (4 passed) · Mode: light · Tested at 4891db9 · 2026-10-28
<!-- /runbook-status -->





## What you're testing

Follow the local review journey: check the tools, prepare a first review and an unchanged follow-up, compare rebased contributions, then verify earlier findings and stale publication evidence. These commands exercise the actual scope engine and shared Bash/Zsh preparation with real temporary Git histories and substituted hosting responses. They do not contact or change a live PR.

The offline walkthrough was executed during finish. Live provider and hosting actions remain outside this journey.

## Test environment

Run from this repository's root. No persistent fixtures are required. The tests create and clean up their own disposable Git repositories and fake hosting responses. Git, Python 3.9+, jq and yq are required; the shared preparation also checks Zsh when installed.

## Steps

### Step 1 of 4: Check the local tools (US1)

**Why this step:** Scope preparation uses Git and JSON/configuration tools independently of any coding agent.

**Needs:** A checkout containing this feature.

**Run:**

```bash
git --version
python3 --version
jq --version
yq --version
```

**What you should see:** Each tool prints its version; Python is 3.9 or newer.

**If you see something else:** Install the missing tool before continuing. This journey does not require GitHub authentication.

**Result:** Passed. Actual output:

```text
git version 2.56.0
Python 3.15.0
jq-1.8.2
yq (https://github.com/mikefarah/yq/) version v4.54.1
```

### Step 2 of 4: Prepare a first review and unchanged follow-up (US1)

**Why this step:** The shared command preparation must select full scope first, establish personal evidence, and skip new dispatch when the contribution is unchanged. It also fetches a genuinely missing current base object from a local Git remote.

**Needs:** Step 1.

**Run:**

```bash
python3 -B tests/test_review_scope.py ScopeTests.test_shared_shell_preparation_computes_scope_and_skips_unchanged_dispatch
```

**What you should see:** One test completes with `OK`. It executes the real preparation block and CLI, checking full then unchanged scope, expected reviewer coverage and skipped dispatch in Bash and, when available, Zsh.

**If you see something else:** Read the failed assertion and captured shell error. A Git/configuration error is different from a scope decision mismatch.

**Result:** Passed. Actual output:

```text
.
----------------------------------------------------------------------
Ran 1 test in 5.811s

OK
```

### Step 3 of 4: Separate a pure rebase from new author changes (US3)

**Why this step:** Upstream movement must not create unnecessary code-review work, while additional author changes must remain in scope.

**Needs:** Step 2.

**Run:**

```bash
python3 -B tests/test_review_scope.py ScopeTests.test_pure_rebase_has_no_code_review_but_request_is_acknowledged ScopeTests.test_mixed_rebase_reviews_only_new_contribution
```

**What you should see:** Two tests complete with `OK`. Real Git rebases prove unchanged contribution in one case and retain only the new author delta in the other; renewed-request acknowledgment remains independent.

**If you see something else:** Inspect the mode or changed-line mismatch. A conflict must produce an explained full fallback rather than an unsupported unchanged claim.

**Result:** Passed. Actual output:

```text
..
----------------------------------------------------------------------
Ran 2 tests in 3.010s

OK
```

### Step 4 of 4: Preserve earlier concerns and reject stale verification (US2)

**Why this step:** Missing rediscovery must not erase a finding, and stale conversation evidence must not establish completion.

**Needs:** Step 3.

**Run:**

```bash
python3 -B tests/test_review_scope.py VerificationTests.test_still_present_findings_survive_absence_from_new_review VerificationTests.test_absent_partial_and_unclear_findings_never_resolve VerificationTests.test_publication_refresh_rejects_a_changed_conversation
```

**What you should see:** Three tests complete with `OK`. A still-present Important concern remains carried without duplication; partial/unclear outcomes do not resolve threads; changed conversations invalidate prepared completion.

**If you see something else:** Keep the original finding open and inspect the exact activity/outcome mismatch. Do not test a failing resolution path against a production PR.

**Result:** Passed. Actual output:

```text
...
----------------------------------------------------------------------
Ran 3 tests in 0.035s

OK
```

## Not covered here

- Actual provider judgment and installed-agent prompt execution need a separate agent session with the updated plugin.
- Live GitHub review requests, approval UI, comments and thread resolutions are not exercised; hosting responses are substituted. Existing approval is still required before those actions.
- Full-suite and marketplace checks are recorded in the implementation review, rather than repeated in this short journey.

## Coverage

- US1: Actual shared preparation and CLI, personal baseline compatibility, current-object availability and unchanged dispatch.
- US3: Real pure/mixed rebases and renewed-request acknowledgment.
- US2: Explicit outcomes, carried findings and stale-publication rejection.
- Live installed-agent/provider integration remains outside this offline journey.

## Results

All four offline steps passed during finish. No live PR actions were performed.
