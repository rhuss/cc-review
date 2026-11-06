# Tasks: Streamlined Inbox Report with Guided Tour and Fan-Out

**Feature**: `012-inbox-tour-orchestration` | **Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

Organized by user story (US1 streamlined report, US2 guided tour, US3 fan-out) plus the FR-017 bulk explicit-list capability. `[P]` marks tasks that touch different files and have no incomplete dependency, so they may run in parallel.

Primary files touched: `review/core/commands/inbox.md`, `review/core/scripts/bulk-select.sh`, `review/core/commands/{review.md,triage.md,bulk.md}`, `tests/`, and the per-harness inbox entry points.

## Phase 1: Setup

- [x] T001 [P] Create a representative read-only inbox snapshot fixture at `tests/fixtures/inbox-snapshot.json` covering several "Needs your attention" items across `pr`, `issue`, and `discussion`, each with `reasons`, state, `detail`, and (for PRs) the shared `assessment`, plus items for the "Waiting on others" and "No current action" groups, and a second variant with an empty attention group and a source/coverage warning, for use by report and selection tests (including the empty-state and coverage-disclosure assertions in T007).
- [x] T002 Confirm the exact change sites before editing: `review/core/commands/inbox.md` Section 4 (Present the Overview) and Section 5 (Clean Up), `review/core/scripts/bulk-select.sh` selector `case`, and the bulk handoff blocks of `review/core/commands/review.md`, `triage.md`, and `bulk.md`. Record the anchors in the task notes (orientation only; no edits).

## Phase 2: Foundational

No blocking cross-cutting tasks: the read-only collector (`inbox.py`), harness core resolution, and the shared PR assessor already exist and are reused unchanged. Each user story below is an independent increment. Proceed to Phase 3.

## Phase 3: User Story 1 — Streamlined report (P1, MVP)

**Goal**: `inbox` leads with a scannable attention table and a detailed assessment section, with the other groups reduced to brief lists, staying read-only.

**Independent test**: Run `inbox` on a repo with several attention items; confirm the table, the per-item detail blocks, the brief lists, and an unchanged working tree (quickstart Scenario 1).

- [x] T003 [US1] In `review/core/commands/inbox.md` Section 4, render "Needs your attention" as a Markdown table with columns Item (type+number as link), What, Why you, Certainty (`Explicit`/`Inferred`/`Uncertain`), Next step, ordered explicit-before-uncertain then most-recently-updated, per `contracts/inbox-report.md` (FR-001).
- [x] T004 [US1] In `review/core/commands/inbox.md` Section 4, add the detailed per-item assessment section below the table: one block per attention item with the factual situation (keeping the explicit/inferred/uncertain discipline), a clearly labeled "My take" recommendation that may state no response is needed, and at least one evidence link (FR-002, FR-003).
- [x] T005 [US1] In `review/core/commands/inbox.md` Section 4, render "Waiting on others" and "No current action" as brief two-column lists and compress the scope header and coverage account while keeping every coverage limit and warning (FR-004, FR-005).
- [x] T006 [US1] In `review/core/commands/inbox.md` (Boundaries and Section 5), re-affirm that producing the report performs no write (no comment, thread resolution, push, agent launch, or working-tree change) (FR-006).
- [x] T007 [P] [US1] Add a report-structure test (extend `tests/test_inbox.py` or add `tests/test_inbox_report.py`) that renders from `tests/fixtures/inbox-snapshot.json` and asserts the five table columns, one detail block per attention item each with a "My take" line and an evidence link, and brief lists for the other two groups; using the empty/coverage-warning fixture variant, assert the empty attention group renders "None found in the inspected scope." and that the coverage warning is disclosed in the account (SC-001, SC-005, FR-005 edge case).

## Phase 4: User Story 2 — Guided tour (P2)

**Goal**: An opt-in end-of-report prompt starts a tour that walks up to five attention items one at a time, with next-five paging, all read-only.

**Independent test**: Accept the prompt, tour the default top five and then a custom selection, confirm paging and the read-only decline/empty cases (quickstart Scenario 2). Depends on US1 (the tour walks the attention items in report order).

- [x] T008 [US2] In `review/core/commands/inbox.md`, move the `$INBOX_TMP`/`snapshot.json` cleanup from Section 5 (immediately after the report) to the true end of the command (after the user declines the tour, or after the tour/fan-out completes), keeping cleanup scoped to the private temp dir (research R-004, FR-011).
- [x] T009 [US2] In `review/core/commands/inbox.md`, add the end-of-report prompt: offered only when the attention group is non-empty and the run is interactive; declining or a non-interactive run ends with the complete read-only report. Also remove the existing Section 5 line stating the report is returned "without automatically offering or executing an action menu", which this prompt deliberately relaxes (spec Assumptions); the report content above the prompt stays read-only (FR-007; `contracts/tour-and-fanout.md`).
- [x] T010 [US2] In `review/core/commands/inbox.md`, add tour selection: offer the default top five or let the user type specific item numbers from the table, cap at five, reject non-attention or over-cap picks with a clear message; present the selected items one at a time (FR-008, FR-009).
- [x] T011 [US2] In `review/core/commands/inbox.md`, present each toured item with a per-item subagent that reads only that item's slice of `snapshot.json` where the harness supports subagents, and fall back to inline sequential presentation otherwise (FR-009, FR-019).
- [x] T012 [US2] In `review/core/commands/inbox.md`, add next-batch handling: after a batch, offer the next five unvisited attention items in report order or a re-run, and stop offering a next batch when none remain (FR-010, SC-006).

## Phase 5: User Story 3 — Fan-out orchestration (P3) + bulk explicit list (FR-017)

**Goal**: From the tour, delegate acting to `review`/`triage`/`issue`, and batch several PRs into `bulk` via a new explicit-list selector; `inbox` never reimplements the commands.

**Independent test**: Act on single items and confirm the matching command runs as if invoked directly; batch several PRs and confirm the bulk run matches `bulk-select.sh --prs` on the same list (quickstart Scenarios 3 and 4). The bulk explicit-list tasks (T013-T015, T019) are independent infra; the inbox fan-out tasks depend on US2.

- [x] T013 [P] [US3] Add an explicit-list mode to `review/core/scripts/bulk-select.sh`: a `--prs <n,...>` selector that resolves exactly those PRs through the shared assessor (`pr_actions.py select`, the same one `bulk-select.sh` already invokes) and prints the unchanged `{"selected": [...], "excluded": [...]}` contract; de-duplicate preserving order, require positive integers, reject combination with `--all-open`/`--search` (exit 2), keep exit codes 0/1/2/75 (FR-017, FR-018; `contracts/bulk-explicit-list.md`).
- [x] T014 [P] [US3] Thread `--prs <list>` through the bulk handoff of `review/core/commands/review.md` and `triage.md`: accept it with `--bulk`, reject it with `--pr` (`Error: --prs and --pr cannot be combined`) and with `--all-open`/`--search`, and forward it to `bulk.md` (FR-017).
- [x] T015 [US3] In `review/core/commands/bulk.md`, accept the explicit PR list as selector kind `explicit`, record it in the run selector state, and pass `--prs` to `bulk-select.sh`, leaving the analysis loop, decision table, apply, and resume unchanged (FR-017, FR-018). Depends on T013, T014.
- [x] T016 [US3] In `review/core/commands/inbox.md`, add the per-item fan-out offer within the tour: `review --pr N` or `triage --pr N` for a PR (offer both when both apply), the `issue` command for an issue, a textual suggestion only for a Discussion; invoke the command and resume the tour on return; act only on explicit user choice (FR-012, FR-014, FR-015). Depends on US2.
- [x] T017 [US3] In `review/core/commands/inbox.md`, add batch fan-out: for several selected PRs, invoke `review --bulk --prs <list>` and/or `triage --bulk --prs <list>` with the list passed unfiltered so `bulk` surfaces exclusions (FR-013, FR-018). Depends on T013-T015, T016.
- [x] T018 [US3] In `review/core/commands/inbox.md`, gate fan-out on a local checkout of the target repo and state that acting is unavailable otherwise, and add the text-handoff fallback (print the exact command) where the harness cannot chain invocations in one session (FR-016, FR-019). Depends on T016.
- [x] T019 [P] [US3] Add a bulk explicit-list selection test in `tests/` asserting `bulk-select.sh --prs` returns the shared-assessor `{selected, excluded}` shape, surfaces an ineligible PR (e.g., a draft under review) as `excluded` rather than dropping it, and rejects `--prs` combined with `--all-open`/`--search`/`--pr` (SC-003, SC-004, FR-018).

## Phase 6: Polish & Cross-Cutting

- [x] T020 [P] Update `review/skills/inbox/SKILL.md` so its description/argument-hint notes the report is read-only by default with an opt-in tour; keep the shim under 50 lines with no review logic (CLAUDE.md SKILL.md contract).
- [x] T021 [P] Reflect the tour/fan-out and read-only-default behavior in the other harness entry points (`review/opencode/command/inbox.md`, `speckit/commands/speckit.cc-review.inbox.md`) so all harnesses describe the feature consistently.
- [x] T022 Run the quickstart scenarios in `specs/012-inbox-tour-orchestration/quickstart.md` end to end and confirm SC-001 through SC-006; fix any gaps found.

## Dependencies

- US1 (T003-T007) is independent and is the MVP.
- US2 (T008-T012) depends on US1 (the tour walks the attention table in report order).
- US3 bulk explicit-list (T013-T015, T019) is independent infrastructure and may be built in parallel with US1/US2. US3 inbox fan-out (T016-T018) depends on US2 (and on T013-T015 for the batch path, T017).
- Polish (T020-T022) runs after the stories it documents/validates.

## Parallel execution examples

- Early infra in parallel: T001, T013, T014 (different files, no incomplete deps).
- Tests alongside their story: T007 with US1, T019 with US3 infra.
- Docs in parallel at the end: T020, T021.

## Implementation strategy

- **MVP**: User Story 1 only (T001-T007). Ships a readable inbox with the explanation preserved; independently valuable and deployable.
- **Increment 2**: Add US2 (tour) on top of the MVP.
- **Increment 3**: Add US3 (fan-out), building the bulk explicit-list infra (parallelizable) and wiring the tour's per-item and batch delegation.
- Land polish (T020-T022) last.
