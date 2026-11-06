# Review Draft Approval: Code Review

**Spec:** `specs/011-review-draft-approval/spec.md` (interfaces: `contracts/scripts.md`, `contracts/worker-protocol.md`, `data-model.md`)
**Date:** 2026-11-06
**Branch:** `011-review-draft-approval`, reviewed against the merge base `a02ff4d`
**Reviewer:** Claude (speckit-spex-gates-review-code with spex-deep-review, ship stage 7, oversight `smart`)

The review judged the code against the spec only. Plan and task files were not read.

## Compliance Summary

| | Before fixes | After fix rounds 1 and 2 | After the user's decisions |
|---|---|---|---|
| **Overall** | **96% (48/50)** | **98% (49/50)** | **100% (50/50)** |
| Functional requirements (34, incl. FR-003a, FR-010a, FR-014a, FR-019a, FR-020a) | 32/34 | 33/34 | 34/34 |
| Edge cases (9) | 9/9 | 9/9 | 9/9 |
| Success criteria (7) | 7/7 | 7/7 | 7/7 |

- Before fixes, two requirements were partial, and both were reproduced in the scratchpad.
  - **FR-009 / SC-003.** The lint stopped checking for test-result phrases as soon as any test run was recorded, failed runs included. "All tests pass" therefore passed the check next to a recorded failure.
  - **FR-013.** `draft.json` kept `lint_attempts` across a rebuild with new inputs, so a rebuilt draft never got its one redraft.
- Both are fixed in `b780eef`.
- The deep review found one more partial: **FR-001 on the "thread actions without a review" path** (7.5h). Thread replies and resolutions that went out without a review skipped the FR-021(c) conversation check and the fingerprint binding. The user chose the fix (D1 below), implemented in `3da3cec`.
- With the user's decisions, the spec was updated in FR-001, FR-020a, FR-021, FR-024 and three Clarification lines:
  - the conversation check counts only items created after the recorded analysis time;
  - `pr_posting.ignore_authors` lists logins treated like bots;
  - the history recheck applies the same rule as the conversation check;
  - a check-only run of `post-review.sh` precedes every thread action.
- The code matches the updated spec.

## Compliance Matrix

| Requirement | Implementation | Status |
|---|---|---|
| FR-001 draft without writes, thread actions after approval and checks | review.md 7.5 Draft/Approve/Post halves, 7.5f collects `thread-actions.json`, 7.5h thread-actions-only approval, 7.5l2 `post-review.sh --check-only` before each action; bulk.md Prepare pass and thread-action check | Compliant (after D1) |
| FR-002 preview content | `review_draft.py preview` | Compliant |
| FR-003 template labels by construction | `comment_body()`, 7.5i slot-only rewrite | Compliant |
| FR-003a edited description and fix kept apart | 7.5g `edited_description`/`edited_fix`, `user_text` | Compliant |
| FR-004 summary section order | `summary_body()`, lint `summary-order` | Compliant |
| FR-005 voice examples start with severity | `reviewer-voice.md` | Compliant |
| FR-006 truncation in drafting | `plan()` with `--max-comments` | Compliant |
| FR-007 one attribution line, first in Review Details | `summary_body()`, lint `attribution` | Compliant |
| FR-008 curation only from per-finding answers | 7.5g and bulk drill-down `facts-set --curated` | Compliant |
| FR-009 results only from recorded runs | `attribution()`, lint `result` (fixed: needs a passing latest round) | Compliant after fix |
| FR-010 repro scenarios statement | `repro_present` slot, `REPRO` sentence | Compliant |
| FR-010a facts recorded per PR at the time | Step 6 item 5, Worker (f), `facts-set` (fixed: one entry per round) | Compliant |
| FR-011 no unsupported first-person claims | lint `claim` (fixed: more claim variants caught) | Compliant |
| FR-012 automatic check rules | `lint()` | Compliant |
| FR-013 one redraft | 7.5k2 "Redraft once", `lint_attempts` (fixed: reset on new inputs) | Compliant after fix |
| FR-014 withhold after failed redraft (unattended, non-interactive) | bulk.md Unattended Policy, review.md 7.5k3 | Compliant |
| FR-014a no pinned commit means stale | lint `commit`, `STALE commit`, worker `stale-commit` | Compliant |
| FR-015 single-PR approve, edit or skip | 7.5k3 | Compliant |
| FR-016 edit scope | 7.5k3 item 3, bulk Edit block, `removed`, `attribution_override` | Compliant (enforced by instructions only, see Notable) |
| FR-017 approval fingerprint, refuse on mismatch | `fingerprint`, `post-review.sh` step 1 | Compliant |
| FR-018 three bulk passes | bulk.md Prepare, Approve and Post passes | Compliant |
| FR-019 answers recorded at once, no re-asking unchanged drafts | Approve pass record block | Compliant |
| FR-019a drafts persisted and reused | worker (g) reuse block, `inputs-key` | Compliant |
| FR-020 skip gives skipped or actioned | Approve pass Skip | Compliant |
| FR-020a analysis records time, conversation identities and author type | scope `analyzed-at.json`, `threads/comments/reviews.json`, `__typename` in platform.sh | Compliant |
| FR-021 head, marker and conversation checks before posting | `post-review.sh` steps 3 to 5; `conversation-diff` (created after analysis, ignored authors) and `history-diff` | Compliant |
| FR-022 moved head means stale | `STALE head` | Compliant |
| FR-023 existing marker recorded, not posted again | `FOUND` (fixed: user's own review, whole marker line) | Compliant |
| FR-024 conversation change withholds; interactive choice | 7.5l and Post pass `CHANGED` mapping | Compliant |
| FR-025 request matches the fingerprint | `post-review.sh` posts the fingerprinted copy | Compliant |
| FR-026 error recovery kept | `post-review.sh` step 6, 7.5m | Compliant |
| FR-027 unattended and non-interactive never prompt, COMMENT only unattended | `REVIEW_EVENT_OVERRIDE`, policy blocks (fixed: REFUSED never prompts; policy requires COMMENT) | Compliant |
| FR-028 triage posting unchanged | no change to triage paths | Compliant |
| FR-029 no-findings marker unchanged | `bulk-apply.sh marker` untouched | Compliant |

All nine edge cases and SC-001 to SC-007 map to the same code. The script-level parts have tests in `tests/test_review_draft.py` and `tests/run.sh` (`test_post_review_*`, `test_unattended_policy_withholds`, `test_bulk_state_withheld`). The spec has no `## Constants` section, so no constants check applied.

## Code Review Guide

Suggested reading order for a human reviewer:

1. **`review/core/scripts/review_draft.py`.** Everything deterministic lives here: slot assembly (`assemble`, `comment_body`, `summary_body`), attribution from facts, the FR-012 lint, the fingerprint, the inputs key and the conversation diff. Start with `lint()` and `attribution()`, which carry the attribution guarantees.
2. **`review/core/scripts/post-review.sh`.** The only path that writes a review. Check the step order in the header against the code. Everything before the POST is read-only, and the POST sends the private copy that was fingerprinted.
3. **`review/core/commands/review.md` Step 7.5.** The Draft, Approve and Post halves, the non-interactive policy block, the 7.5l result mapping and Worker Mode (g), which reuses drafts on resume.
4. **`review/core/commands/bulk.md`.** The Unattended Policy block, then Apply: the Prepare, Approve and Post passes and their state transitions (`withheld`, `stale`, `skipped`, `actioned`).
5. **`review/core/scripts/bulk-state.sh`** (`withheld` status, the "Needs attention" summary, `reset` clearing draft and approval) and **`platform.sh`** (`__typename` for bot detection).
6. **Tests.** `tests/test_review_draft.py` covers one lint rule class per test. `tests/run.sh` runs `post-review.sh` against the fake `gh` (`tests/fixtures/bulk/bin/gh`), which records each request body so it can be compared byte for byte with `payload.json`.

What deserves the closest look: the fingerprint binding between preview, approval and POST; the unattended policy, which is the only safeguard when nobody reads the draft; and the resume paths (draft reuse, approval reuse, a posted review whose thread actions are still pending).

## Deep Review Report

**Gate outcome:** PASS. 0 Critical and 0 Important remain.
- After fix rounds 1 and 2, the gate stood at FAIL with 4 Important findings: three design decisions (D1 to D3) and a partly closed test gap.
- The user decided all four, plus the Notable history-recheck question, and they are implemented in `3da3cec`.
- 13 Minor findings remain open; they are listed below and do not block the gate.

### Agents and tools

| Agent | Found | Fixed | Remaining | Status |
|---|---|---|---|---|
| Correctness | 6 (3 Important, 2 Minor, 1 Notable) | 6 (C6 by user decision) | 1 Minor (C5) | completed |
| Architecture & Idioms | 16 (2 Important, 14 Minor) | 9 | 7 Minor | completed |
| Security | 8 (4 Important, 4 Minor) | 6 (D1 by user decision) | 2 Minor | completed |
| Production Readiness | 8 (4 Important, 4 Minor) | 6 (D2, D3, P8 by user decision) | 2 Minor | completed |
| Test Quality | 10 (2 Important, 7 Minor, 1 Notable) | 5 (T-GAP by user decision) | 5 Minor, 1 Notable | completed |
| Goal Alignment | 0 | 0 | 0 | skipped (no PR for the branch) |
| CodeRabbit (external, local CLI) | 1 (Minor) | 1 | 0 | completed (first attempt failed auth, retried with API key) |
| Codex (external) | 1 (P2, same as CodeRabbit) | 1 | 0 | completed |
| Copilot (external) | 0 | 0 | 0 | skipped (disabled in config) |
| Re-review of fix round 1 (correctness + security) | 4 (Minor) | 4 | 0 | completed |
| Test suite (`make test`) | 0 regressions | | | passed after each round |

Counts are per agent before deduplication. Several agents reported the same defect: the result check was found by Correctness, Test Quality and this compliance pass; the redraft counter by Correctness, Test Quality, Architecture and the compliance pass; the stale preview after an interrupted draft by Security, Production and Architecture. **After merging: 0 Critical, 15 Important, 30 Minor (26 initial plus 4 from the re-review), 2 Notable.**

Final status after the user's decisions:

| Severity | Found | Resolved | Open |
|---|---|---|---|
| Critical | 0 | 0 | 0 |
| Important | 15 | 15 | 0 |
| Minor | 30 | 17 | 13 |
| Notable | 2 | 1 (history recheck) | 1 (locked edit fields) |

MVP: Architecture & Idioms (16 findings).

### Fixed (commit `b780eef`, fix round 1)

| # | Finding (sources) | Fix |
|---|---|---|
| I1 | A recorded **failed** test run turned the test-result check off, so "All tests pass" passed the lint (Correctness, Test Quality, compliance FR-009) | `_passed()`: a result phrase needs a passing latest round |
| I2 | `lint_attempts` and `max_comments` were carried into a draft rebuilt from new inputs, so there was no redraft (FR-013) (Correctness, Test Quality, Architecture, compliance) | `assemble` starts afresh when the inputs key changes |
| I3 | `facts-set --executed` appended a second entry for a round that ran again on resume, which changed the inputs key and could print two outcomes for one round (Correctness) | One entry per round (replace) |
| I4 | Claim regex missed "I’ve tested", "i verified", "I also ran" (Correctness) | Apostrophe normalization, either case of "I", one adverb |
| I5 | Without `--history`, a partial thread or comment read let the conversation check pass (CodeRabbit, Codex) | `CHANGED ... conversation incomplete` |
| I6 | `post-review.sh` posted any event (for example `APPROVE`) and did not require the marker; the preview showed `APPROVE` as "plain comment" (Security) | `REFUSED payload`; new `event` lint rule; preview names unsupported events |
| I7 | Preview and lint written by the drafting worker were trusted as-is, so an interrupted redraft could show an old preview while the approval fingerprinted the new payload, and `jq length` accepted `null` (Security, Production, Architecture) | `assemble` deletes the stale preview; the Approve pass, the worker's reuse step and the unattended policy re-run lint and preview themselves; array type check |
| I8 | `find_marker` accepted any author and a substring match, so a guessable bulk marker in someone else's review would be reported as this run's review (Security) | User's own review, whole marker line |
| I11 | A run interrupted after recording `review_id` never ran the approved thread actions and never finished the PR (Production) | Post pass resumes the seeding and thread-action step for such PRs |
| I13 | `FAILED` before the POST has no recovery file, but 7.5m copied it unconditionally (Architecture) | Documented; copy only when present |
| I14 | Single-PR 7.5l never passed `--just-pushed` after a Step 6 push, so the post went stale (Architecture) | `case "$PUSH_RESULT" in PUSHED*)` |

Minor fixes in the same commit:
- The history `CHANGED` reason now carries the fresh fingerprint, so an accept does not cover a later change (Security, Test Quality).
- `post-review.sh` POSTs the fingerprinted copy, which closes the TOCTOU window (Security).
- `REFUSED` never prompts in unattended or non-interactive mode (Production, Architecture).
- The doubled "review withheld:" prefix is gone (Test Quality, Architecture).
- The single-PR non-interactive policy reports a `commit` finding as stale (Architecture).
- 7.5l reads `APPROVED_FINGERPRINT` from `approval.json` (Architecture).
- Removed the contradictory "redraft and a new approval" sentence in 7.5l (Architecture).
- The worker sets `REVIEWED_HEAD="$EXPECTED_HEAD"` (Architecture).
- `conversation-diff` compares node ids only (Correctness).
- `contracts/scripts.md` arguments and results now match the scripts (Architecture).

### Fixed (commit `b170a41`, fix round 2, re-review findings)

- The result check now ignores negated statements ("did not pass", "fails to pass") that report a recorded failure.
- The bulk unattended policy marks a `commit` finding `stale` instead of `withheld` (FR-014a).
- The loose manual marker search was removed from 7.5m (it duplicated `post-review.sh` without the author check).
- The `facts-set` contract wording was corrected.
- `test_review_md_payload_has_commit_id` required the removed manual search. It now checks that 7.5m delegates the search to `post-review.sh` and that 7.5l passes `--run-marker`.
- New test `test_review_worker_reuses_unchanged_draft` runs the drafting worker's reuse block (FR-019a).

### Decisions by the user (implemented in `3da3cec`)

- **D1 (Important): bind thread actions deterministically** (Security S4, Architecture A16, FR-001).
  - Today 7.5l2 is performed by an LLM subagent that re-reads `thread-actions.json` after the post. No script rechecks the fingerprint of that file before replying.
  - On the 7.5h path, where the thread actions go out without a review, there is no fingerprint at all and no FR-021(c) conversation check.
  - **Decided: (a), resolved.**
    - `post-review.sh --check-only` runs the fingerprint, commit, head and conversation/history checks without posting and answers `OK`.
    - It runs immediately before every reply and resolution: review.md 7.5l2 (also on the 7.5h no-review path) and the bulk.md thread-action subagent.
    - Thread actions approved without a review record `approval.json` with a fingerprint of `thread-actions.json` alone.
    - Tests: `test_post_review_check_only` and `test_bulk_post_pass_block`.
    - Accepted residual: the reply text is still posted by the agent following 7.5l2, not by a script (option b was not chosen). The check catches any change to `thread-actions.json` since approval.
- **D2 (Important): data that was incomplete at analysis time produces a false `CHANGED`** (Production P1).
  - When an analysis-time fetch fails, `[]` is written for reviews, threads or comments, so every existing item looks new at post time. Unattended runs then withhold the PR indefinitely, with a misleading reason.
  - **Decided: count only items created after the analysis time, resolved.**
    - Analysis writes `$SCOPE_DIR/analyzed-at.json` before the first conversation read.
    - `conversation-diff` counts an item only when it was created after that time (with a 5 minute clock-skew margin). It also must be absent from the snapshot and written by someone other than the user, a bot or an ignored author. Edits do not count.
    - Without the analysis time, or for an item without a creation time, the identity comparison decides.
    - Tests: `ConversationDiffTest`.
- **D3 (Important): CI robot accounts that are GitHub users** (`k8s-ci-robot`, `openshift-ci-robot`) count as people, so on Prow repositories every fix-then-post PR returns `CHANGED` (Production P4).
  - **Decided: (a), resolved.**
    - `pr_posting.ignore_authors` (default `[]`) is in `review/config/config-template.yml` (documented there and in init.md and README).
    - It is read with the new `resolve_config_list`, passed as repeatable `--ignore-author` to `post-review.sh`, and forwarded to `conversation-diff` and `history-diff`.
    - Tests: `test_post_review_ignored_authors`, `test_bulk_post_pass_block` (the project config reaches the post) and `ConversationDiffTest`.
- **T-GAP (Important):** several bash blocks in the Markdown commands still run in no test (Test Quality T2).
  - Now covered:
    - the unattended policy block runs against real drafts;
    - `REFUSED payload`, the marker author and whole-line checks, and the history reason have tests;
    - the worker (g) draft-reuse block now runs under bash and zsh: an unchanged draft is reused with its fingerprint and a fresh preview, and a changed head or changed run facts are not reused.
  - **Closed (`3da3cec`):**
    - `test_bulk_post_pass_block` runs the bulk Post-pass block and the thread-check block as written, under bash and zsh: byte-for-byte post, `REFUSED fingerprint`, `--just-pushed` head retries, and `pr_posting.ignore_authors` from the project config.
    - `test_review_noninteractive_policy_block` runs the single-PR 7.5k3 policy block: approval by policy with the checked fingerprint, `STALE commit`, `WITHHELD` with findings, and a missing check.
- **History recheck (Notable, Correctness C6, spec interpretation).** The Follow-up Continuity history fingerprint changes on bot comments, comment edits and the run's own fix push. Because FR-021 says the history recheck "never relaxes" the conversation check, most fix-then-post follow-ups return `CHANGED`. Options:
  - **Decided: filtered history, resolved.**
    - The recheck rebuilds the history from the fresh data and compares only its items (`history-diff`) under the conversation-check rule. Edits, thread states, the head and the run's own review, replies and pushes do not count.
    - A history that cannot be rebuilt is reported as "history could not be rechecked: <error>", separate from a change.
    - Tests: `HistoryDiffTest`.

### Remaining Minor (not fixed, listed for follow-up; they do not block the gate)

- **Security**
  - Slot text can carry extra `cc-review` marker lines or raw HTML comments into the posted body (S7).
  - The `attribution_override`, `gate` and `completion` slots are free text in unattended mode (S8).
- **Production**
  - Transport errors without a 5xx code skip the marker recheck after a failed POST, and the rate-limit text after a POST says "nothing was posted" (P6).
  - Threads with more than 100 comments hide new replies (P7).
  - ~~A history recheck tool failure is reported as a change (P8).~~ Resolved in `3da3cec`: it is reported as "history could not be rechecked: <error>".
- **Test Quality**
  - Comment-structure variants and the en dash are not asserted one by one (T5).
  - Several `post-review.sh` branches are untested: closed PR, catch-up after a push, POST without an id, read failures (T7).
  - `reset` clearing draft and approval is untested (T8).
  - Only one voice example is checked (T9).
- **Architecture**
  - The inline comment format is duplicated in review.md, reviewer-voice.md and `comment_body()` (A8).
  - The doc says every round's test command is listed, but only the latest round is (A10).
  - The history input is built twice, in `post-review.sh` and review.md (A11).
  - Worker (g) points at a `specs/` path that is not shipped (A14).
  - The 7.5m `WORKER_MODE` recovery branch is dead (A7 remainder).
- **Correctness**
  - Dotted identifiers such as `React.Component` outside backticks trigger the missing-space rule (C5).

### Notable

- FR-016's edit restrictions (paths, lines, commit, marker) are enforced by instructions only. `assemble` could compare the locked fields per slot id against the previous payload (Test Quality T10).

### Post-fix spec coverage

The fix rounds only replaced or tightened code paths and removed no function, and every FR in the matrix above still maps to code. The 7.5m manual marker search was removed because `post-review.sh` performs that search, so FR-026 is still covered.

### Test suite results

| Round | Command | Result |
|---|---|---|
| Before review | `make test` | 186 tests pass (per pipeline state) |
| Fix round 1 | `make test` | 1546 passed, 0 failed (186 tests) |
| Fix round 2 | `make test` | first run: 1 failed (`test_review_md_payload_has_commit_id` asserted the removed manual search; assertion updated); rerun: 1559 passed, 0 failed (187 tests) |
| User decisions | `make test` | 1611 passed, 0 failed (191 tests) |
