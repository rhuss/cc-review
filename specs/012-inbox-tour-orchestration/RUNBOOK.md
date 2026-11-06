---
runbook_version: 1
feature: 012-inbox-tour-orchestration
status: drafted
mode: light
steps_total: 3
step_results: pending,pending,pending
drafted_at: 1925550
drafted_fingerprint: ccc63dd9d07a814fa480ed7fdbb95cadfe20276a140cbf878b78bbe30d40f57e
tested_at:
tested_fingerprint:
updated: 2026-11-06
---

# Try it: Streamlined Inbox Report with Guided Tour and Fan-Out

<!-- runbook-status -->
> **Status:** drafted · 0 of 3 steps · Mode: light · Drafted at 1925550 · 2026-11-06
<!-- /runbook-status -->

## What you're testing

This feature reworks the `inbox` command: a scannable report (table plus a detailed assessment section), an opt-in guided tour of the attention items, and an opt-in fan-out that delegates to `review`/`triage`/`issue` and batches pull requests into `bulk` via a new explicit-list selector.

The deterministic parts are exercised by the test suite, which is what this runbook walks through in real order: first confirm the whole suite is green, then run the inbox report-and-contract tests that pin the US1 report structure and the US2/US3 tour and fan-out contract, then run the bulk explicit-list selector tests that pin the new FR-017/FR-018 behavior. The live, interactive `inbox` run against a real GitHub repository is listed under "Not covered here".

## Test environment

No fixtures. Every step runs a local test command in this checkout. Requirements: `bash`, `python3`, `jq`, and a working `make` (the repository's `make test` target wraps `bash tests/run.sh`).

## Steps

### Step 1 of 3: Confirm the full suite is green (US1)

**Why this step:** Establishes a clean baseline so any later surprise is clearly about this feature. The full suite also contains the new inbox and bulk-selector tests, so a green run already proves the feature's tests pass together with the rest.

**Needs:** A clean checkout of branch `012-inbox-tour-orchestration`.

**Run:**

```
make test
```

**What you should see:** The runner prints per-test lines and ends with a summary reporting zero failures (around 1456 assertions passing), and the command exits 0.

**If you see something else:** A non-zero exit or a `FAIL` line means a regression. Note the failing test name; if it is unrelated to inbox or bulk, your local environment may be missing `python3`, `jq`, or `gh`.

**Result:**

### Step 2 of 3: Run the inbox report and tour/fan-out contract tests (US2)

**Why this step:** Pins the user-visible behavior of the new report and the tour/fan-out contract: the five-column attention table, one detail block per item with a labeled "My take" and an evidence link, the brief lists and empty-group rendering (US1), and the guided-tour and fan-out contract assertions (US2 and US3).

**Needs:** Step 1 green (the runner and fixtures resolve).

**Run:**

```
bash tests/run.sh inbox_report
```

**What you should see:** The `test_inbox_report` entry runs the bundled unittest file (snapshot-fixture checks plus the `TourAndFanoutContract` cases) and reports them passing, with zero failures and exit 0.

**If you see something else:** If it reports 0 tests run, the filter matched nothing (check you are in the repo root). A failure here points at the report rendering or the tour/fan-out contract in `review/core/commands/inbox.md`.

**Result:**

### Step 3 of 3: Run the bulk explicit-list selector tests (US3)

**Why this step:** Pins the one genuinely new capability behind batch fan-out: `bulk-select.sh` resolving an explicit `--prs` list through the shared assessor, surfacing an ineligible pull request as excluded rather than dropping it, and rejecting conflicting selectors (FR-017, FR-018).

**Needs:** Step 1 green.

**Run:**

```
bash tests/run.sh bulk_select
```

**What you should see:** The `bulk_select` test family runs, including the explicit-list selection test, and reports all of them passing with zero failures and exit 0.

**If you see something else:** A failure in the explicit-list test points at the new `--prs` mode in `review/core/scripts/bulk-select.sh`; a failure in a pre-existing `bulk_select` test would indicate the new selector disturbed the shared selection path.

**Result:**

## Not covered here

- The live, interactive `inbox` run: rendering the report against a real GitHub repository, accepting the end-of-report tour prompt, paging through batches, and fanning out to `review`/`triage`/`issue`/`bulk`. This needs an authenticated `gh`, a repository with open items relevant to the authenticated user, and an interactive harness, so it is not a deterministic local command. It is specified as quickstart Scenarios 1 to 6 ([quickstart.md](quickstart.md)) to run by hand against a real repository.
- Cross-harness degradation (inline tour without subagents; text-handoff fan-out) on Codex and OpenCode, which requires running inside those harnesses.

## Coverage

- **US1 (streamlined report)**: covered by Steps 1 and 2 (report-structure and empty-group assertions). The live visual rendering is under "Not covered here".
- **US2 (guided tour)**: contract covered by Step 2 (`TourAndFanoutContract`). The interactive prompt, selection, and paging UX are under "Not covered here".
- **US3 (fan-out + bulk explicit list)**: the bulk explicit-list capability is covered by Step 3; the per-item and batch delegation contract is covered by Step 2. The live delegation to `review`/`triage`/`issue`/`bulk` is under "Not covered here".

## Results
