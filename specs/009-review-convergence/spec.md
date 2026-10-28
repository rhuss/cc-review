# Feature Specification: Review Convergence

**Feature Branch**: `009-review-convergence`
**Created**: 2026-10-28
**Status**: Draft
**Input**: Agreed brainstorm `brainstorm/10-review-convergence.md`; tracking issue https://github.com/rhuss/cc-review/issues/11.

## Overview

Follow-up reviews remember earlier discussion, verify substantive concerns and report material new problems. They can conclude with sufficient confidence to merge without finding optional improvements indefinitely. Conversation history and completed code coverage are independent: manual reviews establish context, not an incremental baseline.

## Clarifications

### Session 2026-10-28

Smart oversight selected conservative recommended defaults during the clarify stage:

- Q: Does a manual review without a baseline establish follow-up behavior? → A: Yes for conversation and materiality only; code coverage still uses the existing full fallback.
- Q: Does an acknowledged deferral clear a material concern? → A: No; retain the actual material concern without a duplicate. Only verified fixes or approved accepted explanations clear it.
- Q: Can arbitrary issue comments alone establish personal review history? → A: Only an explicitly attributable review finding can; preserve other comments as contextual evidence, never infer a review from casual participation.
- Q: How do severity labels affect materiality? → A: New follow-up findings need concrete material consequences and Critical/Important severity after calibration. Correct a demonstrably wrong label using evidence rather than elevating optional polish.
- Q: What happens when relevant history or assessment is incomplete? → A: Keep the review visibly incomplete for a clean convergence conclusion; do not clear concerns or claim confidence from missing evidence.

## User Scenarios & Testing

### User Story 1 - Continue the conversation (Priority: P1)

As a reviewer, I want earlier findings, author replies and decisions to inform the next round so I do not repeat answered concerns or silently contradict my earlier advice.

**Why this priority**: Duplicate or contradictory advice directly prevents convergence.
**Independent Test**: Supply earlier manual and cc-review inline and summary findings, author replies and a current assessment; verify references and continuation decisions survive through reporting.

**Acceptance Scenarios**:

1. **Given** an earlier finding with an unanswered author question, **When** reviewing again, **Then** address that question in its conversation rather than creating a duplicate demand.
2. **Given** an author explanation or promised fix, **When** assessing the concern, **Then** inspect current code; neither a reply nor a promise alone proves resolution.
3. **Given** a change made at my request, **When** new evidence warrants reversing that advice, **Then** identify the earlier advice and explain the reversal before proposing it.
4. **Given** summary-only feedback or a relevant resolved thread, **When** reviewing again, **Then** retain it as context alongside inline findings without reopening it solely because it exists.

### User Story 2 - Finish a substantive review (Priority: P1)

As a reviewer, I want follow-ups to report consequential problems and stop once substantive concerns are addressed, while still catching regressions.

**Why this priority**: Optional polish must not create endless rounds.
**Independent Test**: Assess fixed material concerns, new regressions, optional suggestions and incomplete verification; only the fully evidenced clean case receives the clean conclusion.

**Acceptance Scenarios**:

1. **Given** verified substantive fixes and only optional polish remaining, **When** the follow-up completes, **Then** conclude "no outstanding material concerns" without requiring those suggestions to be implemented.
2. **Given** a material regression in a requested fix, **When** reviewing its delta, **Then** report it even after many previous rounds.
3. **Given** unchanged code, **When** considering a new finding, **Then** retain the existing concrete-evidence Critical-only exception.
4. **Given** zero valid new findings, **When** completing review, **Then** do not expand the search merely to find something.

### User Story 3 - Consistent and honest follow-up outcomes (Priority: P2)

As a user, I want the same behavior across single and bulk reviews, full fallbacks and explicit full reassessments, with uncertainty visible.

**Why this priority**: Changing execution mode must not reset the conversation.
**Independent Test**: Run equivalent normalized histories and assessments through each workflow, including missing history and command-tool candidates.

**Acceptance Scenarios**:

1. **Given** only an earlier personal manual review, **When** no completed baseline exists, **Then** perform the required full scope with follow-up conversation and materiality rules.
2. **Given** a follow-up using `--full` or a full fallback, **When** dispatching reviewers and deciding findings, **Then** retain history and the follow-up reporting policy.
3. **Given** incomplete history, unresolved substantive questions or failed required coverage, **When** finishing, **Then** report limitations instead of an unsupported clean conclusion.

### Edge Cases and Error Handling

- Empty but completely fetched personal history is an initial review; collection failure with no visible prior reviews is uncertain, not proof of a first review.
- Reviews by other people do not establish a personal follow-up or code baseline. Their replies inside relevant personal conversations remain context.
- Resolved or deferred concerns are not automatically reopened. New material evidence can justify revisiting an earlier decision with an explanation.
- History truncation, failed pagination, malformed identities and changed conversations must be visible and cannot support a clean conclusion.
- Summary replies can be ambiguous. Keep source references and uncertainty; never infer an exact reply relationship from proximity alone.
- A completed assessment may still report unresolved material concerns. Completion is distinct from a clean conclusion, hosting approval and merge authorization.

## Requirements

### Functional Requirements

- **FR-001**: Recognize follow-up context from earlier submitted reviews or attributable review findings by the authenticated user, independent of incremental-baseline eligibility; exclude pending drafts and foreign reviewers as personal-history evidence.
- **FR-002**: Collect personal manual and cc-review summaries, inline conversations, relevant resolved discussions, author replies and replies to summary-only feedback, retaining exact source references and authorship.
- **FR-003**: Disclose incomplete or bounded history and retain source identity; uncertain associations must remain explicitly uncertain.
- **FR-004**: Supply relevant prior discussion to prompt reviewers, merge, meta-review and decision/report stages before assessment; command-tool output is subject to the same final continuity policy.
- **FR-005**: Classify candidates as new, duplicate-of, already-answered or contradicts-earlier-advice using meaning and code evidence, never path/line similarity alone.
- **FR-006**: Assess explanations and promised fixes against current code. Distinguish accepted explanations/deferrals from unaccepted claims; preserve existing approval rules for acceptance and thread actions.
- **FR-007**: Continue existing concerns in their conversations and show links, avoiding new duplicate comments. Unanswered substantive questions must be addressed or reported unresolved.
- **FR-008**: Explain any proposed reversal of earlier advice using concrete current evidence and the original source; do not silently ask authors to undo compliance.
- **FR-009**: Report new follow-up findings only for concrete consequential defects or regressions; suppress optional polish, speculative improvements and preferences even in changed code.
- **FR-010**: Keep earlier minor suggestions nonblocking and outside mandatory fixes for convergence; a promise alone cannot clear an actual material concern.
- **FR-011**: Review the entire author delta including fixes; preserve the evidence-backed Critical-only unchanged-code exception and existing full-review scope semantics.
- **FR-012**: Permit a clean result without a finding quota or a zero-findings-triggered expansion of review scope; retain evidence requirements for real material problems at every round.
- **FR-013**: Conclude "no outstanding material concerns" only with complete relevant history, required review coverage and explicit verification, no outstanding material concerns and no unresolved substantive questions.
- **FR-014**: Distinguish addressed concerns, existing open material concerns, new material findings, nonblocking prior suggestions and limitations in reports and posting decisions, including empty findings.
- **FR-015**: Apply the same behavior to single and bulk follow-ups, full fallback and `--full`, preserving conversation awareness independently of code-scope mode.
- **FR-016**: Retain history and continuity decisions through merge, calibration and fix rounds; reassess against final code and refresh or withhold stale thread actions before publication.
- **FR-017**: Preserve personal baseline semantics, review/triage independence, posting permissions, user approval steps and worktree restrictions. No automatic approval or merge follows from a clean conclusion.
- **FR-018**: Preserve initial-review behavior outside removal of the contradictory global finding quota; add no new command, mode or fixed round limit.
- **FR-019**: Provide executable regression coverage for history collection, continuity decisions, materiality, clean-result conditions and workflow wiring, plus user documentation.

### Key Entities

- **Review history**: Personal-review evidence, source conversations and comments, collection completeness, follow-up classification and limitations. It is not completed code coverage.
- **Prior concern assessment**: Source reference, current code evidence, materiality, status, substantive-question state and proposed continuation/reversal. Existing verification and approval remain authoritative for resolution.
- **Candidate decision**: Relation to prior discussion, reference, code-backed rationale and materiality of a current candidate; it does not establish thread identity by itself.
- **Convergence conclusion**: Reviewed result that is clean, has outstanding material concerns, is incomplete or is an initial review with unchanged behavior.

## Success Criteria

### Measurable Outcomes

- **SC-001**: All four observed #11 cases have regression scenarios that preserve source context and avoid duplicate or unexplained contradictory new advice.
- **SC-002**: The complete fixed-plus-optional-polish scenario concludes cleanly; incomplete evidence, a material regression or an unresolved substantive question never does.
- **SC-003**: Personal manual review and summary-only scenarios receive follow-up behavior without establishing a new code-coverage baseline.
- **SC-004**: Single, bulk, full fallback and `--full` dispatch and final reporting receive equivalent continuity inputs and policy.
- **SC-005**: Existing incremental scope, verification, approval and posting regression tests remain passing alongside new semantic tests.

## Assumptions and Boundaries

- Reuse the authenticated identity and GitHub read mechanisms. No new service, account or hosting permission is required.
- Materiality depends on concrete consequences, not a finding quota. New follow-up findings require Critical/Important severity after calibration and concrete impact evidence; Minor/Notable suggestions cannot become blockers by repetition. A demonstrably wrong label can be reassessed from evidence. A deferred material concern remains outstanding until verified fixed or cleared by an approved accepted explanation.
- Automatic extraction cannot reliably infer whether arbitrary prose is a finding, reply or agreement. Preserve conversations for code-backed semantic assessment rather than treating text patterns as decisions.
- Existing issue #11 tracks implementation. Changes to initial-review feature scope, triage ownership and upstream inbox selection are outside this feature.
