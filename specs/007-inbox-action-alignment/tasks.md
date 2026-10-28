# Tasks: Inbox PR Action Alignment

**Input**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [data-model.md](data-model.md), [contract](contracts/pr-actions.md).

**Tests**: Meaningful fixture-driven and regression verification is required by SC-001 through SC-006. Each deliverable includes its tests; write the new assertions first, demonstrate the relevant failure, implement, then run the configured `make test` checkpoint before marking the task complete. Do not leave deliberately failing tests between completed tasks.

## Phase 1: Setup

Reuse the existing core, Bash and Python test runner. Setup and fixture creation are folded into the independently testable deliverables below. No new dependency or project scaffold is needed.

## Phase 2: Foundation

- [X] T001 Implement exact reviewer activity fingerprints, a pure open/ownership/head/thread freshness check, scoped read-only/atomic cache operations and bounded marker parsing in `review/core/scripts/reviewer_activity.py`, with `tests/test_pr_actions.py` covering head/reply/edit freshness, malformed or wrong-identity state, safe identity paths, no directory creation on reads, preserved other-thread records, wrong-author markers and no-post outcomes. Wire `tests/test_pr_actions.py` into `tests/run.sh` in this task so every subsequent `make test` checkpoint executes it. Also test missing state as an empty read with no filesystem changes, quoted/malformed markers as non-recovery evidence, a failed write leaving the previous cache readable, and concurrent locked writers retaining both unrelated thread records. Interfaces: `fingerprint`, `load_activity`, `record_activity`, `activity_marker`, `parse_activity_marker` and `check_activity` from plan/contract; pending user decisions are not completed handling.
- [X] T002 Implement pure independent action assessment and deterministic selection in `review/core/scripts/pr_actions.py`, with `tests/test_pr_actions.py` covering requests, existing review-marker policy, author/reviewer ownership, both actions, draft differences, explicit modes, limits, incomplete evidence, uncertain head moves and reliable unchanged-contribution evidence. Assert that an outstanding explicit review request remains eligible with unchanged-contribution evidence; a moved head without a reply reactivates an owned unresolved finding, while unchanged handled activity does not; resolved, manual and wrong-owner threads cannot create reviewer eligibility. Incomplete triage evidence must preserve an independently established review action. Interfaces: `assess_pr`, `select_prs`, consuming T001 handled records.
- [X] T003 Implement canonical inbox/bulk normalization and safe internal JSON CLI entry points in `review/core/scripts/pr_actions.py` and `review/core/scripts/reviewer_activity.py`, with shared fixtures in `tests/fixtures/bulk/` and tests for equal-source assessment, malformed JSON and missing/null fields, root identity and truncated replies; invalid arguments/JSON must fail with actionable stderr and no result falsely claiming an empty queue. Interfaces: `normalize_pr` and T002 assessment; implement the exact assess/select and load/fingerprint/check/record CLI envelopes and exit behavior in `contracts/pr-actions.md#internal-cli-interfaces` for Bash consumers.

## Phase 3: User Story 1 — Aligned Inbox and Bulk Selection (P1)

**Goal**: PR action suggestions and bulk eligibility share evidence and rules.

**Independent test**: Equal canonical snapshots, filters and handled state produce equal action membership through both integration paths, including both-action and excluded cases.

- [X] T004 [US1] Attach shared PR assessments in `review/core/scripts/inbox.py` and update `review/core/commands/inbox.md` to consume them, preserving bounds, raw fingerprint evidence before display truncation, attention groups and issue/Discussion behavior. Extend `tests/test_inbox.py` for ownership/root aliases, both actions, partial evidence, explicit repository state identity and no cache/checkout writes. Retain fake-clock assertions that all detail calls share the 120-second deadline and that collection remains bounded at 100 discoveries per reason, 20 activity entries and 10 replies, with warnings when coverage is truncated. Snapshot the invoking checkout HEAD, index and worktree before/after; include hostile PR text and ensure it stays display data. Interfaces: T001 read-only state, T003 normalization and T002 assessment.
- [X] T005 [US1] Delegate bulk review/triage eligibility to the shared assessor in `review/core/scripts/bulk-select.sh`, retaining existing query guards, review discovery modes, ordering, seed compatibility, warnings and limit reasons while adding reviewed-PR reviewer discovery and triage on drafts. Extend `tests/fixtures/bulk/bin/gh`, fixtures and `tests/run.sh` for author/reviewer/both membership, caps, search narrowing and equal-snapshot inbox/bulk contract. Test missing Python/gh/jq, missing authentication, inaccessible repository and unavailable required evidence as clear nonzero failures; partial per-PR detail failure must retain usable independent results with named warnings rather than a verified empty queue. Assert stable ascending `(updatedAt, number)` ordering and default limit 10. Interfaces: T003 JSON selection CLI and canonical evidence; collect bounded ownership/provenance detail rather than infer from a PR-wide marker.

## Phase 4: User Story 2 — Reviewer Bulk Triage (P1)

**Goal**: Prepare and apply reviewer thread work alongside author triage without reviewer branch mutations.

**Independent test**: A mixed-role fixture run preserves author behavior, prepares reviewer outcomes without remote writes, and applies only fresh approved thread work with zero reviewer commits/pushes.

- [X] T006 [US2] Preserve `triage_role` and shared evidence through bulk seeds/state and render the role/reason in `review/core/scripts/bulk-state.sh` and `review/core/commands/bulk.md`; pass role to the worker. Extend `tests/run.sh` for mixed-role state round trips and legacy seed fallback restricted to author-owned PRs. Interfaces: T005 selected seed fields and existing bulk init/set-prs schema.
- [X] T007 [US2] Add reviewer-specific prepare and single-PR execution instructions to `review/core/commands/triage.md`, using T001/T003 ownership and freshness helpers, isolated checkout/current code, verified outcomes, drafted questions and no author bot-fix/CI path. Extend prompt-contract assertions in `tests/run.sh` for deferred no writes, no prepared commit, unanswered questions in unattended mode and consistent single/bulk role handling. Use an isolated fixture checkout and assert that reviewer preparation leaves the invoking checkout HEAD, index and worktree unchanged. Interfaces: exact top-level/entry reviewer plan keys, Activity and Outcome in `contracts/pr-actions.md#reviewer-plan-fields`; existing `.cc_review_threads[]` and `.human[]` approval flow.
- [X] T008 [US2] Enforce trusted reviewer role and reject prepared commits/author-only branch mutations at the executable boundary in `review/core/scripts/bulk-apply.sh`, with `tests/run.sh` fake-service cases proving rejection before any push/post and preserved author plans. Interfaces: T006 role state and T007 reviewer plan; missing/mismatched role must not grant author mutation authority.
- [X] T009 [US2] Implement exact reviewer target and freshness guards in `review/core/scripts/platform.sh`, `review/core/scripts/bulk-apply.sh`, consuming the T001/T003 freshness CLI, with tests for root replacement, same-path different-thread IDs, closed PR, moved head, reply/edit after preparation, missing/truncated conversation, already-resolved thread, lost ownership/provenance and recheck before resolution. Assert zero affected writes on each stale/incomplete case, while independent valid thread actions can still proceed. Interfaces: T007 expected thread/root/head/digest; no author approximate matching for reviewer actions.
- [X] T010 [US2] Record completed reviewer outcomes and exact activity-marker retries in `review/core/scripts/bulk-apply.sh` and `review/core/scripts/reviewer_activity.py`, preserving post and resolution steps separately and no-post still-present outcomes. Test post-success-before-local-record, cache reload, skipped preparation not handled, pending questions remaining visible and zero duplicate writes in `tests/run.sh`/`tests/test_pr_actions.py`. Interfaces: T001 marker/cache and T009 current-activity guard.

## Phase 5: User Story 3 — Independent Actions and Overlap (P1)

**Goal**: Either command order preserves remaining work and avoids duplicate thread actions.

**Independent test**: Triage→review and review→triage at the same activity version produce at most one matching thread response; new activity reactivates triage without altering review baselines.

- [X] T011 [US3] Add the shared handled-activity guard and record only completed overlapping thread work in `review/core/commands/review.md`, respecting exact ownership/fingerprints without changing full-review scope or marker-baseline policy; extend `tests/run.sh` assertions and helper-driven tests for already handled thread suppression and a review marker alone not clearing triage. Interfaces: T001/T003 activity helpers and existing 7.5d–f reconciliation.
- [X] T012 [US3] Integrate final handled-state writes and freshness checks into single-PR reviewer triage instructions in `review/core/commands/triage.md`, using the same helper operations as bulk apply; test unchanged/fresh state equivalence and single-PR no reviewer branch modifications in `tests/test_pr_actions.py`/`tests/run.sh`. Interfaces: T010 completed outcome contract and T011 overlapping guard.
- [X] T013 [US3] Add shared fixture-driven workflow-order tests in `tests/test_pr_actions.py`, `tests/test_inbox.py` and `tests/run.sh` proving both actions, triage not advancing review baseline, review clearing only actual handled thread activity, no-post idempotency, new head/reply reactivation and question visibility. Keep the T001 Python-suite registration in `tests/run.sh`; all three suites must exercise these cases under `make test`. Interfaces: T004/T005 public integration outputs and T010–T012 handled lifecycle.

## Phase 6: Polish and Quality Gates

- [X] T014 Document author/reviewer roles, both-action inbox flow, draft differences, collection uncertainty, cache location, supported adapter behavior and incremental-review follow-up in `README.md`, `docs/standalone-guide.md`, `review/skills/triage/SKILL.md` (shared Claude Code/Codex adapter) and `review/opencode/command/triage.md`; extend existing adapter assertions only where user-facing descriptions changed.
- [X] T015 Run `make test`, required `make validate` and `git diff --check`; complete the scenarios in `specs/007-inbox-action-alignment/quickstart.md` using fixtures, fix regressions and record evidence there. Keep stage-7 review separate; implementation skips every after_implement extension hook.

## Dependencies and Execution Order

T001 → T002 → T003 is the shared foundation. US1 is T004 → T005. US2 uses the same foundation and runs T006 through T010; it integrates US1's selected seeds. US3 depends on completed handling and runs T011 through T013. T014/T015 finish after all stories. Execute tasks sequentially in this ship run.

No task requires parallel execution; the teams extension is disabled. A future staffed run may inspect completed tests while adapter documentation is drafted, but the dependency order above remains authoritative.

## Implementation Strategy

Deliver the shared assessor and aligned discovery first, then reviewer preparation/apply, then overlap lifecycle. Tests belong to each deliverable and pin the boundary behavior rather than mirror implementation. Global Constraints and Interfaces in plan.md apply to every task. At 15 total tasks, ship correctness checkpoints follow T005 and T010; run `make test` between all completed tasks.

## Requirement Coverage

| Requirement | Implementing tasks | Verification focus |
|-------------|--------------------|--------------------|
| FR-001 | T002–T005 | Equal normalized snapshots use the same pure assessor |
| FR-002 | T002, T004–T005, T013 | Both actions, roles, evidence and uncertainty survive independently |
| FR-003 | T004 | Existing attention groups and issue/Discussion regressions; no invented eligibility |
| FR-004 | T002–T005, T013 | Equal effective scope; explicit draft/query/limit/closed/head/evidence exclusions |
| FR-005 | T002, T005 | Existing default/all-open/search marker policy and uncertain changed-head candidates |
| FR-006 | T002, T004–T005 | Reliable unchanged contribution versus unknown; outstanding request remains independent |
| FR-007 | T005–T007 | Mixed-role selection/state/worker/consolidated role column |
| FR-008 | T002–T005, T012 | Own feedback preserved; other-author open owned cc-review activity required |
| FR-009 | T001–T005, T009 | Root ownership and provenance; wrong-owner/manual/quoted-marker negatives |
| FR-010 | T001–T002, T010, T012–T013 | Reply/edit/head reactivation and unchanged/no-post suppression |
| FR-011 | T002, T004–T005 | Draft triage in both roles; independent review draft exclusion |
| FR-012 | T007, T012 | Isolated current-code verification with explicit outcomes |
| FR-013 | T007–T008, T012 | Zero reviewer fix commits/pushes/CI repair; author behavior retained |
| FR-014 | T006–T010, T012 | No preparation remote writes; existing approval and pending questions |
| FR-015 | T007, T009–T010, T012 | Verified fix/accepted explanation only; deferral/question/disagreement stay visible |
| FR-016 | T008–T010, T012–T013 | Exact fresh open/head/thread checks and replay recovery |
| FR-017 | T001, T010–T013 | No triage review-baseline write; only actually handled overlap cleared |
| FR-018 | T001, T007, T010–T013 | Shared single/bulk helper contract and both command orders |
| FR-019 | T003–T004, T007–T009, T012 | Checkout/index/branch snapshots, no inbox writes, hostile text stays data |
| FR-020 | T003–T005, T009–T010 | Invalid input/dependency/auth/repo errors; partial independent results retained |
| FR-021 | T004, T006–T007, T014 | Supported adapter docs cover roles, overlap, drafts and #09 boundary |
| FR-022 | T003–T005 | Fake-clock 120s deadline, 100 discoveries/reason, 20 activity/10 replies and cap warnings |
| FR-023 | T007, T010, T012–T014 | Unattended verified-policy actions only; questions never marked handled |
| SC-001 | T002–T005, T013 | All recorded equal-scope action memberships match |
| SC-002 | T007–T010, T012 | Fake-service mutation logs: zero reviewer commit/push/pre-approval writes |
| SC-003 | T010–T013 | Both command orders; at most one reply/resolution per handled activity |
| SC-004 | T001–T002, T010, T012–T013 | New head/reply reactivation versus unchanged repeated runs |
| SC-005 | T002–T005, T009, T013 | Draft/incomplete/uncertain-head/known-unchanged fixtures |
| SC-006 | T004–T005, T008, T014–T015 | Existing author/review/issue/Discussion regressions plus adapter docs and quality gates |
