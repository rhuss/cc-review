# Tasks: PR Review Comments

**Input**: Design documents from `/specs/001-pr-review-comments/`

**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md

**Tests**: Not explicitly requested. No test tasks generated.

**Organization**: Tasks grouped by user story. US1+US2 are combined (P1, tightly coupled). US3+US4 are combined (P2, both about comment content). US5 and US6 are separate (P3).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to

---

## Phase 1: Setup

**Purpose**: Configuration and directory structure for PR review commenting

- [x] T001 Add `pr_posting` section to config template in review/config/config-template.yml
- [x] T002 [P] Create templates directory at review/core/templates/ and add reviewer-voice.md with full voice profile content (tone: concise, direct, reasoning-focused; structural elements: what/why/fix)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Platform-level functions needed by all user stories

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T003 Add `_github_post_review` function to review/core/scripts/platform.sh for GitHub review submission API
  - **Interface**: `_github_post_review <owner> <repo> <pr_number> <json_payload_file>` -> exits 0 on success, 1 on failure; writes response JSON to stdout
  - `json_payload_file` contains `{"body": "...", "event": "REQUEST_CHANGES|COMMENT", "comments": [{"path": "...", "line": N, "side": "RIGHT", "body": "..."}]}`
- [x] T004 [P] Add `_github_fetch_reviews` function to review/core/scripts/platform.sh for listing existing reviews on a PR
  - **Interface**: `_github_fetch_reviews <owner> <repo> <pr_number>` -> writes JSON array of review objects to stdout (paginated internally)
- [x] T005 [P] Add `_github_parse_diff_hunks` function to review/core/scripts/platform.sh to build file/line map from `gh pr diff` output
  - **Interface**: `_github_parse_diff_hunks <pr_number>` -> writes JSON object `{"file": [{"start": N, "end": N}]}` to stdout

**Checkpoint**: Platform functions ready for review command integration

---

## Phase 3: User Stories 1+2 - Interactive Review, Posting, and Attribution (Priority: P1) MVP

**Goal**: When `--pr` is provided, present findings interactively, then post accepted findings as a single GitHub review submission with inline comments and source attribution.

**Independent Test**: Run `cc-review --pr <number>` on a PR, accept some findings, verify inline comments appear on GitHub with correct source footers.

### Implementation for User Stories 1+2

- [x] T006 [US1] Add Step 7.5 skeleton to review/core/commands/review.md: detect `--pr` flag and gate the PR posting flow
- [x] T007 [US1] Implement diff hunk filtering in Step 7.5: partition findings into `inline_findings` (within diff hunks) and `summary_only_findings` (outside diff) in review/core/commands/review.md
- [x] T008 [US1] Implement interactive local review in Step 7.5 of review/core/commands/review.md: present Critical/Important one at a time (accept/reject/edit), Minor/Notable in batch. The "edit" option here captures the user's intent and stores `edited_text` on the finding; the full edit UX (text-only editing of description and mitigation) is completed in T027
- [x] T009 [US2] Implement comment body formatting in Step 7.5 of review/core/commands/review.md: structured what/why/fix with source footer from `source_agent` and `also_reported_by` fields
- [x] T010 [US1] Implement review submission assembly in Step 7.5 of review/core/commands/review.md: build JSON payload with `body`, `event` (REQUEST_CHANGES vs COMMENT), `comments` array, and `run_id` marker
- [x] T011 [US1] Implement summary body generation in Step 7.5 of review/core/commands/review.md: findings table (Severity, File, Description, Source columns), rejected count, gate outcome, participating agents list
- [x] T012 [US1] Implement posting via `_github_post_review` from platform.sh in Step 7.5 of review/core/commands/review.md: call the platform function with assembled payload, handle success (log review URL). Error/recovery handling is in T026
- [x] T013 [US1] Implement reject-all guard in Step 7.5: skip posting when no findings are accepted, in review/core/commands/review.md

**Checkpoint**: Core PR commenting flow works end-to-end. Findings appear as inline comments with attribution.

---

## Phase 4: User Stories 3+4 - "What Went Well" and Reasoning Voice (Priority: P2)

**Goal**: The review summary includes agent-generated positive observations. Comment text uses a dedicated reviewer voice when prose plugin is available.

**Independent Test**: Run review on a PR, verify summary has "What Went Well" section. Compare comment tone with and without prose plugin.

### Implementation for User Stories 3+4

- [x] T014 [US3] Extend the goal-alignment agent prompt in review/core/agents/goal-alignment.md to generate a "What Went Well" section identifying positive patterns when running in PR mode
- [x] T015 [US3] Integrate "What Went Well" output into the summary body generation in Step 7.5 of review/core/commands/review.md (place before findings table)
- [x] T016 [US4] Verify and refine the reviewer voice profile in review/core/templates/reviewer-voice.md (created in T002): ensure it defines the three structural elements (what/why/fix), provides example outputs for each severity level, and documents the fallback template for when the prose plugin is absent
- [x] T017 [US4] Implement prose plugin detection and voice integration in Step 7.5 of review/core/commands/review.md: detect prose plugin, load reviewer voice, apply to comment text; fall back to hardcoded template

**Checkpoint**: Reviews include positive highlights and comments use structured reasoning voice.

---

## Phase 5: User Story 5 - Re-run Lifecycle Management (Priority: P3)

**Goal**: On re-run with `--pr`, detect previous cc-review reviews, resolve fixed threads, and post only new findings.

**Independent Test**: Run review twice on same PR, fix an issue between runs, verify fixed thread is resolved and no duplicates appear.

### Implementation for User Story 5

- [x] T018 [US5] Implement previous run detection in Step 7.5 of review/core/commands/review.md: scan reviews for `<!-- cc-review:run-id: -->` marker using `fetch_reviews` from platform.sh
- [x] T019 [US5] Implement finding-to-thread matching in Step 7.5 of review/core/commands/review.md: extract path/line from previous inline comments, match against current findings using location-based overlap (3-line tolerance)
- [x] T020 [US5] Implement thread resolution for fixed findings in Step 7.5 of review/core/commands/review.md: call `_github_resolve_thread` and `_github_post_reply` from platform.sh with resolution reason
- [x] T021 [US5] Implement new-findings-only posting in Step 7.5 of review/core/commands/review.md: exclude matched findings from the submission, post only unmatched new findings

**Checkpoint**: Re-runs cleanly resolve fixed threads and avoid duplicates.

---

## Phase 6: User Story 6 - Triage Integration (Priority: P3)

**Goal**: The triage command recognizes cc-review threads and manages their lifecycle based on replies.

**Independent Test**: Post a cc-review comment, reply with "fixed," run triage, verify thread is resolved.

### Implementation for User Story 6

- [x] T022 [US6] Add cc-review bot profile detection to triage thread classification in review/core/commands/triage.md: recognize threads by source footer pattern `_Source: .* agent_` or `_Source: coderabbit`
- [x] T023 [US6] Implement reply assessment logic for cc-review threads in review/core/commands/triage.md: parse reply intent (fixed, won't fix, deferred), verify fix against current code state
- [x] T024 [US6] Implement thread resolution for confirmed fixes and acknowledged rejections in review/core/commands/triage.md: call `_github_resolve_thread` and `_github_post_reply` with acknowledgment via platform.sh

**Checkpoint**: Triage fully manages cc-review thread lifecycle.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, edge cases, and integration hardening

- [x] T025 [P] Add edge case handling for findings on deleted files in Step 7.5 of review/core/commands/review.md
- [x] T026 [P] Add error/recovery handling around `_github_post_review` call in Step 7.5 of review/core/commands/review.md: detect `gh` auth failure, write accepted findings to `.cc-review/recovery-<run-id>.json`, and report failure with retry instructions
- [x] T027 [P] Add edit action implementation for interactive review in Step 7.5 of review/core/commands/review.md: allow text-only editing of description and mitigation (completes the edit stub from T008)
- [x] T029 [P] Add truncation guard for large finding sets in Step 7.5 of review/core/commands/review.md: if accepted inline findings exceed a configurable limit (default 50), truncate to the limit, log a warning listing omitted findings, and include omitted findings in the summary body only
- [x] T028 Run quickstart.md validation scenarios

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies, start immediately
- **Foundational (Phase 2)**: Depends on Setup completion, BLOCKS all user stories
- **US1+US2 (Phase 3)**: Depends on Foundational (Phase 2) completion
- **US3+US4 (Phase 4)**: Depends on Phase 3 (needs Step 7.5 skeleton and summary body)
- **US5 (Phase 5)**: Depends on Phase 3 (needs posting flow and run-id marker)
- **US6 (Phase 6)**: Depends on Phase 3 (needs cc-review comment format established)
- **Polish (Phase 7)**: Depends on Phase 3 minimum, ideally all prior phases

### Within Each Phase

- Tasks marked [P] can run in parallel
- Unmarked tasks should execute sequentially in listed order
- T006 (Step 7.5 skeleton) must complete before T007-T013

### Parallel Opportunities

- T001 and T002 can run in parallel (Phase 1)
- T003, T004, T005 can run in parallel (Phase 2, different functions in same file but independent)
- T014 and T016 can run in parallel (Phase 4, different files)
- T022-T024 are sequential (Phase 6, same file)
- T025, T026, T027 can run in parallel (Phase 7, different edge cases)

---

## Implementation Strategy

### MVP First (Phase 1 + 2 + 3)

1. Complete Phase 1: Config and templates setup
2. Complete Phase 2: Platform functions (post_review, fetch_reviews, parse_diff_hunks)
3. Complete Phase 3: Interactive review + posting + attribution
4. **STOP and VALIDATE**: Test with `--pr` on a real PR
5. This delivers the core value: findings visible on the PR

### Incremental Delivery

1. Setup + Foundational + US1+US2 -> Core posting works (MVP)
2. Add US3+US4 -> Reviews include highlights and use reviewer voice
3. Add US5 -> Re-runs are clean (no duplicates, auto-resolve)
4. Add US6 -> Triage manages cc-review threads
5. Polish -> Edge cases and hardening

---

## Notes

- All implementation is in Markdown command files (prompt-based), not compiled code
- The review/core/commands/review.md Step 7.5 is the primary implementation target
- Platform functions in platform.sh are shell scripts callable from the prompt context
- The reviewer voice profile is a Markdown file defining tone guidelines
- Commit after each task or logical group
