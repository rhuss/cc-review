# Code Review: Bulk Review and Bulk Triage

**Spec:** specs/005-bulk-review-triage/spec.md
**Branch:** 005-bulk-review-triage (base: main)
**Date:** 2026-10-25
**Reviewer:** Claude (speckit-spex-gates-review-code, speckit-spex-deep-review-run)
**Invocation:** quality-gate (ship pipeline, autonomous)

## Compliance Summary

**Overall Score: 95.5% (64 of 67 items compliant, 3 minor deviations, 0 missing)**

| Group | Compliant | Total | Score |
|-------|-----------|-------|-------|
| Functional requirements (FR-001 to FR-036, FR-011a, FR-014a, FR-021a) | 39 | 39 | 100% |
| Edge cases | 18 | 21 | 85.7% |
| Success criteria (SC-001 to SC-007) | 7 | 7 | 100% |
| **Total** | **64** | **67** | **95.5%** |

Rechecked after ship fix cycle 1, which added FR-011a and three edge cases from the user's decisions and amended FR-006, FR-027, FR-028 and FR-030.

The score was taken on the tree before the fix loop and rechecked after it. The fix round turned one edge case (fork PR in bulk triage) from "nothing posted" into "only replies posted", which is closer to the spec but still detects the fork at apply time, not in the decision step, so it stays a minor deviation.

## Functional Requirements

| Req | Status | Implementation / notes |
|-----|--------|------------------------|
| FR-001 `--bulk` on review and triage | Compliant | review.md and triage.md "Bulk Mode" hand-off to core/commands/bulk.md; no new command |
| FR-002 bulk options and flag table | Compliant | bulk.md Inputs; `--spec`/`--output` rejected for review, `--no-fix` gates "apply fixes", `--idea-inbox` offered once (deferred), `--no-coverage-fix` accepted, `interactive: false` means unattended |
| FR-003 rejected combinations | Compliant | bulk.md Flag Validation; hand-offs reject `--bulk`/`--resume` with `--pr` (fix round 1 added `--resume --pr`) |
| FR-004 default selection incl. team requests and re-reviews | Compliant | bulk-select.sh `review-requested:@me` plus `reviewed-by:@me` with the user's marker review at an older commit |
| FR-005 `--all-open`, `--search` | Compliant | `gh pr list --state open [--search]`, scoped to the current repository |
| FR-006 reviewed-at-head exclusion | Compliant | `classify` `reviewed_at_head` (marker plus `commit.oid == headRefOid`, author not the PR author); excluded with reason; the re-review set ignores markers on the user's own PRs |
| FR-007 triage selection | Compliant | GraphQL search `author:@me`, unresolved thread count, `no-open-threads` exclusions; fix round 1 also filters on the author and follows thread pagination |
| FR-008 limit, oldest first, list the rest | Compliant | `sort_by(.updatedAt)`, `over-limit` exclusions |
| FR-009 user's tree untouched | Compliant | detached worktrees under `.cc-review/bulk/<run>/pr-<n>/wt`; `test_bulk_md_checkout_block` asserts a clean tree and unchanged branch. Shared triage state `.cc-review/.triage-state.json` is written as FR-014a requires (already git-ignored) |
| FR-010 bounded coordinator context | Compliant | worker protocol, status lines, counts via `jq`; fix round 1 makes reviewer prompts pass file paths instead of pasted bodies |
| FR-011 config once, PR reviewers ignored | Compliant | config from `PROJECT_DIR`, discovery with the PR's changed files |
| FR-011a command reviewers in fork checkouts | Compliant | review.md "Untrusted Checkout" (`apply_untrusted_checkout`), `UNTRUSTED_CHECKOUT` from the isolated checkout and from bulk.md; `allow_untrusted_checkout.<name>` validated in resolve-config.sh |
| FR-012 worktree keep and remove rules | Compliant | keep rules in Review/Triage Analysis and Apply; summary lists kept worktrees |
| FR-013 same pipeline, per-PR report path | Compliant | review.md Worker Mode (a) to (e); report path in decision table |
| FR-014 triage prepare, CI and coverage exceptions | Compliant | triage.md Prepare Mode table; 12b/12c/13 carry the exception; summary "CI not checked" |
| FR-014a invoking repository's triage state | Compliant | `TRIAGE_STATE_FILE` exported to the worker and to `bulk-apply.sh triage` |
| FR-015 one PR failing does not stop the run | Compliant | per-PR `failed` with reason; checkout failure tested |
| FR-016 sequential | Compliant | analysis loop one PR at a time |
| FR-017 no prompts during analysis | Compliant | bulk.md Analysis Loop |
| FR-018 one decision step, shortcuts, drill-down | Compliant | "Apply proposed actions", "Skip all", per-PR changes (asked in batches of up to 4 PRs per prompt, a harness limit), "Review findings" drill-down inside the step |
| FR-019 review actions, apply fixes for own PRs | Compliant | Allowed actions table; fixes run after the decision in the kept worktree, push after the head check; fix round 1 counts Critical/Important findings as fixable |
| FR-020 triage actions | Compliant | Apply/Skip plus Approve/Edit/Skip per human comment |
| FR-021 proposed actions | Compliant | `post`, `marker`, `apply`, `skip` |
| FR-021a no-findings marker | Compliant | `bulk-apply.sh marker`, COMMENT review with marker and `commit_id` |
| FR-022 unattended has no prompts | Compliant | Unattended Policy |
| FR-023 unattended review posts COMMENT only | Compliant | `REVIEW_EVENT_OVERRIDE=COMMENT`, never `fix` |
| FR-024 unattended triage | Compliant | bot part applied, human comments untouched, idea inbox skipped |
| FR-025 unattended decisions recorded | Compliant | policy block records `decision` per PR |
| FR-026 run id, state.md and state.json | Compliant | `bulk-state.sh init`, `render_md` after every update |
| FR-027 recorded fields | Compliant | PR entry fields, `failed_attempts`, `reanalyses` and `actions` (pushed sha, review id, replies, resolved) |
| FR-028 resume rules, never repeat | Compliant | `resume-plan`, recorded sub-actions skipped, marker and reply lookups before posting; a PR with 3 failed attempts is terminal |
| FR-029 resume options and modes | Compliant | Resume step 1; `--resume --unattended` starts a new run when none is unfinished |
| FR-030 head check before every post and push | Compliant | `bulk-apply.sh head` before every push, post and marker, `pending_push`; branch-tip check right before triage replies; a move before the decision triggers one re-analysis (`bulk-state.sh reanalyze`) |
| FR-031 one unfinished run per command | Compliant | Unfinished-Run Check (resume, abandon, cancel; unattended error) |
| FR-032 state kept, finished marked | Compliant | Summary sets `finished`; nothing deletes run directories |
| FR-033 ignore file | Compliant | `.cc-review/bulk/.gitignore` with `*` |
| FR-034 summary | Compliant | `bulk-state.sh summary` (selected, excluded, kept worktrees, needs attention, CI) |
| FR-035 single-PR isolated checkout | Compliant | review.md "Isolated PR Checkout" with `pr-worktree.sh is-pr-branch` |
| FR-036 behavior preserved, commit recorded | Compliant | single-PR path unchanged apart from `commit_id` (the accepted exception) and the isolated checkout of FR-035 |

## Edge Cases

| Edge case | Status | Evidence |
|-----------|--------|----------|
| No PRs selected | Compliant | "No PRs matched" with counts; no run directory |
| More PRs than the limit | Compliant | `over-limit` exclusions |
| Checkout fails | Compliant | `CHECKOUT failed`, PR `failed` (tested) |
| Reviewer or triage step fails for one PR | Compliant | PR `failed`, worktree kept |
| PR closed before decision | Compliant | Pre-Decision Refresh sets `closed` |
| PR head moves before decision | Compliant | Pre-Decision Refresh re-analyzes once, then `stale` |
| PR that keeps failing | Compliant | `failed_attempts`, terminal at 3 |
| PR from a fork (bulk review, isolated checkout) | Compliant | command reviewers `skipped (untrusted checkout)` unless opted in |
| Draft PRs | Compliant | excluded unless `draft:true`/`is:draft` |
| `--search` with scope qualifiers | Compliant | `check-query` (also `user:` and `state:`) |
| State or kept checkout missing on resume | Compliant | `resume-plan` `intact` check |
| User's own branch checked out locally | **Deviation (minor)** | `local-unpushed` handling is complete, but "your local branch is now behind" is told inline after the push, not in the written summary |
| PR from a fork (bulk triage) | **Deviation (minor)** | The decision table shows a `cross-repo` flag; "cannot push" is only known when the push is refused at apply time. Since fix round 1, the replies that do not depend on the fixes are then posted and the PR ends `cannot-push` |
| Not authenticated / not GitHub | Compliant | Platform and Authentication block |
| Unfinished run exists | Compliant | Unfinished-Run Check |
| Project reviewers changed by a PR | Compliant | discovery with changed files |
| Corrupt state on resume | Compliant | `validate`, never rewritten |
| `--bulk` with `--pr` | Compliant | rejected |
| `--resume` without `--bulk` | Compliant | treated as `--bulk --resume` |
| External reviewer rate-limited for one PR | **Deviation (minor)** | Only that reviewer fails (as in single-PR review); the PR is not marked failed. Arguably better; spec evolution candidate |
| Hosting-service rate limit | Compliant | exit 75, run `paused`, resume message |

## Success Criteria

| SC | Status | Evidence |
|----|--------|----------|
| SC-001 one invocation, one decision step | Compliant | decision step design |
| SC-002 tree unchanged | Compliant | worktree tests and `test_bulk_md_checkout_block` (success and failure) |
| SC-003 resume never repeats | Compliant | resume-plan and rerun tests, including edge branches added in fix round 1 |
| SC-004 one failure leaves others processed | Compliant | per-PR failure handling (checkout failure tested) |
| SC-005 10 PRs within context | Compliant (inspection) | worker protocol; reviewer prompts by path after fix round 1 |
| SC-006 same reviewer set and report | Compliant (inspection) | Worker Mode reuses Steps 1 to 7 |
| SC-007 unattended zero prompts | Compliant (inspection) | Unattended Policy |

## Extra Features (not in spec)

- `user:` and `state:` are also rejected in `--search`. Helpful; add to the edge case.
- Single-PR isolated checkouts live in `.cc-review/pr-worktrees/` with their own ignore file. Needed for FR-035.
- Selection warnings when a list query reaches its cap (fix round 1). Helpful.

## Spec Evolution Candidates

- Edge case "rate limiting by an external reviewer": describe "that reviewer fails, the PR continues".
- Edge case "PR from a fork": allow detection at push time ("cannot push" after a refused push, then only replies).
- Edge case "local branch behind": allow the notice at apply time instead of in the summary.
- (Resolved in ship fix cycle 1: FR-028 now caps retries at 3 failed attempts.)

---

# Deep Review Report

**Gate Outcome: PASS** (0 Critical and 0 Important open after fix round 4; the three Important design questions were decided by the user and implemented)
**Rounds:** 4 fix rounds (commits 8dab94f, e64262e, eb9b74d; round 4 = ship fix cycle 1: 4a3140a, 17a4235, 344e7fb, d496403)
**cc-review delegation:** not detected (no cc-review extension); the built-in review ran.

## Review Passes

| Pass | Tree reviewed | Reviewers |
|------|---------------|-----------|
| 1 (initial) | `main...3569d43` | correctness, architecture, security, production, test quality agents; CodeRabbit; Codex |
| 2 (after round 1) | 8dab94f | combined re-review agent (correctness, security, production, tests); CodeRabbit |
| 3 (after round 2) | e64262e | CodeRabbit |
| 4 (after round 3) | eb9b74d | CodeRabbit failed (rate limit); the one-line wording change was checked by hand |
| 5 (after round 4) | d496403 | focused re-read of every hunk of `81c60dd..d496403` against the spec; no new reviewer agents ran |

Goal Alignment was skipped: no PR exists for the branch. Copilot was skipped (CLI not installed).

## Summary

| Severity | Found | Fixed | Remaining |
|----------|-------|-------|-----------|
| Critical | 1 | 1 | 0 |
| Important | 20 | 20 | 0 |
| Minor | 27 | 26 | 1 (partly fixed) |
| Notable | 1 | - | 1 |
| **Total** | **49** | **47** | **2** |

Counts are after deduplication (correctness and architecture both reported the `review-findings` decision; Codex P2 items on pagination and stale `accepted.json` merged into the production and correctness findings).

## Agent Table

| Agent | Found | Fixed | Remaining | Status |
|-------|-------|-------|-----------|--------|
| Correctness | 8 | 8 | 0 | completed |
| Architecture and Idioms | 13 | 12 | 1 (Minor, partly fixed) | completed |
| Security | 5 | 5 | 0 | completed |
| Production Readiness | 9 | 9 | 0 + 1 Notable | completed |
| Test Quality | 9 | 9 | 0 | completed |
| Goal Alignment | 0 | 0 | 0 | skipped (no PR) |
| CodeRabbit (external) | 3 | 3 | 0 | completed (pass 4 rate-limited) |
| Copilot (external) | 0 | 0 | 0 | skipped (CLI not installed) |
| Codex (external) | 6 (1 P1, 5 P2) | 4 new after dedup | 0 | completed |
| Round 1 re-review | 2 | 2 | 0 | completed |
| Test Suite (regression) | 0 | 0 | 0 | passed every round |

MVP: Architecture and Idioms (13 findings).

## Findings Fixed

### Fix round 1 (8dab94f)

- **Critical, security**: a PR could add a symlink to a file outside its checkout (for example `../../../.env` from the fixed-depth worktree), and a reviewer would quote the user's secret in a posted finding. Step 1 now drops symlinks and paths that resolve outside `REVIEW_ROOT` from `CHANGED_FILES`, and reviewer prompts get a no-symlink rule.
- **Important, security**: the human-comment decision block took the reply text from a shell variable that the coordinator had to fill from an untrusted comment. Approve now copies the drafted reply inside jq from the plan; Edit reads a file written with the file-write tool (`--rawfile`). Tested with a `$(touch ...)` payload.
- **Important, correctness and architecture**: `["review-findings"]` was recorded as a decision that no apply part handles, so an interrupted drill-down left the PR "actioned" with nothing posted. Only the final `["post"]` or `["skip"]` is recorded; `resume-plan` treats a stray `["review-findings"]` as undecided.
- **Important, correctness (also Codex)**: a re-analysis reused the PR directory, so an old `accepted.json` or meta verdicts could be applied to a new head. The checkout block clears the directory (except the worktree) first.
- **Important, correctness**: "apply fixes" required a `fix` text that prompt reviewers never produce, so it was never offered for the user's own PRs. Critical and Important findings now count as fixable, as with the single-PR "Apply the important fixes".
- **Important, correctness**: on a refused push (fork) bulk triage posted nothing, while the spec says only reply posting remains. The replies that do not depend on the fixes are now posted and the PR ends `cannot-push`.
- **Important, correctness (Codex P1)**: the branch could move between the thread read and the replies. A branch-tip check now runs right before the replies.
- **Important, architecture**: the recorded `options` were built from `PER_PR_OPTIONS`, whose definition excluded `--no-fix`, `--config`, `--profile`, `--idea-inbox`. A separate `RECORDED_OPTIONS` array is now built explicitly.
- **Important, production**: worker-mode reviewer prompts pasted preamble, body and references into the coordinator's context for every PR. Workers now get file paths.
- **Important, production (also Codex)**: selection silently truncated at 200 PRs and 100 threads. The list cap is 1000 with a warning, the triage query reads `issueCount` and thread `hasNextPage`.
- **Important, test quality**: new tests for the DENIED push path (script and triage), cc-review thread replies and stale resolutions, re-posted bot comments and missing threads, the `remove` guard against deleting a repository, resume-plan edge branches (unknown head, terminal statuses, applying without worktree, deciding status), and the checkout block of bulk.md under bash and zsh (clean tree, failure, GraphQL rate-limit wording).
- Minor fixes: rate-limit pattern covers "API rate limit already exceeded"; resume sets `paused` on a rate limit; `--resume --pr` rejected; unattended error message fits a deferred run; `init` no longer loops forever on a read-only root; per-command selection file; triage keeps only the user's own PRs; shared triage state repaired for recorded replies (Codex); missing shell headers on two snippets; docs say the reviewed-at-head rule applies to review only (CodeRabbit); default state root exercised by a test.

### Fix round 2 (e64262e)

- **Important, correctness (re-review)**: the path-only reviewer prompts dropped the declared goals and the default hints file. Both are passed again as file paths.
- Minor: every worker that reads the checkout gets the symlink guard (CodeRabbit); test for the symlink filter under bash and zsh (re-review).

### Fix round 3 (eb9b74d)

- **Important, CodeRabbit**: the guard told workers not to read anything outside the review root, contradicting the instruction and run files they are given. It now limits code reads to the review root.

### Fix round 4 (ship fix cycle 1: 4a3140a, 17a4235, 344e7fb, d496403)

The three Important findings were design questions; the user decided them, and the spec records each decision in its Clarifications (Session 2026-10-25).

- **Important, architecture (4a3140a)**: a PR whose head moved between analysis and decision was dropped as `stale`. The Pre-Decision Refresh now re-analyzes it once in the same run (`bulk-state.sh reanalyze`, `reanalyses` in the state) and marks it `stale` only on a second move (FR-030 amended). Tests: `test_bulk_state_reanalyze_once_then_stale`, `test_bulk_md_pre_decision_refresh` (bash and zsh).
- **Important, production (4a3140a)**: a permanently failing PR kept a scheduled unattended job on one run. Every new `failed` status counts in `failed_attempts`; at 3 the PR is terminal, `resume-plan` keeps it, and the run can finish (FR-028 amended). Tests: `test_bulk_state_failed_attempts_cap`.
- **Important, security (17a4235)**: command reviewers ran inside a fork PR's checkout. They are now `skipped (untrusted checkout)` there, in bulk review and in the isolated `--pr` checkout, unless `allow_untrusted_checkout.<name>: true` (validated as a boolean in resolve-config.sh, documented in the config template and docs); prompt reviewers still run (new FR-011a). Tests: `test_config_validate_untrusted_checkout_types`, `test_apply_untrusted_checkout`, `test_review_md_untrusted_checkout`, isolated-checkout assertions.
- **Minor, security (17a4235)**: marker reviews by the PR's own author no longer count for "reviewed at head" or the re-review set (FR-006 amended), and `bulk-apply.sh marker` only accepts this run's marker posted by the user. Tests: `test_bulk_select_marker_authors` (also the missing "re-review author filter is decisive" fixture), marker lookup assertion.
- **Minor, architecture (4a3140a)**: one head check, `bulk-apply.sh head`, used by the pre-decision refresh and before every push, post and marker (`test_bulk_apply_head`).
- **Minor, architecture (344e7fb)**: `rate_limited` and `try` live in `rate-limit.sh`, sourced by the three scripts (bulk.md no longer greps the pattern); unused `ci_note`, `head_sha` and `updated_at` fields removed; distributed files no longer cite `R-003`, `R-009`, `data-model.md`, `contracts/*.md` or the spec's worker protocol; the validation table says where each check runs; bulk triage rejects `--spec` like bulk review; human drafts are a `draft` string; the duplicated worktree removal of analysis step 3 is gone.
- **Minor, production (344e7fb)**: abandoning a run removes its kept worktrees (`bulk-state.sh abandon`) and lists them in its `summary.md`; `summary.md` shows review links, pushed shas, reply and resolution counts.
- **Minor, test quality (344e7fb)**: `test_bulk_state_find_unfinished_lists_corrupt_run`, `test_bulk_state_abandon_removes_worktrees`.
- Verification pass (d496403): every changed hunk of the cycle re-read against the spec; one stale comment and one data-model description corrected.

## Remaining Findings

### Important

None.

### Minor

- Architecture (partly fixed): the terminal, reset, acted and apply-list predicates are shared jq definitions in bulk-state.sh (`terminal`, `to_apply`, `open-prs`, `finish`), but bulk.md still selects PRs by status inline in a few listing blocks (pending PRs of the analysis loop, the apply list, undecided PRs of the unattended policy). Each is a single-use, readable filter; moving them behind more subcommands is optional.

## Notable Observations

Captured to brainstorm/idea-inbox.md: worktrees and run state inside the working tree (nested checkouts seen by tools that ignore nested `.gitignore` files; no retention for old runs).

## Post-Fix Spec Coverage

Fix round 1 removed code only where it replaced it (the old human-comment block, the DENIED early return, the 200-PR list size). Every requirement those parts served is still implemented: FR-020 (human decisions, now via the plan or a file), FR-014/FR-020 and the fork edge case (DENIED now posts the independent replies), FR-005/FR-007/FR-008 (selection with a larger cap and pagination signals). All 38 functional requirements verified after the fix loop.

## Test Suite Results

| Round | Command | Result | Status |
|-------|---------|--------|--------|
| baseline | make test | 974 passed (116 tests) | passed |
| 1 | make test | 1044 passed (126 tests) | passed |
| 2 | make test | 1052 passed (127 tests) | passed |
| 3 | make test | 1052 passed (127 tests) | passed |
| 4 | make test | 1145 passed (137 tests) | passed |

## Layer Comparison

The pipeline state holds no checkpoint finding counts, so no layer comparison is shown.
