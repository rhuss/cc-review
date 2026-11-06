# Deep Review Findings

**Date:** 2026-11-06
**Branch:** 011-review-draft-approval (base `a02ff4d`)
**Rounds:** 2, plus the user's decisions
**Gate Outcome:** PASS (after the user's decisions, implemented in `3da3cec`, no Critical or Important finding remains)
**Invocation:** quality-gate (ship stage 7)

## Summary

| Severity | Found | Fixed | Remaining |
|----------|-------|-------|-----------|
| Critical | 0 | 0 | 0 |
| Important | 15 | 15 | 0 |
| Minor | 30 | 17 | 13 |
| Notable | 2 | 1 | 1 |
| **Total** | **47** | **33** | **14** |

**Agents completed:** 5/6 (Goal Alignment skipped: no PR for the branch), plus CodeRabbit and Codex. Copilot is disabled in the config.
**Agents failed:** none. CodeRabbit's first attempt failed authentication and the retry with the API key succeeded.

The full per-finding descriptions, resolutions and open decision options are in `REVIEW-CODE.md`, section "Deep Review Report". This file lists them in the deep-review schema.

## Findings

### FINDING-1 (I1)
- **Severity:** Important
- **File:** review/core/scripts/review_draft.py (lint, result patterns)
- **Category:** correctness
- **Source:** correctness-agent (also reported by: test-quality-agent, spec compliance)
- **Round found:** 1
- **Resolution:** fixed (round 1, `b780eef`); round 2 (`b170a41`) added negation handling

**What is wrong:** A recorded failed test run disabled the test-result check, so "All tests pass" passed the lint.
**Why this matters:** The review states a false test result under the user's name (FR-009, SC-003), and in unattended mode the lint is the only safeguard.
**How it was resolved:** A result phrase now needs a passing latest fix round, and a negated phrase such as "did not pass" is not counted as a claim.

### FINDING-2 (I2)
- **Severity:** Important
- **File:** review/core/scripts/review_draft.py (cmd_assemble)
- **Category:** correctness
- **Source:** correctness-agent (also reported by: test-quality-agent, architecture-agent, spec compliance)
- **Resolution:** fixed (round 1)

**What is wrong:** `lint_attempts` and `max_comments` carried over into a draft rebuilt from new inputs.
**Why this matters:** A rebuilt draft lost its one redraft (FR-013).
**How it was resolved:** A different inputs key starts the draft metadata afresh.

### FINDING-3 (I3)
- **Severity:** Important
- **File:** review/core/scripts/review_draft.py (cmd_facts_set)
- **Category:** correctness
- **Source:** correctness-agent
- **Resolution:** fixed (round 1)

**What is wrong:** A fix round that ran again on resume was appended a second time.
**Why this matters:** The inputs key changed and the user was asked again about an approved draft. A flaky test also printed two outcomes for one round.
**How it was resolved:** Each round keeps one entry; a repeated round replaces the earlier one.

### FINDING-4 (I4)
- **Severity:** Important
- **File:** review/core/scripts/review_draft.py (CLAIM)
- **Category:** correctness
- **Source:** correctness-agent
- **Resolution:** fixed (round 1)

**What is wrong:** First-person claims with a typographic apostrophe, a lowercase "i" or an adverb ("I also ran") were not detected.
**Why this matters:** Unsupported claims could be posted unattended (FR-011).
**How it was resolved:** Apostrophes are normalized, the pronoun matches in either case, and one adverb is allowed between pronoun and verb.

### FINDING-5 (I5)
- **Severity:** Important
- **File:** review/core/scripts/post-review.sh (step 5)
- **Category:** external
- **Source:** codex (also reported by: coderabbit, as Minor)
- **Resolution:** fixed (round 1)

**What is wrong:** Without `--history`, a partial thread or comment read was compared as if it were complete.
**Why this matters:** New items could be missed, and the review posted anyway (FR-021).
**How it was resolved:** The script now answers `CHANGED ... conversation incomplete`.

**External tool analysis (Codex):**
> If fetching threads or issue comments fails after returning a valid partial array, and the caller omits the optional `--history` argument, the incomplete flags are never checked and `conversation_diff` can miss new items outside that partial data; the script then proceeds to post despite not verifying the full conversation.

### FINDING-6 (I6)
- **Severity:** Important
- **File:** review/core/scripts/post-review.sh, review_draft.py (preview)
- **Category:** security
- **Source:** security-agent
- **Resolution:** fixed (round 1)

**What is wrong:** Any `event` value, including `APPROVE`, and a payload without the marker were posted; the preview showed `APPROVE` as "plain comment".
**Why this matters:** A prompt-injected worker could approve a PR under the user's account (FR-027).
**How it was resolved:** `REFUSED payload`, an `event` lint rule, explicit preview labels, and an unattended policy that approves plain comments only.

### FINDING-7 (I7)
- **Severity:** Important
- **File:** review/core/commands/bulk.md, review.md, review_draft.py
- **Category:** security
- **Source:** security-agent (also reported by: production-agent, architecture-agent)
- **Resolution:** fixed (round 1)

**What is wrong:** The coordinator trusted the worker's `preview.md` and `lint.json`, and an interrupted redraft left a stale preview behind.
**Why this matters:** The user could approve text they never saw (FR-015, FR-017, SC-001).
**How it was resolved:** `assemble` drops a stale preview. The Approve pass, the reuse step and the unattended policy re-run lint and preview themselves, and `lint.json` must be an array.

### FINDING-8 (I8)
- **Severity:** Important
- **File:** review/core/scripts/post-review.sh (find_marker)
- **Category:** security
- **Source:** security-agent
- **Resolution:** fixed (round 1)

**What is wrong:** The marker search accepted any author and a substring match.
**Why this matters:** Another person's review carrying a guessable bulk marker would be reported as this run's review (FR-023).
**How it was resolved:** Only the user's own review, with the marker as a whole line, counts.

### FINDING-9 (I11)
- **Severity:** Important
- **File:** review/core/commands/bulk.md (Post pass)
- **Category:** production-readiness
- **Source:** production-agent
- **Resolution:** fixed (round 1)

**What is wrong:** A run interrupted after recording `review_id` never performed the approved thread actions.
**Why this matters:** The PR stayed `applying` and the run never finished.
**How it was resolved:** The Post pass resumes seeding and thread actions for such PRs.

### FINDING-10 (I13)
- **Severity:** Important
- **File:** review/core/scripts/post-review.sh, review.md 7.5l/7.5m, bulk.md
- **Category:** architecture
- **Source:** architecture-agent
- **Resolution:** fixed (round 1)

**What is wrong:** A `FAILED` result before the POST has no recovery file, but 7.5m copied one unconditionally.
**Why this matters:** The user was pointed at a recovery file that did not exist.
**How it was resolved:** The script header and contract document this, and the file is copied only when present.

### FINDING-11 (I14)
- **Severity:** Important
- **File:** review/core/commands/review.md 7.5l
- **Category:** architecture
- **Source:** architecture-agent
- **Resolution:** fixed (round 1)

**What is wrong:** Single-PR posting never passed `--just-pushed` after a Step 6 push.
**Why this matters:** The review was reported stale right after the fix push.
**How it was resolved:** `--just-pushed` is passed when `PUSH_RESULT` is `PUSHED`.

### FINDING-12 (D1, remaining)
- **Severity:** Important
- **File:** review/core/commands/review.md 7.5l2 and 7.5h
- **Category:** security
- **Source:** security-agent (also reported by: architecture-agent)
- **Resolution:** fixed by user decision (a), `3da3cec`: `post-review.sh --check-only` before every reply and resolution; thread-actions-only approval

**What is wrong:** Thread actions are performed by an LLM subagent, and no script rechecks the approval fingerprint. On the path where thread actions go out without a review, there is no fingerprint and no FR-021(c) check.
**What needs to happen:** Choose between a check-only mode of `post-review.sh`, a deterministic thread-action script, both, or keeping the instruction guard (see REVIEW-CODE.md D1).

### FINDING-13 (D2, remaining)
- **Severity:** Important
- **File:** review/core/scripts/post-review.sh, review.md Prior Review Context
- **Category:** production-readiness
- **Source:** production-agent
- **Resolution:** fixed by user decision, `3da3cec`: analysis records `analyzed-at.json`; only items created after it count

**What is wrong:** Data that was incomplete at analysis time (written as `[]`) makes every existing item look new at post time.
**What needs to happen:** Choose a distinct reason, timestamp filtering, keeping partial reviews, or a combination (see D2).

### FINDING-14 (D3, remaining)
- **Severity:** Important
- **File:** review/core/scripts/review_draft.py (conversation-diff)
- **Category:** production-readiness
- **Source:** production-agent
- **Resolution:** fixed by user decision (a), `3da3cec`: `pr_posting.ignore_authors`

**What is wrong:** CI robot accounts that are GitHub users count as people, so on Prow repositories reviews are withheld.
**What needs to happen:** Add an ignore-authors config, add a suffix heuristic, or keep the strict bot definition (see D3).

### FINDING-15 (T-GAP, partly closed)
- **Severity:** Important
- **File:** tests/run.sh
- **Category:** test-quality
- **Source:** test-quality-agent
- **Resolution:** fixed (rounds 1 and 2, and `3da3cec`)

**What is wrong:** The bash blocks in the Markdown commands for draft reuse, the Post-pass arguments and the single-PR policy block were not executed by any test.
**How it was resolved:** The unattended policy block runs against real drafts, and the worker reuse block runs under bash and zsh. `3da3cec` adds `test_bulk_post_pass_block` and `test_review_noninteractive_policy_block`, which run the remaining blocks as written.

## Minor findings

Fixed:
- History reason carries the fresh fingerprint.
- `post-review.sh` posts the fingerprinted copy (TOCTOU).
- `REFUSED` never prompts in unattended or non-interactive mode.
- The doubled withheld prefix is gone.
- A `commit` finding is reported as stale, in single-PR and bulk mode.
- `APPROVED_FINGERPRINT` is read from `approval.json`.
- The contradictory 7.5l sentence is removed.
- The worker sets `REVIEWED_HEAD`.
- `conversation-diff` compares by node id.
- The contract table is aligned with the scripts.
- The manual 7.5m marker search is removed.
- The `facts-set` contract wording is fixed.
- Negated result phrases are no longer flagged.

P8 (history tool failure reported as a change) was resolved with the filtered history recheck in `3da3cec`.

Remaining: S7, S8, P6, P7, T5, T7, T8, T9, A7 (remainder), A8, A10, A11, A14, C5. See REVIEW-CODE.md, "Remaining Minor".

## Notable Observations

### NOTABLE-1
- **File:** review/core/scripts/review_draft.py (assemble)
- **Category:** test-quality
- **Source:** test-quality-agent
- **Description:** FR-016's locked edit fields are enforced by instructions only.
- **Rationale:** `assemble` could compare them per slot id against the previous payload.

### NOTABLE-2
- **File:** review/core/scripts/post-review.sh (history recheck)
- **Category:** correctness
- **Source:** correctness-agent
- **Description:** The history fingerprint changes on bot comments, edits and the run's own push, so fix-then-post follow-ups return `CHANGED`.
- **Rationale:** This cancels out the FR-021(c) carve-out for bots and edits.
- **Resolution:** decided by the user (filtered history), implemented in `3da3cec` with `history-diff`; the spec was updated.

## Post-Fix Spec Coverage

All spec requirements were verified after the fix loop. No function was removed. The removed manual marker search duplicated `post-review.sh`.

## Test Suite Results

| Round | Test Command | Exit Code | Failures | Status |
|-------|-------------|-----------|----------|--------|
| 1 | make test | 0 | 0 | passed (186 tests) |
| 2 | make test | 2 | 1 | failed: `test_review_md_payload_has_commit_id` asserted the removed manual search; assertion updated |
| 2 (rerun) | make test | 0 | 0 | passed (1559 passed, 187 tests) |
| User decisions | make test | 0 | 0 | passed (1611 passed, 191 tests) |
