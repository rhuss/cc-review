# Tasks: Incremental PR Review

**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

All tasks inherit the plan's Global Constraints. Execute sequentially in the isolated feature worktree. Each task writes its semantic tests first, observes failure, implements, then runs focused tests and `make test` before completion. No live hosting writes in tests.

## Phase 1: US1 and US3 — Trustworthy Contribution Scope

- [X] T001 [US1] Implement personal completion evidence, coverage fingerprints and read-only contribution comparison in `review/core/scripts/review_scope.py`, with real-Git tests in `tests/test_review_scope.py` and registration in `tests/run.sh`.

  **Interfaces**: `coverage_key(reviewers: list, settings: dict, context_files: list) -> str`; `plan_scope(repo: Path, snapshot: dict) -> dict`; CLI `prepare --repo PATH --input FILE --output DIR`. See `contracts/scope.md` and `data-model.md` for fields.

  **Tests**: first/legacy/foreign reviews -> full; completed personal chain -> incremental; no-findings completion accepted; changed coverage, missing/cyclic parents -> full; explicit full override; fast-forward delta includes fixes; pure rebase -> unchanged; mixed rebase -> only author delta; conflicts/missing objects -> full; spaced/renamed/deleted/binary paths; dirty worktree/index unchanged and no pinned completion.

## Phase 2: US2 — Explicit Verification and Finding Scope

- [X] T002 [US2] Add exact target/reconciliation, scoped finding filtering and completion generation to `review/core/scripts/review_scope.py`; extend `review/core/schemas/finding.schema.json` and semantic tests in `tests/test_review_scope.py`.

  **Interfaces**: Consume T001 scope. `verification_targets(snapshot: dict) -> dict`; `reconcile_verifications(batch: dict, outcomes: list) -> dict`; `filter_findings(scope: dict, findings: list, verified: list) -> dict`; `completion_marker(scope: dict, run_id: str, reviewers: list, verification: dict) -> dict`. Reuse `reviewer_activity.py` ownership, completeness and exact fingerprints without changing their meaning.

  **Tests**: all older owned threads included; foreign/resolved threads excluded; partial/moved/unmatched findings never imply fixed; missing/duplicate/stale/unclear verification incomplete; approved explanations distinguished; carried identity exact; ordinary unchanged findings excluded; critical unchanged finding needs evidence; failed required reviewer/dirty code/incomplete verification yields no marker; complete unresolved findings permit completion.

## Phase 3: US1–US3 — Execute the Contract Across Workflows

- [X] T003 [US1] Wire scope, verification, finding filtering and completion through `review/core/commands/review.md`, `review/core/commands/triage.md`, `review/core/commands/bulk.md`, `review/core/scripts/bulk-apply.sh`, `review/core/scripts/platform.sh`, `review/core/scripts/pr_actions.py` and reviewer/meta-review prompts; add executable wiring/selector regressions to `tests/run.sh` and `tests/test_pr_actions.py`.

  **Interfaces**: Consume T001/T002 JSON CLI and schema. Keep `ALL_CHANGED_FILES` for discovery/trust and inline anchors; use scope artifacts for dispatch; carry artifacts through bulk analysis/apply. Generate markers only after all required review/verification work, freshness and approval conditions hold. Triage never creates scope completion evidence.

  **Tests**: renewed requests remain actionable on unchanged contribution; thread pagination failure is incomplete; bulk no-findings markers attach only valid pinned completion; malformed/mismatched completion is refused; scope input/diff reaches single and bulk reviewers and critics; shared verification replaces absence-based resolution. Existing review/triage idempotency and approval tests remain green.

## Phase 4: Public Usage and Final Verification

- [X] T004 [US1] Expose `--full` consistently in review adapters and document automatic scope, personal baseline, legacy fallback, rebases and explicit verification in `README.md` and `docs/standalone-guide.md`; update adapter tests in `tests/run.sh` and complete implementation validation.

  **Interfaces**: Existing command adapters forward `--full` unchanged, including bulk and resume's recorded-options policy. Public documentation reflects T001–T003 behavior, limitations and unchanged posting permissions.

  **Tests**: adapter flag propagation and help text; full `make test`; `make validate`; `git diff --check`.

## Requirement Coverage

| Requirements | Tasks |
|--------------|-------|
| FR-001–FR-005 | T001, T003, T004 |
| FR-006 | T002, T003 |
| FR-007–FR-011 | T002, T003 |
| FR-012–FR-014 | T001, T003 |
| FR-015–FR-018 | T001, T002, T003 |
| FR-019–FR-020 | T003, T004 |
| FR-021 | T001, T002 |
| FR-022 | T003 |
| FR-023 | T001–T004 |

## Dependencies and Acceptance

T001 produces scope consumed by T002 and T003. T002 produces verification/filter/marker contracts consumed by T003. T004 documents and validates the integrated result. No task requires parallel execution. SC-001/004/005 are pinned by T001/T003; SC-002/003 by T002/T003; SC-006 by T004. Every error and Review Focus case belongs to its named task's tests.

## Post-Pipeline Walkthrough

After code review, the ship workflow drafts `RUNBOOK.md` through the walkthrough skill without executing its steps or live PR actions. This is a post-review artifact, not a prerequisite for completing implementation.
