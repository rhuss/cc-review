---
runbook_version: 1
feature: 009-review-convergence
status: passed
mode: light
steps_total: 5
step_results: passed,passed,passed,passed,passed
drafted_at: c177b55
drafted_fingerprint: b42d11c61b60c2ba581764aba5e72d08ab5261ed9569aaf0d1453a74a82fd654
tested_at: 3c8eb4c
tested_fingerprint: b42d11c61b60c2ba581764aba5e72d08ab5261ed9569aaf0d1453a74a82fd654
updated: 2026-10-28
---

# Try it: Review Convergence

<!-- runbook-status -->
> **Status:** passed · 5 of 5 steps (5 passed) · Mode: light · Tested at 3c8eb4c · 2026-10-28
<!-- /runbook-status -->






## What you're testing

Follow one review through remembered manual feedback, an outstanding material concern, and a verified-fix outcome. Then exercise the shared coordinator blocks and stale-evidence protection.

This is a repeatable, partly testable local journey through the real helpers. Its explicitly synthetic semantic outcomes represent code inspections; they do not claim that a hosted PR was inspected. A live agent's interpretation of prose remains a separate check.

Run every step from the repository root in the same terminal so the temporary-directory variable survives.

## Test environment

No background services, remote resources or paid fixtures are needed. Step 1 creates disposable JSON inputs under a fresh temporary directory; Step 5 removes them. The agent executed this local journey during finish; Step 5 removed the disposable inputs. No remote resources were created. Python 3 and jq are checked in Step 1.

## Steps

### Step 1 of 5: Prepare a manual-review snapshot (US1)

**Why this step:** Start with an earlier manual review and no completed code-coverage baseline.

**Needs:** Python 3 and jq available on PATH; repository root as the current directory.

**Run:**

```bash
command -v python3
command -v jq
export REVIEW_CONVERGENCE_DEMO=$(mktemp -d)
python3 -B - <<'PY'
import json, os, runpy
from pathlib import Path
fixtures = runpy.run_path('tests/test_review_continuity.py')
path = Path(os.environ['REVIEW_CONVERGENCE_DEMO']) / 'history-input.json'
path.write_text(json.dumps(fixtures['snapshot'](comments=[])))
print(path)
PY
```

**What you should see:** Paths to Python and jq, followed by a history-input.json path in a new temporary directory. The fixture contains a personal manual review about data loss, not a completion marker.

**If you see something else:** Missing commands must be installed first; a missing tests file means the terminal is outside the repository root.

**Result:** Passed by the agent during finish. Expected tools and a disposable input file; actual Python/jq paths and the created JSON file were confirmed.

Actual output:

```text
/opt/homebrew/bin/python3
/opt/homebrew/bin/jq
/var/folders/3v/16m6pn090hl4d60grm1057ww0000gn/T/tmp.DdZFoLJHT4/history-input.json
```

### Step 2 of 5: Read the preserved review history (US1)

**Why this step:** Show that manual feedback establishes conversation continuity without establishing a code baseline.

**Needs:** Step 1 and the same terminal.

**Run:**

```bash
python3 -B review/core/scripts/review_continuity.py prepare \
  --input "$REVIEW_CONVERGENCE_DEMO/history-input.json" \
  > "$REVIEW_CONVERGENCE_DEMO/history.json"
jq '{follow_up, complete, sources, has_baseline:has("baseline")}' \
  "$REVIEW_CONVERGENCE_DEMO/history.json"
```

**What you should see:** follow_up and complete are true, has_baseline is false, and review:12 retains the earlier review body and source link.

**If you see something else:** Inspect limitations in history.json. Incomplete or malformed collections must not be treated as a clean first review.

**Result:** Passed by the agent during finish. Expected personal follow-up with complete history and no coverage baseline; actual follow_up=true, complete=true, has_baseline=false and source review:12.

Actual output:

```text
{
  "follow_up": true,
  "complete": true,
  "sources": [
    {
      "data": {
        "author": {
          "login": "me"
        },
        "body": "Please avoid losing saved data.",
        "databaseId": 12,
        "state": "COMMENTED",
        "submittedAt": "2026-10-28T09:00:00Z",
        "url": "https://github.com/acme/widget/pull/7#pullrequestreview-12"
      },
      "kind": "review",
      "source_id": "review:12",
      "url": "https://github.com/acme/widget/pull/7#pullrequestreview-12"
    }
  ],
  "has_baseline": false
}
```

### Step 3 of 5: Keep an unresolved material concern visible (US2)

**Why this step:** No new findings must not hide an earlier substantive concern.

**Needs:** Step 2. The semantic outcome below is synthetic fixture data representing an inspected unchecked save failure.

**Run:**

```bash
python3 -B - <<'PY'
import json, os
from pathlib import Path
folder = Path(os.environ['REVIEW_CONVERGENCE_DEMO'])
history = json.loads((folder / 'history.json').read_text())
concern = dict(source_id='review:12', status='open', material=True,
               question_open=False, code_checked=True,
               evidence='Synthetic inspection fixture: failed save loses user data.')
assessment = dict(history=history, head_oid=history['head_oid'],
                  fingerprint=history['fingerprint'], findings=[], decisions=[],
                  concerns=[concern], coverage_complete=True, verification_complete=True)
(folder / 'assessment.json').write_text(json.dumps(assessment))
PY
python3 -B review/core/scripts/review_continuity.py assess \
  --input "$REVIEW_CONVERGENCE_DEMO/assessment.json" \
  | jq '{conclusion, counts, findings}'
```

**What you should see:** outstanding material concerns, open_material equal to 1, and an empty new-findings array. The existing conversation remains the place for that concern.

**If you see something else:** Inspect the full assessor output and its limitations. An empty findings array alone is not an all-clear.

**Result:** Passed by the agent during finish. Expected an open material concern without a new duplicate; actual conclusion="outstanding material concerns", open_material=1 and findings=[].

Actual output:

```text
{
  "conclusion": "outstanding material concerns",
  "counts": {
    "addressed": 0,
    "new_material": 0,
    "nonblocking": 0,
    "open_material": 1
  },
  "findings": []
}
```

### Step 4 of 5: Conclude after a verified-fix snapshot (US2)

**Why this step:** Demonstrate a valid stopping point without inventing optional improvements. This fixture supplies a new pinned head and a verified addressed outcome.

**Needs:** Step 3. This remains synthetic semantic evidence, not a claim of a real PR fix.

**Run:**

```bash
python3 -B - <<'PY'
import json, os
from pathlib import Path
folder = Path(os.environ['REVIEW_CONVERGENCE_DEMO'])
snapshot = json.loads((folder / 'history-input.json').read_text())
snapshot['head_oid'] = 'b' * 40
(folder / 'fixed-history-input.json').write_text(json.dumps(snapshot))
PY
python3 -B review/core/scripts/review_continuity.py prepare \
  --input "$REVIEW_CONVERGENCE_DEMO/fixed-history-input.json" \
  > "$REVIEW_CONVERGENCE_DEMO/fixed-history.json"
python3 -B - <<'PY'
import json, os
from pathlib import Path
folder = Path(os.environ['REVIEW_CONVERGENCE_DEMO'])
history = json.loads((folder / 'fixed-history.json').read_text())
assessment = json.loads((folder / 'assessment.json').read_text())
assessment.update(history=history, head_oid=history['head_oid'], fingerprint=history['fingerprint'])
assessment['concerns'][0].update(status='addressed', material=False,
    evidence='Synthetic verified-fix fixture: save failures now preserve the data.')
(folder / 'fixed-assessment.json').write_text(json.dumps(assessment))
PY
python3 -B review/core/scripts/review_continuity.py assess \
  --input "$REVIEW_CONVERGENCE_DEMO/fixed-assessment.json" \
  | jq '{conclusion, complete, counts}'
```

**What you should see:** no outstanding material concerns, complete true, one addressed source and zero open material sources. Nothing is posted, approved or merged.

**If you see something else:** Inspect limitations and verify that head and fingerprint belong to the same snapshot. Reusing stale semantic judgments must not produce a clean result.

**Result:** Passed by the agent during finish. Expected a clean conclusion after the verified-fix fixture; actual complete=true, addressed=1, open_material=0 and conclusion="no outstanding material concerns".

Actual output:

```text
{
  "conclusion": "no outstanding material concerns",
  "complete": true,
  "counts": {
    "addressed": 1,
    "new_material": 0,
    "nonblocking": 0,
    "open_material": 0
  }
}
```

### Step 5 of 5: Exercise shared workflow wiring and clean up (US3)

**Why this step:** Check the real coordinator code blocks for full/incremental histories, manual summaries, partial collection and stale assessment context.

**Needs:** Repository root; the earlier steps can remain as inspection artifacts until this step finishes.

**Run:**

```bash
python3 -B tests/test_review_continuity.py WorkflowTests
if [ -n "${REVIEW_CONVERGENCE_DEMO:-}" ]; then
  rm -rf -- "$REVIEW_CONVERGENCE_DEMO"
  unset REVIEW_CONVERGENCE_DEMO
fi
```

**What you should see:** The workflow test group passes. It uses a local fake hosting boundary, executes the real embedded shell blocks, and performs no live PR mutations. The temporary JSON inputs are removed afterward.

**If you see something else:** Retain the failure output before cleaning up. A failure can indicate missing context propagation or an unsupported clean conclusion.

**Result:** Passed by the agent during finish. Expected the shared coordinator scenarios to pass and temporary inputs to be removed; actual 6 tests passed, with cleanup confirmed.

Actual output:

```text
......
----------------------------------------------------------------------
Ran 6 tests in 5.697s

OK
```

## Not covered here

- A fresh plugin agent's code-backed interpretation of author prose, contradictions and accepted explanations needs a real PR with earlier personal feedback. These local semantic fixtures cannot prove that interpretation.
- Live bulk worker dispatch, thread replies, publication freshness and hosting approval require a separately approved session. This draft neither creates PR fixtures nor posts comments.

## Coverage

- US1: manual history and source identity, separate from code coverage.
- US2: outstanding material concerns and a legitimate clean stopping point.
- US3: executable shared coordinator blocks, full/incremental scope and stale/incomplete evidence. Live single/bulk agent behavior and publication remain outside this local journey.

## Results

5 of 5 steps passed, 0 failed, 0 skipped. Real helper/coordinator commands ran against explicitly synthetic semantic fixtures. No hosted PR was inspected or mutated, and the live-agent limits above still apply.
