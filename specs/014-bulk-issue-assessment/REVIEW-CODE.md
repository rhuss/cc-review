# Code Review: Bulk Issue Assessment with Optional Draft-PR Fixes

**Spec:** specs/014-bulk-issue-assessment/spec.md
**Date:** 2026-11-23
**Reviewer:** Claude (speckit.spex-gates.review-code)
**Branch:** 015-bulk-issue-assessment

## Compliance Summary

**Overall Score: 98%** (52/53 checks) before the deep review; **100%** (53/53) after the fix loop (the FR-007 deviation was fixed).

- Functional Requirements: 37/38 (97%)
- Edge Cases: 15/15 (100%)
- Success Criteria: 8/8 supported by code and tests (SC-001/SC-002 depend on the prompt and are instructed)
- Spec-Declared Constants: n/a (no `## Constants` section in the spec)

The feature is a deterministic helper (`review/core/scripts/issue_bulk.py`, about 1540 lines), a kind-agnostic run-state module (`review/core/scripts/run_state.py`), small refactors of `assess_issue.py` (collect_issue) and `assessment.py` (run marker), an orchestrator prompt (`review/core/commands/issue-bulk.md`), a fix-worker template, and shim updates. Prompt-only requirements (assessment judgment, conversation, subagent dispatch) are assessed as "does the prompt instruct the required behavior"; helper requirements are assessed against control flow and the 98 tests of `tests/test_issue_bulk.py` (all passing before review).

## Detailed Review

### Functional Requirements

#### Invocation

- **FR-001** `issue --bulk` with `--search`, `--limit` (default 10), `--scan` (default 100), `--repo`, `--resume [<id>]`: `issue_bulk.py validate()` / `parse_raw()`, shims forward the flags. **Compliant.**
- **FR-002** Validation table: `validate()` covers every row (targets with bulk/resume, `--unattended`, bulk-only flags without `--bulk`, resume with search/limit/scan/repo, `--resume` alone implies bulk, ranges, forbidden qualifiers incl. negated forms via `FORBIDDEN_QUALIFIERS`). The "no matching unfinished run" error is produced by `run_state.py find-unfinished` with the required wording. `issue.md` dispatches to bulk before the unattended dispatch. **Compliant.**
- **FR-003** Single-issue path unchanged; `assess_issue.collect()` now delegates to `collect_issue()` with identical behavior. **Compliant.**

#### Selection

- **FR-004** `search_string()` forces `repo:<R> is:issue is:open sort:created-desc`; `select()` additionally filters nodes to open Issues of the repository by URL. **Compliant.**
- **FR-005** Marker check in `classify()`. **Compliant.** (After the spec amendment, only markers by maintainers or bots count; implemented and tested, see A3.)
- **FR-006** Maintainer association, not the issue author, bots excluded. **Compliant.**
- **FR-007** Maintainer-owned open or merged PR on this repository (author, reviewer or commenter; bots excluded). **Deviation (minor):** `classify()` pops a PR from `linked` on any `DisconnectedEvent`, even when the same PR also cross-references the issue (closing keyword or mention). Removing a manual sidebar link then hides a maintainer PR that still references the issue, and the issue is selected instead of skipped as "maintainer PR #M". Recommendation: fix code (track cross-references separately from connected/disconnected links). **Fixed in the deep review** (links are tracked per source; regression test `test_disconnect_keeps_a_cross_reference`).
- **FR-008** Non-maintainer or closed-unmerged PRs stay eligible and are recorded with state. **Compliant.**
- **FR-009** Maintainer-opened issues go through the same rules. **Compliant.**
- **FR-010** Paging continues until limit, exhaustion or ceiling; `scanned`, `ceiling_reached`, `exhausted` recorded. **Compliant.**
- **FR-011** Every skip recorded with reason; selection is pure given the API data (fixture tests). **Compliant.**
- **FR-011b** Truncated comments, timeline, or linked PR reviews/comments give "history too long to verify". **Compliant.**
- **FR-011a** `graphql()` raises on transport errors and partial responses; `select` writes nothing on failure; `start` refuses an empty selection. **Compliant.**

#### Assessment

- **FR-012** Fresh worker per issue (prompt step 7); `collect` failure and `fail` record "assessment failed". **Compliant.**
- **FR-013** `check_estimate()` requires the estimate on every assessment; `fix_eligibility()` applies Pursue + confirmed + bound (3 files, 100 lines, 300 test lines); `is_test_path()` matches the spec's test-file definition. **Compliant.**
- **FR-014** `render-item` rejects an assessment that does not name each open non-maintainer linked PR's URL; the prompt also requires closed/merged ones to be mentioned. **Compliant** (helper enforcement covers open PRs; closed ones are prompt-instructed).
- **FR-015** Untrusted-data rules in `issue-bulk.md` and `issue-fix-worker.md`. **Compliant.**

#### Approval and posting

- **FR-016** Approval after the assessment pass, in selection order (`next decide`); edit re-renders and recomputes label and eligibility (`render-item` clears the decision). **Compliant.**
- **FR-016a** Prompt posts right after each approval; `post` records the result. **Compliant.**
- **FR-017** Fix or leave for eligible issues; "review linked PRs" replaces fix when open non-maintainer PRs exist; `decide` enforces both. **Compliant.**
- **FR-018** Only the rendered comment (REST POST) and the mapped label (add-labels endpoint); project `ci.yml` mapping when present. **Compliant.**
- **FR-019** `recheck()`/`recheck_verdict()` before posting; withheld with reason. **Compliant.**
- **FR-020** Missing label detected by GET 404, never created, reported. **Compliant.**
- **FR-020a** Failed comment/label recorded, run continues; run marker authored by the user counts as posted on resume; label retried. **Compliant.**

#### Fixes

- **FR-021** `start` sets `fixes_available` only with a verified matching checkout and WRITE/MAINTAIN/ADMIN permission; reason stated once. **Compliant.**
- **FR-022** Fresh worktree from `origin/<default>` after fetch, inside the run directory. **Compliant.**
- **FR-022a** Fix worker template: file tools only, no commands, no network. **Compliant** (prompt-level; see deep review for containment hardening).
- **FR-023** Worker give-up recorded; `fix-measure` enforces the bound and abandons without commit. **Compliant.**
- **FR-024** Empty `core.hooksPath` plus `--no-verify`; PR body carries the tests note. **Compliant** (see deep review for containment hardening).
- **FR-025** One commit, conventional type from kind, push of a new branch, draft PR with summary, `Fixes #N`, note; existing unrecorded branches refused. **Compliant.**
- **FR-025a** Steps recorded separately; pushed-without-PR only opens the PR after `open_pr_for()`. **Compliant.**
- **FR-026** `fix-cleanup` removes worktree and local branch. **Compliant.**

#### Handoff, report and state

- **FR-027** `record-handoff` plus prompt step 11/12. **Compliant.**
- **FR-028** `item_outcome()` covers every listed outcome; coverage section from the selection. **Compliant.**
- **FR-029** Durable atomic state; resume reuses assessments, keeps decisions, never reposts, never reruns a fix with a PR; start-fresh abandons. **Compliant.**
- **FR-030** Helpers own validation, selection, state, loop control, posting, re-checks, branches, PRs and counts. **Compliant** (the handoff list is computed with `jq` in the prompt but validated by `record-handoff`; noted as a minor quality item).
- **FR-031** `run_state.py` is kind-agnostic. **Compliant.**
- **FR-032** Subagents per assessment and fix, inline fallback with warning. **Compliant.**

### Edge Cases

All 15 edge cases have a handling path: no match ("No issues matched" with the query, no run), all skipped (no "verified empty" claim when the ceiling was reached), re-check before posting (maintainer reply, new assessment, closed), missing label, no checkout or no push access, default branch moved (fetch at fix time), branch conflict, push-without-PR resume, selection failure, per-issue collection failure, untrusted instructions, fork PRs (counted via `baseRepository`), incomplete collection (`conversation_complete`/`warnings` passed to the worker), post failures, no-subagent fallback. **15/15.**

### Extra Features (Not in Spec)

- **Withheld reply abandons an unpushed fix** (`cmd_post`, the `withheld` branch). When the re-check withholds the reply, a chosen fix that has not been pushed is abandoned. The spec says fix and post are independent decisions. Assessment: defensible (the issue no longer qualifies), but it is undocumented in the spec. Recommendation: add to the spec via evolve, or drop. **Now specified in FR-019 (decision A4).**
- **Checkout-containment snapshot** (`checkout_snapshot`, `fix-measure`). Detects HEAD, index, status, branch and run-state changes by the fix worker. Helpful hardening of FR-022/FR-022a; recommend recording it in the spec.

### Spec-Declared Constants

Not applicable: the spec has no `## Constants` section.

## Code Quality Notes

See the Deep Review Report below.

## Conclusion

Spec compliance is 98% (one minor deviation in FR-007 timeline handling), above the 95% threshold for deep review. Proceeding to deep review. The deep review fixed the FR-007 deviation; post-fix compliance is 100%.

---

# Deep Review Report

**Date:** 2026-11-23
**Branch:** 015-bulk-issue-assessment
**Rounds:** 3 (initial review, then two re-review rounds on the fix diff)
**Gate Outcome:** PASS
**Invocation:** quality-gate (ship pipeline)

## Summary

| Severity | Found | Fixed | Remaining |
|----------|-------|-------|-----------|
| Critical | 4 | 4 | 0 |
| Important | 37 | 36 (31 in the fix loop, 5 after maintainer decisions) | 0; 1 dismissed |
| Minor | 35 | 35 (17 in the fix loop, 18 after maintainer decisions) | 0 |
| Notable | 6 | - | 6 (captured) |
| **Total** | **82** | **75** | **0** (6 Notable captured) |

Counts are after deduplication across agents and external tools. The five Important design questions and the four ambiguous Minor items were decided by the maintainer and resolved afterwards, together with all sixteen unambiguous Minor items (see Remaining Findings: Resolved).

**Internal agents completed:** 5/6 (Correctness, Architecture & Idioms, Security, Production Readiness, Test Quality; Goal Alignment skipped: no PR for the branch), plus one combined correctness/security re-review of the round-1 fix diff.
**External tools:** CodeRabbit completed (3 runs: 18, 12 and 12 findings, the later runs on the fix diff), Codex completed (3 runs: 5, 2 and 4 findings), Copilot skipped (disabled in config).
**Test suite:** `python3 -B tests/test_issue_bulk.py` 131 tests green (98 before review); final `make test` green (1932 passed, 0 failed).

## Findings (Critical: all fixed)

### FINDING-1: fix worker could get code executed through a redirected worktree gitdir
- **Severity:** Critical **Confidence:** 95 **Category:** security
- **File:** review/core/scripts/issue_bulk.py (git calls in fix-measure/fix-publish)
- **Source:** security agent (verified by execution); also Codex (filters), CodeRabbit (unverified)
- **Resolution:** fixed (round 1, hardened round 2)

**What was wrong:** every helper git call in the fix worktree let git discover the repository through the worktree's `.git` gitfile, which the worker is allowed to edit. Rewriting it to `gitdir: .evil` with a planted config made `git add -A`, `diff`, `write-tree`, `commit` and `push` run `core.fsmonitor`, `gpg.program` and `remote.origin.receivepack`.

**Why it mattered:** untrusted issue text steering a fix worker became arbitrary shell execution on the maintainer's machine (FR-022a, FR-024).

**How it was resolved:** worktree git calls pass `--git-dir`/`--work-tree` explicitly (verified against the recorded common directory); every helper git call passes `core.fsmonitor=false` and `core.hooksPath=/dev/null`; `git_metadata()` digests the worktree's `.git` file, its git directory, the common configuration, attributes and excludes, and the global config, compared without running git before any git call in fix-measure and on resume. A mismatch taints the fix and no git command runs for it.

### FINDING-2: containment snapshot blind to `.git/config` and itself ran fsmonitor; taint only per item
- **Severity:** Critical **Confidence:** 85 **Category:** security
- **File:** review/core/scripts/issue_bulk.py (`checkout_snapshot`, fix steps, `abandon-run`)
- **Source:** security agent; re-review agent (run-wide taint gap, round 2); CodeRabbit round 2 (abandon-run before measure)
- **Resolution:** fixed (rounds 1 to 3)

**What was wrong:** the snapshot hashed HEAD, index, status and branches only; a worker writing `core.fsmonitor`, `remote.origin.uploadpack` or similar into `<checkout>/.git/config` was not detected, the snapshot's own `git status` executed it, and after the round-1 fix a taint on one item still let the next fix's `git fetch` run the planted config.

**How it was resolved:** a run-level git baseline (checkout `.git` entry, its git directory when it is a linked worktree, common config/attributes/excludes, global config) is recorded at the first fix-prepare and checked without git at the start of every fix step, cleanup and `abandon-run`. Any change sets `extra.git_tainted`: all later fix steps refuse git, `next fix` returns nothing, cleanup and abandon-run leave manual-cleanup instructions, and the report says "Fixes stopped". A regression test plants `remote.origin.uploadpack` (not blocked by the git `-c` overrides) and proves the second fix runs no git.

### FINDING-3: worker-writable run state drove `git branch -D`, `worktree remove --force` and the push refspec
- **Severity:** Critical **Confidence:** 90 **Category:** security
- **File:** review/core/scripts/issue_bulk.py (fix-cleanup, fix-publish, checkout_snapshot)
- **Source:** security agent (verified: deleted local `main` with an unpushed commit)
- **Resolution:** fixed (round 1)

**How it was resolved:** branch, worktree path and PR title are derived from the issue number (`fix_branch`, `fix_worktree`, `commit_subject`), never read back from state; the item's `fix` record is part of the state digest compared at measure; the push sends the recorded commit (`<commit>:refs/heads/<branch>`), not the branch tip.

### FINDING-4: helper `git status` ran the checkout's `post-index-change` hook
- **Severity:** Critical (reported Important by the test agent; it is project code running locally, FR-024) **Confidence:** 95 **Category:** security / test-quality
- **File:** review/core/scripts/issue_bulk.py (`checkout_snapshot`), tests/test_issue_bulk.py (`FixTestCase`)
- **Resolution:** fixed (round 1): all helper git calls disable hooks; the test hook list now includes `post-index-change`, `reference-transaction`, `post-rewrite`, `post-merge`, and the tests' own git calls run without hooks so the hook log shows only helper calls.

## Findings (Important: fixed)

- **FINDING-5** Sanitizer bypass: an unbalanced or backslash-escaped backtick hid closing keywords and `@mentions` from `sanitize_summary`/`commit_subject` (security, re-review). Fixed: the summary and the commit subject are neutralized as a whole, with no code-span exception.
- **FINDING-6** A retried post was withheld because the run's own fix PR counted as a maintainer PR (correctness). Fixed: `recheck_verdict` ignores a PR on `cc-review/fix-issue-<n>` by the run user only when this run recorded a push or PR for the item (narrowed in round 3 after CodeRabbit).
- **FINDING-7** Resume re-dispatched a fix worker after the worker had finished, measured or pushed (correctness, CodeRabbit, Codex). Fixed: `fix-prepare` returns `worker_needed`; the prompt skips the worker when false.
- **FINDING-8** A raising fix step (fetch timeout, staging failure, push timeout) left the fix open, so `next fix` looped or the run closed with "fix not run yet" (correctness, architecture, production). Fixed: `fail_step()` records abandonment (or a pending PR); the attempt is recorded at prepare; the prompt says how to continue after `Error:`.
- **FINDING-9** `report` marked runs finished with open fixes, uncleaned worktrees, or undecided issues (correctness, production, CodeRabbit). Fixed: those keep the run `running` and are listed under "Still pending".
- **FINDING-10** Crash window: the branch and worktree existed before ownership was recorded, so resume called it a foreign conflict and leaked it (production, correctness, Codex). Fixed: `creating` is recorded before `worktree add`; only an existing worktree is adopted on resume; a failed `worktree add` drops the claim so a foreign branch is never deleted.
- **FINDING-11** A pending PR kept its worktree and local branch indefinitely (production). Fixed: cleanup removes both once pushed; resume opens the PR from the remote branch.
- **FINDING-12** "Start fresh" left the abandoned run's worktrees and local fix branches behind (production, correctness). Fixed: new `issue_bulk.py abandon-run` cleans them (or lists them for manual cleanup) before abandoning.
- **FINDING-13** Two sessions on one run could both post the same comment (production). Fixed: an exclusive `flock` per run around every helper call; lock errors surface as `Error:`.
- **FINDING-14** The handoff list was computed with `jq` in the prompt (FR-030) (architecture). Fixed: `record-handoff RUN` computes it; `jq` is no longer needed.
- **FINDING-15** `run_state` accepted `ssh://` origins while `assess_issue.local_context` did not, so state location and fix availability disagreed (architecture). Fixed: one origin rule.
- **FINDING-16** Containment missed a second edit to an already dirty maintainer file (CodeRabbit). Fixed: the status digest includes the content of every listed path.
- **FINDING-17** Search text with an apostrophe broke the prompt's single-quoting (Codex). Fixed: the prompt requires `'\''` escaping.
- **FINDING-18** A worker's stored `assessment.json` was re-assessed after an interruption (Codex). Fixed: `next assess` reports `stored`; the prompt renders it first.
- **FINDING-19** A commit made just before an interruption was retried and abandoned (Codex, correctness, CodeRabbit). Fixed: adopted only when it is the helper's own commit (single parent = base, measured tree, helper message); a worker commit or moved branch ref is abandoned at measure (re-review).
- **FINDING-20** A push that timed out after reaching origin abandoned the fix (CodeRabbit round 2). Fixed: the remote branch is compared with the recorded commit before giving up.
- **FINDING-21** The 1000-result search cap was reported as an exhausted queue, on both the last-page and the scan-limit path (production, Codex, CodeRabbit). Fixed.
- **FINDING-22** The handoff and resume commands did not say which repository checkout they need (CodeRabbit). Fixed in output, report and prompt (see remaining FINDING-R3 for the underlying limit).
- **FINDING-28** Round-3 hardening (CodeRabbit, Codex on the fix diff): `abandon-run` after a partial cleanup no longer treats the removed worktree as tampering; a push whose outcome cannot be confirmed stays resumable (the recorded commit is pushed again); per-fix git metadata is re-checked before the commit; the checkout status digest no longer ignores submodules; a failed `worktree add -b` keeps ownership only of a branch it created; a tainted pending PR no longer keeps the run "running" forever.
- **FINDING-23..27** Test gaps (test agent): no failing re-check test; repeated publish did not assert a single `pr create`; no timeline-truncation or missing-connection test; no ceiling-on-page-boundary test; no partial GraphQL `errors` test; clean checkout fixture hid stash/checkout/reset regressions. All added; the fix fixture now runs on a feature branch with staged, unstaged and untracked changes and checks `git stash list`.

## Minor findings fixed

FR-007 `DisconnectedEvent` dropped a still cross-referencing PR (now tracked per link source); closed-unmerged PR truncation caused `history_too_long` (FR-008); GraphQL partial errors now carry their messages; `rendered.md` is read once (hashed bytes are the posted bytes); `ASSESSMENT_MARKER` reuses `assessment.HIDDEN_PREFIX`; `issue.md` unattended-dispatch wording now follows the bulk dispatch; `SKILL.md` argument hint per mode; fix-worker template forbids touching `.git` and describes detection accurately; git runs with `GIT_TERMINAL_PROMPT=0` and no stdin; fix branches are created with `--no-track` (no config writes); cleanup is scheduled for a recorded PR whose worktree was not removed; contracts table updated (escaped pipes, new outputs); helper reads never refresh the maintainer's index (`GIT_OPTIONAL_LOCKS=0`); the prompt's `next` stop condition reads `{"number": null}`.

Dismissed: CodeRabbit "keep runs discoverable after dropping `ssh://` origin support" (no released version stored runs under the old rule). Not part of this feature: `.specify/spex.json` (`security: yolo`), flagged by Codex P1, is a pre-existing uncommitted change in the worktree and was left uncommitted.

## Remaining Findings: Resolved (maintainer decisions, 2026-11-23)

The maintainer accepted all recommendations; the spec records the decisions (commit 628726e: FR-005, FR-014, FR-019, SC-006, Assumptions, Clarifications). Every remaining finding is resolved below. Regression tests are in `tests/test_issue_bulk.py`.

### Important (design decisions)

- **R1. Assessment workers could rewrite `state.json`.** **Resolved.** New `issue_bulk.py guard-begin RUN N` prints a canonical digest of `state.json` (without `updated_at`) and of every run file outside `items/<N>/` (locks and worktrees excluded). The orchestrator keeps the digest in its own context and calls `guard-end RUN N --digest D` after the worker and before `render-item`. Any difference records `extra.halted` and exits 1 naming the item; a halted run refuses all commands except `item`, `report` and `abandon-run`. Wired into `commands/issue-bulk.md` step 7 (also before a corrective re-dispatch). Tests: `ItemGuardLockTests.test_guard_*`.
- **R2. Run state inside the checkout.** **Resolved.** `run_state.root()` always returns `${XDG_STATE_HOME:-~/.local/state}/cc-review/<kind>-bulk/<owner>__<name>/`; the in-checkout root, origin matching and `.gitignore` writing are removed. Fixes still require the verified checkout (worktrees are added from it, under the run directory). `issue-bulk.md` warns once before the fix pass that fix workers have file-write access and the helpers only detect changes to the checkout, its git files and the run state. README, data model and contract updated. Tests: `test_root_is_per_user_even_inside_a_matching_checkout`, start test.
- **R3. Handoff and resume need a checkout of the repository.** **Resolved (no code change).** The repository stays named in the `record-handoff` output, the report and the resume hint; the spec Assumptions record `--repo` for `review --bulk` and `issue --resume` as a follow-up.
- **R4. Maintainer-configured git filters.** **Resolved (no code change).** The maintainer's configured filters are accepted (spec Assumptions); filters added by a worker remain detected through the git metadata digests. Verified that the current code refuses no legitimate configured filter: the baseline and per-fix digests only compare file contents.
- **R5. Two sessions on one run.** **Resolved.** `run_state.claim_session()` writes `<run>/lock` with the session id and timestamp; `issue_bulk.py main()` calls it for every command given `--session` (now accepted by `next`, `collect`, `render-item`, `item`, `guard-*`, `decide`, `post` and all fix steps, and passed by the prompt everywhere). Another session is refused with an actionable error naming the takeover time while the lock is younger than 30 minutes, and takes it over after that. Tests: `test_session_lock_refuses_then_allows_takeover` (module) and `test_second_session_is_refused_until_the_lock_expires` (CLI).

### Minor (unambiguous)

- **M1. Dead code.** **Resolved.** Removed `start --options`, `run_state.item()` and the `github` parameter of `assess_issue.collect_issue`.
- **M2. Duplicate atomic writes.** **Resolved.** One `run_state.atomic_write()` (temp file, fsync of the file, rename, fsync of the directory); `write_json` and `issue_bulk.write_text` use it.
- **M3. Whole state loaded per issue.** **Resolved.** New `issue_bulk.py item RUN N`; the approval pass uses it instead of `run_state.py show`. Test: `test_item_prints_one_items_decision_fields`.
- **M4. Phase `posted` without a comment.** **Resolved.** A skipped or withheld reply with an open fix now has phase `fix_pending`. Test: `test_withheld_post_with_open_fix_is_fix_pending_not_posted`.
- **M5. Duplicated run id pattern.** **Resolved.** `assessment.RUN_ID` is built from `run_state.run_id_pattern("issue")`.
- **M6. Durability and silent skips.** **Resolved.** fsync in `atomic_write`; `find_unfinished()` reports unreadable runs (`unreadable` in the CLI output and in the "no unfinished run" error). Test: `test_unreadable_runs_are_reported`.
- **M7. Abandon reason blamed the worker.** **Resolved.** Neutral wording "The checkout changed during the fix (status: <up to five paths>; branches; state ...). A change by you or by the fix worker stops the fix ..."; the snapshot keeps per-path status and content digests to name the paths. Tests: `test_outside_worktree_changes_abandon`, `test_dirty_file_edited_again_abandons`.
- **M8. Same-second run ordering.** **Resolved.** Numeric suffix ordering (`-issue-10` before `-issue-9`). Test: `test_same_second_runs_sort_by_numeric_suffix`.
- **M9. Push URL not checked.** **Resolved.** `fix-publish` refuses an `origin` push URL that differs from the verified fetch URL and does not name the run's repository. Test: `test_push_url_elsewhere_is_refused`.
- **M10. Handoff used stale PR state.** **Resolved.** `record-handoff` re-reads each PR (`repos/<repo>/pulls/<n>`) and leaves out closed or merged ones (`closed` in the output). Test: `test_pr_closed_since_selection_is_not_handed_off`.
- **M11. Push failure abandoned the fix.** **Resolved.** Any failed or unconfirmed push records `pending: "push"`; resume pushes the recorded commit again; the report shows "push pending" and keeps the run open. Tests: `test_rejected_push_stays_pending_and_is_retried`, `test_unconfirmed_push_stays_resumable`.
- **M12. Weak assertions and missing fixtures.** **Resolved.** Exact withhold reasons per case; per-row report outcomes and the full skip breakdown; the only write in the missing-label case is the comment; `--resume` with no id and no run; new `tests/fixtures/issue-bulk/classify-extra.json` with a stranger pasting the marker (eligible), a maintainer comment on a contributor PR (maintainer PR), a bot `MEMBER` PR author and reviewer (not a maintainer), and a merged contributor PR (eligible).
- **M13. Test environment isolation.** **Resolved.** Inherited `GIT_*` variables are removed; `HOME`, `XDG_CONFIG_HOME` and `GIT_CEILING_DIRECTORIES` point into the temporary directory, for helper subprocesses and the tests' own git calls.
- **M14. No re-check before a fix.** **Resolved.** A new fix re-reads the issue (this run's own reply and PR excluded) and is not started when the issue was closed, no longer qualifies, or a contributor PR now references it. Test: `test_issue_changed_since_assessment_stops_a_new_fix`.
- **M15. Unescaped pipes in data-model.md.** **Resolved.**
- **M16. Own-PR exclusion too broad.** **Resolved.** The re-check ignores only the recorded PR URL, or (before a PR is recorded) the fix branch whose head repository is the run's repository, by the run user. `headRepository` was added to the query. Test: `test_own_pr_is_ignored_only_by_recorded_url_or_own_head_repository`.

### Minor (ambiguous, decided)

- **A1. Binary files.** **Resolved.** Any binary file in the change abandons the fix ("Binary change: ..."); `test_bound_boundaries` aligned.
- **A2. Closed linked PR links.** **Resolved (no code change).** FR-014 now requires links only for open linked PRs, which `render-item` enforces.
- **A3. Pasted assessment markers.** **Resolved.** The marker counts only in comments by a maintainer (`OWNER`, `MEMBER`, `COLLABORATOR`) or a bot (FR-005), at selection and in both re-checks. Fixture #201 and the re-check tests cover it.
- **A4. Withheld reply abandons an unpushed fix.** **Resolved (no code change).** Now specified in FR-019.

## Notable Observations

Captured to `brainstorm/idea-inbox.md`:
- `bulk-issue-api-cost`: a full 1000-candidate scan can cost about 1000 GraphQL points before the first assessment (nested comments, timeline, reviews per page).
- `bulk-run-dir-pruning`: run directories and request files are never pruned.
- `run-state-vs-bulk-review-layout`: `run_state` uses a different directory and document layout than `bulk.md`/`bulk-state.sh`; the shared-runner refactor (#18) needs a migration or reader.
- `fix-worktrees-outside-checkout`: worktrees and run state inside the maintainer checkout make relative-path tampering easy (see R1, R2). Addressed afterwards by R2: run state and worktrees now live in the per-user state directory.
- `report-finishes-as-side-effect`: `report RUN` changes the run status, unlike `report --selection`.
- `prompt-only-guarantees`: SC-001, FR-015, FR-032 and the worker's "run nothing" rule are prompt-only and untestable without a model.

## Post-Fix Spec Coverage

The fix rounds removed and replaced code (fix section rewrite, dead code-span helpers). All 38 functional requirements were re-checked after round 3 and again after the decision changes, against the amended spec (FR-005, FR-014, FR-019, SC-006, Assumptions); all remain implemented; FR-007 is now fully compliant (the pre-review deviation was fixed). FR-022, FR-022a, FR-023, FR-024, FR-025, FR-025a, FR-026, FR-029 and FR-030 are strengthened. Spec coverage: 38/38.

## Test Suite Results

| Round | Command | Exit | Failures | Status |
|-------|---------|------|----------|--------|
| baseline | python3 -B tests/test_issue_bulk.py | 0 | 0 | 98 passed |
| 1 | make test | 0 | 0 | passed (1932 passed, 0 failed) |
| 2 | python3 -B tests/test_issue_bulk.py | 0 | 0 | 117 passed |
| 3 | python3 -B tests/test_issue_bulk.py | 0 | 0 | 119 passed |
| 3 (before last hardening) | make test | 0 | 0 | passed (1932 passed, 0 failed) |
| 3 (final) | make test | 0 | 0 | passed (1932 passed, 0 failed) |
| decisions | python3 -B tests/test_issue_bulk.py | 0 | 0 | 131 passed |
| decisions | make test | 0 | 0 | passed (1932 passed, 0 failed) |

## Gate Outcome

**PASS.** All Critical and Important findings are fixed, and every remaining finding is resolved after the maintainer's decisions (R1 to R5, M1 to M16, A1 to A4). Nothing is left open; the six Notable observations are captured in the idea inbox. As the spec Assumptions state, the helpers detect changes to the run state, the checkout and its git files, but a full sandbox for workers with file-write access is out of scope.
