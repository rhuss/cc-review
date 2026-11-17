---
runbook_version: 1
feature: 013-ci-automation
status: drafted
mode: light
steps_total: 5
step_results: pending,pending,pending,pending,pending
drafted_at: 80e8555
drafted_fingerprint: 2e2e9667c972c19829f69fa6fb88c9dd2956c8786c2b684894094fc9a99607ab
tested_at:
tested_fingerprint:
updated: 2026-11-11
---

# Try it: Unattended CI setup and routing

<!-- runbook-status -->
> **Status:** drafted · 0 of 5 steps · Mode: light · Drafted at 80e8555 · 2026-11-11
<!-- /runbook-status -->


## What you're testing

Generate a pinned CI installation in a temporary directory, inspect its settings,
route an issue event without network access, then disable and remove that demo.
This exercises local management and event selection. It does not run a paid model
or publish to GitHub.

## Test environment

No fixtures have been started. Step 2 creates a disposable local directory and
Step 5 removes it. Run all steps from the cc-review checkout in the same shell.

## Steps

### Step 1 of 5: Check local prerequisites (US4)

**Why this step:** Confirm the local helper and its documented tools are available.

**Needs:** A checkout containing this feature.

**Run:**

```bash
python3 --version
gh --version
yq --version
git rev-parse --show-toplevel
```

**What you should see:** Python 3.9 or newer, gh, Mike Farah yq v4 and the current
repository root. This step makes no service request.

**If you see something else:** Install the missing tool or switch to the checkout.

**Result:**

### Step 2 of 5: Create an isolated demo directory (US4)

**Why this step:** Keep generated caller/config files away from the real project.

**Needs:** Step 1.

**Run:**

```bash
export CC_CI_DEMO_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/cc-review-demo.XXXXXX")"
printf '%s\n' "$CC_CI_DEMO_ROOT"
```

**What you should see:** A newly generated temporary directory path.

**If you see something else:** Check temporary-directory permissions before continuing.

**Result:**

### Step 3 of 5: Generate and inspect the pinned installation (US4)

**Why this step:** See the managed workflow, configuration and optional App manifest.

**Needs:** Step 2 in the same shell.

**Run:**

```bash
python3 -B review/core/scripts/ci.py setup --root "$CC_CI_DEMO_ROOT" --ref "$(git rev-parse HEAD)"
cat "$CC_CI_DEMO_ROOT/.cc-review/ci.yml"
cat "$CC_CI_DEMO_ROOT/.github/workflows/cc-review.yml"
```

**What you should see:** JSON naming generated files, schema version 1 with enabled
triggers/commands, and a caller whose workflow ref and integration_ref use the same
40-character current commit. No credential values are present.

**If you see something else:** Inspect the helper's precise schema/pin/path error;
this demo must not overwrite an unrelated workflow.

**Result:**

### Step 4 of 5: Route a new issue without service access (US1)

**Why this step:** Verify that an enabled event becomes an assessment request.

**Needs:** Step 3.

**Run:**

```bash
python3 - <<'PY'
import json, os
from pathlib import Path
root = Path(os.environ['CC_CI_DEMO_ROOT'])
(root / 'event.json').write_text(json.dumps({'action': 'opened', 'issue': {'number': 7}, 'sender': {'login': 'demo'}, 'repository': {'full_name': 'demo/repo'}}))
PY
python3 -B review/core/scripts/ci.py select --repo demo/repo --event issues --event-file "$CC_CI_DEMO_ROOT/event.json" --config "$CC_CI_DEMO_ROOT/.cc-review/ci.yml"
```

**What you should see:** One selected request (count 1), number 7, operation assess,
and source event in the matrix JSON. Selection alone runs no model and writes no
GitHub comment.

**If you see something else:** Check enabled and triggers.issue_opened in the demo
configuration. GitHub runner output variables can redirect output into their files;
use an ordinary local terminal for this walkthrough.

**Result:**

### Step 5 of 5: Disable routing and clean up (US4)

**Why this step:** Confirm that disable prevents work and removal touches only the demo.

**Needs:** Step 4 in the same shell.

**Run:**

```bash
python3 -B review/core/scripts/ci.py disable --root "$CC_CI_DEMO_ROOT"
python3 -B review/core/scripts/ci.py select --repo demo/repo --event issues --event-file "$CC_CI_DEMO_ROOT/event.json" --config "$CC_CI_DEMO_ROOT/.cc-review/ci.yml"
python3 -B review/core/scripts/ci.py disable --root "$CC_CI_DEMO_ROOT" --remove
rm -rf -- "$CC_CI_DEMO_ROOT"
unset CC_CI_DEMO_ROOT
```

**What you should see:** Disabled confirmation, count 0 and a skipped selection,
then managed-file removal confirmation. The actual project configuration is untouched.

**If you see something else:** Stop if the temporary path was lost; do not substitute
a real project directory for the cleanup target.

**Result:**

## Not covered here

Live publication, concurrency, fork review and model/provider/App execution require
a configured disposable GitHub repository and credentials. Those checks are tracked
in [issue #17](https://github.com/rhuss/cc-review/issues/17). Offline regression tests
cover policy behavior separately; they are not live-run evidence.

## Coverage

US1: local issue-event routing. US4: setup, configuration inspection and disable.
US2 and US3 need live authorized comments and Actions concurrency/sweep runs;
follow docs/CI.md and the live acceptance issue for those checks.

## Results
