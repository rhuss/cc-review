# Feature Specification: Incremental PR Review

**Feature Branch**: `008-incremental-review`

**Created**: 2026-10-28

**Status**: Draft

**Input**: Agreed revisit in `brainstorm/09-incremental-review.md`; tracking issue https://github.com/rhuss/cc-review/issues/8.

## Overview

Follow-up review automatically examines changed author content since the authenticated user's latest trustworthy completed cc-review run. It verifies earlier findings explicitly, preserves unresolved concerns without duplicate comments, and distinguishes upstream rebases from substantive changes. `--full` requests a full PR review. Existing approval and independent review/triage rules remain in force.

## Clarifications

### Session 2026-10-28

Smart-oversight clarification selected conservative defaults consistent with the agreed brainstorm:

- Q: Can legacy run markers prove completed coverage? → A: No. Require explicit trustworthy completion and coverage evidence; otherwise perform a full review once to establish it.
- Q: What happens when the enabled reviewer set or relevant review settings change? → A: Require matching coverage evidence or perform a full review. Do not borrow another run's unperformed coverage.
- Q: Can a no-findings run become a baseline? → A: Yes, when its personal completion evidence covers the required review and verification work; a bare no-findings marker is insufficient.
- Q: How are reviewers without delta support handled? → A: Run them with full context, disclose their actual scope, and apply the same finding-scope policy. Failure of a required enabled reviewer leaves the run incomplete.
- Q: What happens when code comparison succeeds but thread collection fails? → A: Preserve useful review results, mark verification incomplete, withhold unsupported thread actions and do not advance the baseline.

## User Scenarios & Testing

### User Story 1 - Review Follow-up Changes (Priority: P1)

A reviewer runs single-PR or bulk review after the author updates a previously reviewed PR. The review examines the entire new delta, including fixes, with the rest of the PR available as context.

**Why this priority**: Avoids repeatedly reviewing unchanged content without skipping regressions in fixes.

**Independent Test**: Compare first-review, personal-baseline, other-reviewer and explicit-full snapshots and check selected scope and explanation.

**Acceptance Scenarios**:

1. **Given** a trustworthy completed personal review and substantive new changes, **When** review runs, **Then** it automatically reviews the entire delta and states its baseline.
2. **Given** only fixes to previous findings, **When** review runs, **Then** those fixes remain in the review delta.
3. **Given** no trustworthy personal baseline or an explicit `--full`, **When** review runs, **Then** it examines the full PR and explains the mode.
4. **Given** unchanged code outside the delta, **When** a new concern is found there, **Then** only a critical concern with concrete evidence can be reported.

### User Story 2 - Verify Earlier Findings (Priority: P1)

A reviewer verifies open concerns from all their previous cc-review runs against current code. Fixed concerns can be resolved, while partial fixes, disagreements and uncertain outcomes remain visible in existing threads.

**Why this priority**: A finding disappearing from the next review must never falsely resolve an unfixed problem.

**Independent Test**: Prepare fixed, still-present, partial and unclear outcomes; exercise both review/triage execution orders and repeat without new activity.

**Acceptance Scenarios**:

1. **Given** an earlier finding absent from the new review, **When** verification lacks proof of a fix, **Then** its thread remains open.
2. **Given** a partially fixed finding, **When** verified, **Then** the remaining concern stays in the original thread without reposting.
3. **Given** a verified fix already handled at the same code and conversation state, **When** either command repeats, **Then** no duplicate reply or resolution occurs.
4. **Given** completed triage and outstanding changed-code review, **When** assessed again, **Then** review remains outstanding.

### User Story 3 - Handle Rebases and Incomplete Evidence (Priority: P1)

A reviewer sees whether the author's contribution changed across a rebase or history rewrite. The system avoids unnecessary review when equivalence is proven and reports fallback or incomplete coverage otherwise.

**Why this priority**: A changed commit identifier is not evidence of changed author contribution.

**Independent Test**: Exercise fast-forward changes, pure rebases, conflict resolutions, unavailable history and renewed requests against known contributions.

**Acceptance Scenarios**:

1. **Given** proven unchanged contribution and no renewed request, **When** assessed, **Then** no new code review or review post is required and pending thread work remains.
2. **Given** that same contribution and a renewed review request, **When** processed, **Then** earlier findings are verified and the request acknowledged without an automatic full review.
3. **Given** unreliable comparison evidence, **When** processed, **Then** full review is selected with a reason.
4. **Given** incomplete required review or thread evidence, **When** a run finishes, **Then** it reports incomplete coverage and establishes no completed baseline.

### Edge Cases

- A newer review by another person cannot replace the user's baseline.
- A completed review with findings remains completed; completion does not imply approval or all findings fixed.
- A no-findings review can establish a baseline only with trustworthy completion and coverage evidence.
- Configuration changes or added reviewers must not silently inherit coverage they never performed.
- Earlier open findings can predate the chosen baseline and can move across files or lines.
- Conflict-resolution edits and mixed rebase/substantive changes remain reviewable.
- Deleted or unavailable historical commits require explained fallback rather than unsafe equivalence claims.
- Truncated conversations, failed reviewers or partial posting cannot masquerade as completed work.
- A changed head or thread after preparation invalidates affected prepared actions before posting.
- Local branch reviews without PR context retain their existing behavior; `--full` does not require PR context.

## Requirements

### Functional Requirements

- **FR-001**: Apply automatic incremental mode consistently in single-PR and bulk review when a trustworthy completed personal baseline exists and content changed.
- **FR-002**: Select only the authenticated user's latest trustworthy completed cc-review run for the same PR; never use another person's run as their baseline.
- **FR-003**: Perform full review for first reviews, explicit `--full`, or unreliable baseline/comparison evidence, and report the reason.
- **FR-004**: Review the entire delta, including fixes; permit access to the full PR and files as context.
- **FR-005**: Distinguish author contribution changes from upstream movement, retaining substantive conflict resolutions and mixed changes.
- **FR-006**: Permit new findings outside the delta only when critical and supported by concrete evidence; identify delta, carried and unchanged-critical scopes.
- **FR-007**: Verify all unresolved personal cc-review findings, including older runs, against current code; record fixed, still present or unclear.
- **FR-008**: Never infer fixed from absent, unmatched, moved or reclassified findings. Keep partial fixes and unclear concerns open in their original threads.
- **FR-009**: Preserve triage's handling of accepted explanations, disputed reasoning, deferrals and questions under existing approval rules.
- **FR-010**: Reuse consistent verification and exact handled-activity rules between review and triage; avoid duplicate replies, resolutions and reposted findings in either execution order.
- **FR-011**: Triage must not advance the code-review baseline. Review clears overlapping thread work only when actually handled.
- **FR-012**: Proven unchanged contribution without a renewed request requires no new code review or review post; retain pending thread work independently.
- **FR-013**: Honor a renewed explicit review request on proven unchanged contribution through verification and acknowledgment; require `--full` for an explicitly requested full reassessment.
- **FR-014**: Preserve explicit request evidence and distinguish uncertainty from proven unchanged contribution in shared action assessment.
- **FR-015**: Record completed baseline evidence only after all required review and verification work completes; unresolved findings do not by themselves make a run incomplete.
- **FR-016**: Treat missing thread evidence, failed required reviewers and unsupported incremental coverage as explicit limitations; incomplete runs cannot establish completed baselines or clear outstanding personal review work, including after the hosting service removes a request.
- **FR-017**: Disclose the actual scope of every reviewer. A reviewer unable to accept delta scope must use an explained full-scope fallback subject to the same finding-scope policy, or leave the run incomplete.
- **FR-018**: Reports state mode, personal baseline, reviewed scope, verification outcomes, fallback reasons and incomplete coverage, including empty-delta outcomes.
- **FR-019**: Recheck current PR head, open state and exact affected thread activity before remote writes; stale actions are withheld and reported.
- **FR-020**: Preserve existing approval, author/reviewer-role, fix-loop and checkout isolation rules, supported adapters and default draft exclusions.
- **FR-021**: Review-chain evidence must preserve the cumulative coverage established by a complete full review and subsequent complete delta reviews. Legacy evidence cannot imply unproven coverage.
- **FR-022**: Keep inbox read-only and selection bounded. Lightweight assessment may retain uncertain candidates; execution establishes final review scope.
- **FR-023**: Provide regression tests and user documentation for automatic mode, `--full`, fallback, rebases, partial findings and review/triage independence.

### Key Entities

- **Personal review baseline**: PR, reviewer, reviewed contribution, covered reviewers, completion and provenance evidence.
- **Review scope**: Full, incremental or unchanged, baseline/head, changed content, evidence confidence and fallback reason.
- **Prior finding verification**: Owned thread identity, finding concern, current code/conversation, outcome, evidence and remaining concern.
- **Completed review evidence**: Actual coverage, baseline chain, reviewed code, verification completeness and completion status.

### Error Handling

Invalid arguments fail before mutations. Missing baseline or comparison evidence selects full scope with an explanation. Missing current review inputs or required reviewer/thread coverage yields an incomplete result without a completed baseline. Stale prepared actions are withheld individually. Remote failures retain independent usable results and idempotent recovery state. No missing evidence proves a fix or unchanged contribution.

## Success Criteria

### Measurable Outcomes

- **SC-001**: All recorded single/bulk mode scenarios choose the same mode and personal baseline under equal evidence and overrides.
- **SC-002**: Every fix-only follow-up includes all changed content in review scope and verifies all known unresolved personal findings.
- **SC-003**: Fixed, partial, still-present, moved and unclear fixtures produce zero unsupported resolutions and zero duplicate thread actions on repeated runs.
- **SC-004**: Pure-rebase fixtures create zero unnecessary code reviews; mixed/conflict changes remain reviewable, and renewed requests receive acknowledgment.
- **SC-005**: Every incomplete-history/coverage fixture reports fallback or incompleteness and creates zero unsupported completed baselines.
- **SC-006**: Existing review, triage, inbox and adapter checks continue passing; documented examples cover both modes and their limitations.

## Assumptions

- Existing GitHub authentication and permissions remain in use; remote content is untrusted.
- Baseline persistence is evidence, not permission to post or resolve.
- Retain existing local non-PR review behavior and existing unattended policy.
- New public configuration for borrowing another person's baseline is out of scope.
- Detailed comparison, persistence and verification contracts belong in planning.
