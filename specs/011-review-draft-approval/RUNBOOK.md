---
runbook_version: 1
feature: 011-review-draft-approval
status: drafted
mode: light
steps_total: 9
step_results: pending,pending,pending,pending,pending,pending,pending,pending,pending
drafted_at: 784a646
drafted_fingerprint: 2105450470adc6521149c982551ac9ac214d38a8961b580ee7e24c3506e2f56c
tested_at:
tested_fingerprint:
updated: 2026-11-06
---

# Try it: Review Draft Approval

<!-- runbook-status -->
> **Status:** drafted · 0 of 9 steps · Mode: light · Drafted at 784a646 · 2026-11-06
<!-- /runbook-status -->

## What you're testing

cc-review now drafts every PR review before it is posted. A script builds the comments from a fixed template, adds an attribution line that matches what the run actually did, checks the draft, and renders a preview. A second script posts only the exact draft that was approved, after checking the PR and its conversation again.

This journey runs the draft and posting scripts by hand on the bundled test fixtures, in the order a review goes through them:

1. Build a draft from a slots file and look at the comment structure.
2. Read the attribution line, then see how it changes when the run's facts change.
3. Render the preview and run the draft check on a clean draft.
4. Damage the draft the way a careless rewrite would, and watch the check catch it.
5. See the posting script refuse a draft that changed after approval, before it contacts GitHub.
6. See the conversation check pick out new comments by people, ignore bots, and skip ignored CI accounts.
7. Run the automated posting tests, which use a fake `gh` to cover the real POST path.

Every command runs from the root of the `011-review-draft-approval` worktree. Nothing is sent to GitHub.

## Test environment

No fixtures are needed. The steps use `python3`, `jq` and `bash`, and work on copies of `tests/fixtures/review-draft/` inside `specs/011-review-draft-approval/.walkthrough/play`, which is ignored by git.

## Steps

### Step 1 of 9: Prepare a play folder (US4)

**Why this step:** All later steps work on copies of the test fixtures, so the repository stays untouched.

**Needs:** a shell in the worktree root.

**Run:**

```bash
P=specs/011-review-draft-approval/.walkthrough/play
rm -rf "$P" && mkdir -p "$P/draft" && cp tests/fixtures/review-draft/slots-basic.json "$P/slots.json" && cp tests/fixtures/review-draft/facts-uncurated.json "$P/facts.json" && ls "$P"
```

**What you should see:** `draft`, `facts.json` and `slots.json`.

**If you see something else:** `No such file` means the shell is not in the worktree root.

**Result:**

### Step 2 of 9: Assemble a draft from the slots (US4)

**Why this step:** The slots file holds only the text of each part of a finding (what, why, fix, source). The script adds every label and heading itself, so a later prose rewrite cannot remove them.

**Needs:** Step 1.

**Run:**

```bash
P=specs/011-review-draft-approval/.walkthrough/play
python3 -B review/core/scripts/review_draft.py assemble --slots "$P/slots.json" --facts "$P/facts.json" --out "$P/draft" --inputs-key walkthrough | tee "$P/assemble.out"; ls "$P/draft"
```

**What you should see:** one line `FINGERPRINT` followed by a 64-character hex hash, then a listing that includes `payload.json` and `draft.json`.

**If you see something else:** an `Error:` line on stderr names the slot or fact that failed validation.

**Result:**

### Step 3 of 9: Check the structure of every inline comment (US4)

**Why this step:** This is the original complaint from the issue: the labels must survive. Each comment has to start with the severity label and keep `Why this matters`, `Suggested fix` and the source footer in that order.

**Needs:** Step 2.

**Run:**

```bash
P=specs/011-review-draft-approval/.walkthrough/play
jq -r '.comments[] | "== \(.path):\(.line)\n\(.body)\n"' "$P/draft/payload.json"
```

**What you should see:** two comments. `src/parser.go:42` starts with `**Important**:` and `src/server.go:88` starts with `**Critical**:`. Each continues with `**Why this matters**:`, then `**Suggested fix**:`, and ends with an italic `_Source: ..._` line.

**If you see something else:** a missing label or a different order is exactly the bug this feature fixes; note which comment.

**Result:**

### Step 4 of 9: Read the attribution line, then change the facts (US3)

**Why this step:** The summary says how the findings came about, based only on recorded facts. With no curation and no test run it must not claim either; with a curated run and a recorded test it says so.

**Needs:** Step 2.

**Run:**

```bash
P=specs/011-review-draft-approval/.walkthrough/play
jq -r '.body' "$P/draft/payload.json" | sed -n '/^### Review Details/,/^$/p' | sed -n '1,3p'
echo "--- curated run with a recorded test:"
python3 -B review/core/scripts/review_draft.py attribution --facts tests/fixtures/review-draft/facts-curated-tested.json
```

**What you should see:** the first line after `### Review Details` reads "These findings were produced by cc-review's reviewer agents and posted without a per-finding review." After the separator, the curated version starts with "I went through these findings one by one and selected the ones posted here" and adds "The run executed `go test ./...` in fix round 1: passed."

**If you see something else:** an empty first block means the Review Details heading or the attribution line is missing from the body.

**Result:**

### Step 5 of 9: Render the preview (US1)

**Why this step:** This is what you see before anything is posted: the review type in plain words, the full summary, every inline comment under its file and line, and the findings that stay in the summary.

**Needs:** Step 2.

**Run:**

```bash
P=specs/011-review-draft-approval/.walkthrough/play
python3 -B review/core/scripts/review_draft.py preview --draft "$P/draft" && rg -n '^#|Review type' "$P/draft/preview.md"
```

**What you should see:** the path of `preview.md`, then its headings: `# Review preview`, the line `- Review type: plain comment`, `## Summary body`, `## Inline comments` with two `###` entries for `src/parser.go` and `src/server.go`, and `## Findings in the summary only`.

**If you see something else:** a missing section means the preview leaves out part of what would be posted.

**Result:**

### Step 6 of 9: Check the clean draft (US5)

**Why this step:** The draft check runs before every preview and every unattended post. A draft built straight from the template must pass it.

**Needs:** Step 2.

**Run:**

```bash
P=specs/011-review-draft-approval/.walkthrough/play
python3 -B review/core/scripts/review_draft.py lint --draft "$P/draft" --facts "$P/facts.json" --expected-head 0123456789abcdef0123456789abcdef01234567 --run-marker 20261102-120000-review/pr-7; echo "exit=$?"
```

**What you should see:** `LINT ok` and `exit=0`.

**If you see something else:** `LINT findings=` with a number means a rule fires on the clean fixture; `cat "$P/draft/lint.json"` shows which one.

**Result:**

### Step 7 of 9: Damage the draft and let the check catch it (US5)

**Why this step:** A prose rewrite can slip in an em dash or an "I ran the tests" claim the run cannot back up. The check must name both.

**Needs:** Steps 2 and 6.

**Run:**

```bash
P=specs/011-review-draft-approval/.walkthrough/play
jq '.went_well[0] = "The parser is fast \u2014 really fast." | .went_well[1] = "I ran the tests by hand."' "$P/slots.json" > "$P/slots-bad.json"
python3 -B review/core/scripts/review_draft.py assemble --slots "$P/slots-bad.json" --facts "$P/facts.json" --out "$P/draft" --inputs-key walkthrough
python3 -B review/core/scripts/review_draft.py lint --draft "$P/draft" --facts "$P/facts.json" --expected-head 0123456789abcdef0123456789abcdef01234567 --run-marker 20261102-120000-review/pr-7; echo "exit=$?"
jq -r '.[] | "\(.rule): \(.message)"' "$P/draft/lint.json"
```

**What you should see:** a new `FINGERPRINT` line that differs from the one in Step 2, then `LINT findings=2` and `exit=1`, and two findings: one with rule `dash` and one with rule `claim`.

**If you see something else:** only one finding means one of the two rules missed its case; `LINT ok` means the check does not look at the What Went Well text.

**Result:**

### Step 8 of 9: The posting script refuses a changed draft (US1)

**Why this step:** Approval records the fingerprint of exactly what you saw. The draft has changed since Step 2, so posting with the Step 2 fingerprint must stop at the first check, before any call to GitHub.

**Needs:** Steps 2 and 7.

**Run:**

```bash
P=specs/011-review-draft-approval/.walkthrough/play
bash review/core/scripts/post-review.sh --draft "$P/draft" --owner acme --repo widget --pr 7 --user me --expected-head 0123456789abcdef0123456789abcdef01234567 --run-marker 20261102-120000-review/pr-7 --scope tests/fixtures/review-draft/scope --approved-fingerprint "$(awk '{print $2}' "$P/assemble.out")"; echo "exit=$?"
```

**What you should see:** exactly one line `REFUSED fingerprint`, then `exit=1`. No `gh` error appears, because the script stops before it reads the PR.

**If you see something else:** a `gh` error or `STALE head` means the fingerprint check did not run first.

**Result:**

### Step 9 of 9: The conversation check ignores bots and listed CI accounts (US1)

**Why this step:** Before posting, cc-review looks for new comments by other people since the analysis. Bot accounts never count, and logins in `pr_posting.ignore_authors` (for CI robots that are plain user accounts) count like bots.

**Needs:** Step 1.

**Run:**

```bash
P=specs/011-review-draft-approval/.walkthrough/play
rm -rf "$P/current" && cp -R tests/fixtures/review-draft/scope "$P/current"
jq '. + [{"id":"IC_new1","databaseId":301,"body":"Wait, I changed the parser again.","author":{"login":"bob","__typename":"User"},"createdAt":"2026-11-06T09:00:00Z","updatedAt":"2026-11-06T09:00:00Z"},{"id":"IC_new2","databaseId":302,"body":"/retest","author":{"login":"k8s-ci-robot","__typename":"User"},"createdAt":"2026-11-06T09:01:00Z","updatedAt":"2026-11-06T09:01:00Z"},{"id":"IC_new3","databaseId":303,"body":"Coverage report: 82%.","author":{"login":"codecov","__typename":"Bot"},"createdAt":"2026-11-06T09:02:00Z","updatedAt":"2026-11-06T09:02:00Z"}]' tests/fixtures/review-draft/scope/comments.json > "$P/current/comments.json"
echo "--- without an ignore list:"
python3 -B review/core/scripts/review_draft.py conversation-diff --analysis tests/fixtures/review-draft/scope --current "$P/current" --user me; echo "exit=$?"
echo "--- with k8s-ci-robot ignored:"
python3 -B review/core/scripts/review_draft.py conversation-diff --analysis tests/fixtures/review-draft/scope --current "$P/current" --user me --ignore-author k8s-ci-robot; echo "exit=$?"
```

**What you should see:** the first run prints a JSON list with two items, authored by `bob` and `k8s-ci-robot`, and `exit=1`. `codecov` is not listed. The second run lists only `bob`, again with `exit=1`.

**If you see something else:** `codecov` in the list means bots are not filtered; `k8s-ci-robot` in the second list means `--ignore-author` is not applied.

**Result:**

## Not covered here

- **The interactive preview and approve flow in Claude Code** (`/cc-review:review --pr <n>` and `--bulk`): it needs this branch's plugin loaded in a session and a test PR you own. Follow `quickstart.md` sections 2 to 4 for that; choosing **Skip** at the preview posts nothing.
- **A real POST to GitHub**: posting is covered by the automated tests below with a fake `gh`, not by hand, so this walkthrough never writes to a PR.

To run the automated posting tests (exact bytes posted, head and marker checks, check-only mode before thread actions, ignored authors): `bash tests/run.sh test_post_review`.

## Coverage

- **US1** (approve the exact text, single PR): Steps 5, 8 and 9 cover the preview, the fingerprint refusal and the conversation check. The interactive question itself is not covered (see above).
- **US2** (bulk approval pass): not covered by hand; it needs a bulk run against real PRs. The automated tests `test_bulk_command_three_pass_apply` and `test_bulk_resume_reasks_changed_draft` check it.
- **US3** (attribution): Step 4.
- **US4** (comment structure): Steps 2 and 3.
- **US5** (draft checks): Steps 6 and 7.
- **US6** (unattended and non-interactive): not covered by hand; `test_unattended_policy_withholds` runs the policy block under bash and zsh.

## Results
