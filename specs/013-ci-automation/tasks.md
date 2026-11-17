# Tasks: Unattended CI

## Setup and Foundation

- [x] T001 Add failing router/config/state/proposal tests in tests/test_ci.py and integrate them into tests/run.sh; verify missing CI coordinator fails before implementation.
- [x] T002 Implement strict schema/version/limits validation, exact comment parsing, permission routing, bot suppression, fingerprints and trusted marker eligibility in review/core/scripts/ci.py with defaults in review/config/ci.yml. Interfaces: load_config, route, fingerprint, eligible; limits sweep 1..100, turns 1..100, timeout 1..60, diff bytes 1..1000000.

## US1: Unattended assistance

Goal: automatic review/triage/assessment with visible terminal outcomes. Independent test: fake transport prepare/finalize and failure fixtures.

- [x] T003 [US1] Implement gh transport, bounded complete evidence collection, sticky per-operation markers, prepare/result validation and guarded publishers in review/core/scripts/ci.py; tests assert COMMENT only, failed/pending checks withhold, missing result becomes attention, issue labels stay configured, human threads untouched, and no duplicate result on retry.
- [x] T004 [US1] Add shared commands/unattended.md, route single --unattended through it before interactive guards in review/core/commands/{review,triage,issue}.md, and update review/skills/{review,triage,issue}/SKILL.md plus OpenCode/Spec Kit adapters. Interfaces: explicit --pr or issue target, ci proposal-only mode, unattended defaults and terminal outcome.

## US2: Authorized commands

Goal: immediate acknowledgement, fork isolation, explicit fixes. Independent test: permission/target/fork/head-race fixtures.

- [x] T005 [US2] Implement comment acknowledgement and same-repository maintainer-only file proposal commits with non-force Git ref updates in review/core/scripts/ci.py; reject unsafe paths, stale heads and unsuccessful checks before writes. Tests cover spoofed author association, fork fixes, changed heads and human triage resolution attempts.

## US3: Sweep and workflow

Goal: bounded recovery sharing item serialization. Independent test: event/sweep matrix fixtures plus actionlint of generated caller and reusable workflow.

- [x] T006 [US3] Add ci/action.yml and .github/workflows/cc-review.yml with trusted pinned checkout, pure selection, per-item concurrency, fixed empty model tool allowlist, max turns/timeout, provider inputs, always finalizer and summary. Extend ci.py selection for bounded PR+issue sweeps skipping current complete/active states; fixture assertions cover mixed entries and bot loops.

## US4: CI management

Goal: setup/status/update/disable/doctor. Independent test: temporary repository generation, preservation/migration and missing prerequisites.

- [x] T007 [US4] Implement managed caller/config/App manifest generation and lifecycle helpers in review/core/scripts/ci.py, review/core/templates/ci-workflow.yml and review/core/commands/ci.md; add concise review/skills/ci/SKILL.md and OpenCode/Spec Kit adapters. Setup skill provisions secrets/labels and dispatches/watches smoke test, doctor checks secret names/App permissions/version/labels, disable touches only managed files. Tests preserve user settings/unrelated files and reject invalid pins/schema.

## Polish

- [x] T008 Document installation, version pinning, providers, identity/browser App setup, failure remedies and unattended policy in docs/CI.md and README.md; run make test, make validate and workflow validation, resolve findings and draft RUNBOOK.md.

## Dependencies and Strategy

Execute T001..T008 in order. US1 is the first usable command slice; US2 adds authorized control, US3 event execution/recovery, US4 repeatable installation. No parallel agents (repository instruction). Test files could be extended independently after interfaces stabilize, but this pipeline executes inline. Run make test at completed task checkpoints. Correctness checkpoints follow T002 and T005; final spec/security/code review follows T008. No after_implement hooks inside ship.

## Coverage

| Requirement | Tasks |
|---|---|
| FR-001 | T004 |
| FR-002 | T002,T003,T006 |
| FR-003 | T003,T004 |
| FR-004 | T002,T006 |
| FR-005 | T002,T005 |
| FR-006 | T005 |
| FR-007 | T002,T006 |
| FR-008 | T002,T003,T006 |
| FR-009 | T003,T006,T007 |
| FR-010 | T006,T007,T008 |
| FR-011 | T002,T006 |
| FR-012 | T007 |
| FR-013 | T007 |
| FR-014 | T002,T003,T006 |
