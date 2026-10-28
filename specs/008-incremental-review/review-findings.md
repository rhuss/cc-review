# Code Review: Incremental PR Review

**Spec**: [spec.md](spec.md)
**Date**: 2026-10-28
**Functional compliance**: 23/23 requirements
**Gate**: PASS after post-fix regression verification

## Review Coverage

The six perspectives were checked sequentially inline by the implementing agent, honoring the project's prohibition on Codex subagents without a parallel-work request. This does not provide six independent reviewer contexts. CodeRabbit provided the independent external review of commit `c1bd5d7`; subsequent corrections were checked inline and with regression tests. Codex CLI review was not launched under the same project constraint; Copilot is disabled in the configured deep-review profile.

| Perspective | Evidence checked |
|-------------|------------------|
| Correctness | Real Git fast-forward/rebase/conflict/deletion paths; exact verification; preservation of carried concerns; final head check |
| Architecture | Existing portable Markdown engine and activity helpers reused; one deterministic scope/verification module; no new runtime packages |
| Security | Identity/provenance, quoted markers, path bounds, safe argument arrays, temporary index and existing remote-action authority |
| Production readiness | Bounded Git operations, temporary-index cleanup, partial API evidence, stale publication and incomplete-run recovery |
| Test quality | Real Git histories, actual shared Bash/Zsh preparation with fake hosting, missing-object fetch, precise outcomes and HTTP-boundary fixture tests |
| Goal alignment | All issue #8 requirements mapped below; no new posting permissions or triage baseline advancement |

## Findings and Corrections

1. **Important, fixed:** Recheck the live PR head after thread refresh immediately before marker publication. Regression: `test_bulk_apply_marker_validates_completion_evidence` makes the second head read fail and requires zero posts.
2. **Minor, fixed (CodeRabbit):** Preserve valid partial thread arrays when collection returns incomplete status, so known thread IDs remain available without asserting complete coverage. Regression: `test_platform_fetch_reviews_retains_partial_thread_ids`.
3. **Important, fixed:** A first incomplete personal review can remove the hosting service's request without completing the work. Retain it as a personal review candidate, including at the same head, until superseded by a completed personal run. Regressions: `test_incomplete_personal_attempt_remains_work_after_request_is_cleared` and `test_bulk_select_incomplete_current_head`.
4. **Important, fixed:** Current head/base objects may be absent when reviewing from the PR branch. Fetch those current objects before pure comparison; do not fetch unavailable old baselines to disguise fallback. Regression: shared Bash/Zsh preparation uses a genuinely missing upstream commit and a local Git remote.

CodeRabbit also suggested suppressing incomplete notices entirely. That alternative was not adopted: approved partial notices remain explicitly incomplete and carry no completed-baseline marker. The independent pending-review assessment above prevents them from clearing review work. This preserves useful partial reporting and the agreed approval policy.

## Functional Compliance

| Requirement | Implementation evidence |
|-------------|-------------------------|
| FR-001 | Shared Personal PR Review Scope in single and bulk execution |
| FR-002 | `review_scope.parse_completion` and `select_baseline` |
| FR-003 | `plan_scope` explained full fallback and `--full` |
| FR-004 | Whole contribution delta, including fix code, passed to dispatch |
| FR-005 | Temporary-index contribution reconstruction and real rebase tests |
| FR-006 | `filter_findings`, schema additions, reviewer/critic instructions |
| FR-007 | `verification_targets` across all owned unresolved threads |
| FR-008 | Explicit reconciliation and canonical carried findings; no absence heuristic |
| FR-009 | Approved explanation outcomes and retained existing triage policy |
| FR-010 | Shared exact activity fingerprints, existing reply/resolution recovery |
| FR-011 | Triage never emits completion markers or advances review baselines |
| FR-012 | Unchanged mode skips dispatch and new review posts without requests |
| FR-013 | Explicit request evidence survives head markers; unchanged acknowledgment path |
| FR-014 | Shared assessment retains explicit requests and uncertain selection separately |
| FR-015 | `completion_marker` validates pinned code, exact required results and verification |
| FR-016 | Incomplete markers, coverage warnings and personal-attempt retry selection |
| FR-017 | Disclosed full-input command reviewer scope with common finding filtering |
| FR-018 | Scope, baseline, outcomes, actual coverage and limitations in reports |
| FR-019 | Exact activity guards, refreshed completion and final publication head check |
| FR-020 | Existing role/approval/checkout rules; explicit local non-PR skip guards |
| FR-021 | Completed full-rooted personal chains with compatible fingerprints |
| FR-022 | No comparison/network mutation in inbox; execution finalizes scope |
| FR-023 | Regression suites, public adapters and user documentation |

## Validation

- Final full regression suite, including the current-object compatibility correction: 1,311 assertions passed, 0 failed (162 tests).
- Scope/verification suite: 29 tests, including executable Bash/Zsh preparation and local non-PR behavior.
- PR action suite: 28 tests, including incomplete personal work and renewed requests.
- CodeRabbit: completed successfully with 2 minor findings, reviewed against current code as described above.
- `make validate`: passed; existing optional plugin-icon warning remains unrelated.
- Post-fix review found no remaining Critical or Important findings. Approved partial notices remain intentionally supported as explained above.

No live PR comments, resolutions or fixture branches were created for validation. The remaining manual boundary is an installed agent/provider session against a real PR; the draft walkthrough describes the offline engine coverage and this limitation.
