# Tasks: Review Convergence

**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

All tasks inherit Global Constraints. Work sequentially in this isolated worktree; write failing semantic tests before implementation and run focused tests plus `make test` after each task. Setup uses existing Python/Bash tooling; no new scaffolding/dependency task is needed.

## Phase 1: US1 — Collect conversation history (MVP)

- [X] T001 [US1] Implement history normalization/CLI in `review/core/scripts/review_continuity.py` and bounded read-only comment collection in `review/core/scripts/platform.sh`; enrich review/thread source URLs, add history and stubbed-collector tests to `tests/test_review_continuity.py`, and register the suite in `tests/run.sh`.

  **Interfaces**: `prepare_history(snapshot: dict) -> dict`; CLI `prepare --input FILE`; `fetch_issue_comments(owner, repo, pr_number)` array stdout/nonzero on partial collection. Input/output fields in contracts/continuity.md and data-model.md are authoritative.

  **Tests**: empty complete history is first review; incomplete empty history is uncertain; manual submitted review establishes follow-up but no baseline; pending/foreign reviews do not; personal root and explicit review summary do; ordinary participation does not. Preserve resolved threads, all replies and source URLs. Missing/duplicate IDs, incomplete comments, malformed GraphQL/null arrays and pagination caps disclose uncertainty. Fingerprint changes with body, head or identity. Validate CLI and no network mutations.

## Phase 2: US2 — Enforce continuity and materiality

- [X] T002 [US2] Implement semantic decision validation and convergence conclusion in `review/core/scripts/review_continuity.py`; extend `tests/test_review_continuity.py` with code-backed decision and CLI scenarios.

  **Interfaces**: Consume T001 History; `assess(history: dict, head_oid: str, fingerprint: str, findings: list, decisions: list, concerns: list, coverage_complete: bool, verification_complete: bool) -> dict`; CLI `assess --input FILE`. Retain exact scope-verified carried material findings; overlaps become continuations rather than new comments.

  **Tests**: fixed-plus-optional-polish clean; material regression retained; Minor/Notable and impact-free severity inflation suppressed; duplicate concerns and acknowledged Notables not new; unanswered questions prevent clean; promises remain open; reversal needs source/evidence/reason; accepted explanation needs approval; summary sources require all constituents assessed. Missing/duplicate/unknown decisions or sources, invalid statuses and stale head/fingerprint prevent clean. Failed coverage/verification prevents clean. Initial findings pass unchanged; full fallback/override retain follow-up policy. Scope engine regression suite retains Critical-only unchanged-code policy and exact ownership.

## Phase 3: US3 — Execute one policy across workflows

- [X] T003 [US3] Wire collection, history dispatch and assessment through `review/core/commands/review.md`, `review/core/commands/bulk.md`, `review/core/agents/preamble.md`, `review/core/agents/meta-skeptic.md`, `review/core/agents/meta-calibrator.md`; document behavior in `README.md` and `docs/standalone-guide.md`; add executable wiring/contract regressions in `tests/test_review_continuity.py` and finish validation.

  **Interfaces**: Consume T001/T002 JSON artifacts under `$SCOPE_DIR` (bulk `$PR_DIR/scope/`). Pass absolute history paths before prompt dispatch and through merge/meta/report/fix workers. Apply existing scope filtering then semantic continuity assessment after calibration and after final fixes. Feed new/continued material concerns into gate/report; existing verification remains the sole authority for owned thread resolution. Refresh live history/head before publication and withhold stale actions.

  **Tests**: both dispatch paths and all critics receive history even if meta-review is skipped; command findings pass the same mandatory policy; missing artifacts cannot yield clean; fixing cannot revive optional suggestions; full fallback/`--full` do not erase context; no zero-finding quota; no new automatic write/approval. Full `make test`, `make validate`, `git diff --check`.

## Dependencies and Delivery

T001 → T002 → T003. T001 is an independently usable history artifact; T002 enforces offline assessment; T003 completes user-facing execution. No parallel agent work is requested. Tests can run independently but these tasks edit shared files and are deliberately sequential.

## Requirement Coverage

| Requirement | Tasks |
|-------------|-------|
| FR-001–FR-003 | T001, T003 |
| FR-004 | T003 |
| FR-005–FR-008 | T002, T003 |
| FR-009–FR-014 | T002, T003 |
| FR-015–FR-018 | T003 |
| FR-019 | T001–T003 |
| SC-001–SC-003 | T001, T002 |
| SC-004–SC-005 | T003 |

## Checkpoints

After T001 and T002, inspect correctness against the spec and record checkpoint findings/fixes. Final review is separate from implementation. After code review, draft RUNBOOK.md without executing walkthrough steps or live PR actions.
