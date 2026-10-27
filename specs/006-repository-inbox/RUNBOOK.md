---
runbook_version: 1
feature: 006-repository-inbox
status: drafted
mode: light
steps_total: 5
step_results: pending,pending,pending,pending,pending
drafted_at: 66bd595
drafted_fingerprint: efb103376ca0deaec00e0863b2f136763ce0987433cf02b1fa23494edbe8594f
tested_at:
tested_fingerprint:
updated: 2026-10-26
---

# Try it: Repository Inbox

<!-- runbook-status -->
> **Status:** drafted · 0 of 5 steps · Mode: light · Drafted at 66bd595 · 2026-10-26
<!-- /runbook-status -->

## What you're testing

Try the new read-only inbox from a coding agent: establish access, load the updated plugin, inspect the repository overview, focus on selected item types, and see an invalid argument rejected. The report must explain relevance, who acts next, evidence and missing coverage.

The live examples use rhuss/cc-review. Its items can change between runs, so success depends on scope, evidence and honest coverage rather than a fixed number of action items.

## Test environment

No fixtures are created. Use your existing GitHub authentication and the plugin installation from this checkout. Refreshing the plugin and opening a fresh agent session are user actions in Step 2.

## Steps

### Step 1 of 5: Check prerequisites (US4)

**Why this step:** The inbox reuses Python and your existing GitHub access.

**Needs:** A terminal at the repository root.

**Run:**

```bash
python3 --version
gh auth status
```

**What you should see:** Python 3.9 or newer and an authenticated GitHub account with access to rhuss/cc-review. Authentication status must not expose an unredacted token.

**If you see something else:** Install the missing prerequisite or authenticate gh for the repository's host before continuing.

**Result:**

### Step 2 of 5: Load the new command (US2)

**Why this step:** The coding agent must load the inbox adapter from the updated plugin.

**Needs:** Step 1 and this feature's checkout.

**Do:**

1. Refresh your existing cc-review plugin installation from this checkout using the [README installation instructions](../../README.md#installation) for your harness.
2. Open a fresh coding-agent session at this checkout.
3. Confirm that the installed inbox command or skill is available.

**What you should see:** The agent can discover inbox alongside review and triage.

**If you see something else:** Check that the installation points to this checkout and that the agent session loaded the refreshed plugin.

**Result:**

### Step 3 of 5: Read your repository overview (US1)

**Why this step:** See relevant work grouped by who acts next.

**Needs:** Step 2.

**Do:**

1. In your coding agent, invoke the inbox command or skill with `--repo rhuss/cc-review --limit 2`. In Codex, use `$cc-review:inbox --repo rhuss/cc-review --limit 2`.
2. Inspect the scope, the three groups, each entry's relevance and evidence, and the coverage account.

**What you should see:** Needs your attention, Waiting on others, and No current action, including empty groups. Each entry has a type/title/link and a supported next step or waiting explanation. Missing or truncated context is marked. If Discussions are disabled, the report explains that they were unavailable.

**If you see something else:** A bare metadata list, an unsupported obligation, missing evidence, hidden coverage gaps or an automatically launched action is a mismatch.

**Result:**

### Step 4 of 5: Focus on issues and Discussions (US2)

**Why this step:** Verify that type and history filters change the overview's scope.

**Needs:** Step 3.

**Do:**

1. Invoke inbox with `--repo rhuss/cc-review --type issue,discussion --since 2026-10-01 --limit 5`. In Codex, use `$cc-review:inbox --repo rhuss/cc-review --type issue,discussion --since 2026-10-01 --limit 5`.
2. Compare the header, item types and coverage with the previous report.

**What you should see:** Only issues and Discussions are selected. The report states the explicit updated-since date and the five-items-per-type bound. A valid empty result is distinguished from unavailable Discussions.

**If you see something else:** PR entries, an undisclosed date filter or a claim of complete coverage despite missing sources is a mismatch.

**Result:**

### Step 5 of 5: Reject an invalid filter (US4)

**Why this step:** Mistyped options must stop before service access.

**Needs:** The terminal from Step 1.

**Run:**

```bash
python3 -B review/core/scripts/inbox.py --type unknown
```

**What you should see:** An argument error naming the accepted types and exit status 2. No JSON inbox is produced.

**If you see something else:** A successful empty inbox or an authentication request means invalid input was not rejected early enough.

**Result:**

## Not covered here

The live repository may not contain requested reviews, manual reviews followed by new commits, unresolved PR feedback or personal Discussion conversations. Those collection structures and failure cases are covered by offline tests; next-actor judgments for such real conversations still need a representative repository. No remote fixture issues, PRs or comments are created by this runbook.

## Coverage

- US1: Step 3 exercises personal discovery, grouping, explanations and evidence on available live items.
- US2: Steps 2 and 4 exercise command availability, explicit repository, type selection, history and limits.
- US3: Partly covered through available item context in Step 3; the specific review/reply scenarios depend on live repository activity.
- US4: Steps 1, 3 and 5 exercise prerequisites, visible unavailable/truncated coverage, and argument errors.
- Read-only behavior is verified by the automated CLI integration. This runbook must leave follow-up actions as suggestions.

## Results
