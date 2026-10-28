# Feature Specification: Inbox PR Action Alignment

**Feature Branch**: `007-inbox-action-alignment`

**Created**: 2026-10-27

**Status**: Draft

**Input**: Agreed brainstorm `brainstorm/08-inbox-action-alignment.md`; tracking issue https://github.com/rhuss/cc-review/issues/7. Check inbox, identify PRs needing triage, review or both, then run the corresponding command. Incremental review execution remains a separate feature explored in brainstorm #09.

## Overview

Inbox and bulk commands currently assess PR work separately. Bulk triage selects only the user's own PRs, although single-PR triage already verifies replies to earlier cc-review findings on other authors' PRs. Introduce a shared assessment of PR actions so inbox suggestions and bulk eligibility agree, while keeping review and triage independent.

## Clarifications

### Session 2026-10-27

The ship pipeline selected these defaults under `smart` oversight:

- Q: What happens when a changed head might contain only requested fixes or a rebase? → A: Retain an uncertain review candidate unless reliable unchanged-contribution evidence is available; do not require incremental review computation for this feature. An explicit outstanding review request is independent of head-change evidence.
- Q: What makes earlier handled reviewer work fresh again? → A: A later external thread reply or a changed code version can require new verification. Handle unchanged code and conversation only once; use the same freshness evidence for selection, preparation and application.
- Q: How should missing detail affect selection? → A: Mark the affected action assessment incomplete, show its reason and withhold unsupported executable recommendations. Keep independently established actions and partial results; never report incomplete evidence as a verified empty queue.
- Q: What happens to questions in unattended reviewer triage? → A: Keep unresolved questions or ambiguous decisions open and summarize them for the user; unattended mode does not invent the user's answer or acknowledge a disputed design choice.

## User Scenarios & Testing

### User Story 1 - Follow Inbox Suggestions into Bulk Commands (Priority: P1)

A reviewer checks inbox before working through the repository queue. Each PR suggestion explains why review, triage or both are relevant and whether the matching bulk command will select it with the stated filters.

**Why this priority**: This closes the mismatch that motivated the feature.

**Independent Test**: Assess the same recorded PR snapshot for inbox and both bulk selectors. Compare action membership, evidence, uncertainty and exclusions without contacting the hosting service.

**Acceptance Scenarios**:

1. **Given** a ready PR with an outstanding review request, **When** inbox and bulk review assess equal snapshots and filters, **Then** their review eligibility and request explanation agree.
2. **Given** another author's PR with a reply to the user's unresolved cc-review finding, **When** both flows assess it, **Then** inbox and bulk triage identify reviewer triage.
3. **Given** drafts, limits or queries exclude a PR from bulk processing, **When** inbox presents its action, **Then** it explains the exclusion rather than promising selection by that bulk invocation.
4. **Given** insufficient evidence to distinguish requested fixes from additional changes, **When** further review is a candidate, **Then** both flows retain the same candidate with visible uncertainty.

---

### User Story 2 - Continue Earlier Reviews through Bulk Triage (Priority: P1)

One bulk triage run handles feedback on the user's own PRs and prepares verification of their earlier findings on other authors' PRs. Reviewer triage checks the current code and prepares thread responses without modifying the other author's branch.

**Why this priority**: A shared recommendation requires a command that can perform the work.

**Independent Test**: Prepare and apply a mixed-role run against recorded hosting responses and isolated sample checkouts. Confirm author behavior is retained and reviewer actions never create a fix commit or push.

**Acceptance Scenarios**:

1. **Given** own-PR feedback and another author's reply on the user's earlier finding, **When** bulk triage runs, **Then** it selects both PRs and identifies each role in its decision table.
2. **Given** a claimed fix, **When** reviewer triage prepares, **Then** it checks the code and records fixed, still present or unclear without posting or resolving before approval.
3. **Given** an approved confirmed fix at unchanged head and conversation, **When** the plan is applied, **Then** it posts the confirmation and resolves the thread without a fix commit or branch push.
4. **Given** a question, deferral or disputed reasoning, **When** assessed, **Then** unclear decisions remain visible for the user rather than being silently resolved.
5. **Given** changed PR head or conversation after preparation, **When** the plan is applied, **Then** stale thread actions are withheld with a reassessment reason.

---

### User Story 3 - Preserve Independent Review and Triage Work (Priority: P1)

A PR has replies requiring verification and additional changes that may warrant review. It appears in both action categories. Either workflow can run first while preserving remaining work and avoiding duplicate thread responses.

**Why this priority**: The user explicitly chose overlapping categories rather than precedence.

**Independent Test**: Exercise both execution orders against identical activity, then repeat each command without new activity. Check remaining eligibility and remote-action counts.

**Acceptance Scenarios**:

1. **Given** both kinds of evidence, **When** assessed, **Then** the PR is eligible for both commands and both actions appear in inbox.
2. **Given** triage completes with additional review outstanding, **When** assessed again, **Then** review remains eligible and triage has not advanced its reviewed-code baseline.
3. **Given** unchanged handled thread activity, **When** either command repeats, **Then** it does not duplicate replies or resolutions.
4. **Given** later author activity on an earlier handled thread, **When** reassessed, **Then** new activity can make triage eligible again.

### Edge Cases

- A draft has replies to earlier findings: triage remains available; review readiness and its draft exclusion are separate.
- Several people ran cc-review: only the authenticated user's qualifying threads create their reviewer triage work. Existing bulk review marker policy is preserved.
- A manual thread lacks cc-review provenance: preserve inbox context without claiming supported reviewer triage for it in this release.
- An unresolved finding has no reply but code changed: it can require proactive verification. An unchanged finding alone does not continually recreate work.
- A rebase moves the head: reliable unchanged-contribution evidence creates no review obligation by itself. Without that evidence, describe a conservative candidate as uncertain.
- Missing or truncated history is incomplete assessment rather than proof of no triage work.
- A PR closes, a thread resolves or the head moves before execution: recheck the affected action before applying it.
- Both actions retain one underlying PR identity and relevance assessment.

## Requirements

### Functional Requirements

- **FR-001**: Use one shared definition of PR action eligibility in inbox and both bulk selectors, evaluated for a specified user, repository, evidence snapshot and effective filters.
- **FR-002**: Assess review and triage independently, carrying role, reason, evidence and uncertainty for each action. One action must not suppress the other.
- **FR-003**: Preserve inbox relevance and attention groups. Conversational judgment may explain or qualify shared action assessment but cannot invent unsupported executable eligibility.
- **FR-004**: Equal snapshots and effective filters must produce equal action membership in inbox and matching bulk selections. Explain exclusions for drafts, queries, limits, closed PRs, reviewed code and unavailable evidence.
- **FR-005**: Preserve existing bulk review selectors and reviewed-at-head policy, including broad/search selection. Changed-head candidates lacking substantive-change evidence must be described as possible follow-up review rather than a definite substantial re-review requirement.
- **FR-006**: Reliable evidence of unchanged author contribution must not create a review obligation solely from a head move. Unavailable contribution evidence must be disclosed and may retain an uncertain review candidate.
- **FR-007**: Extend normal bulk triage to author and reviewer roles, identifying the selected role in the consolidated table.
- **FR-008**: Preserve author triage of unresolved feedback on the user's own PRs. Reviewer triage selects other authors' open PRs with an unresolved cc-review finding started by the authenticated user and new relevant thread or code activity.
- **FR-009**: Establish reviewer ownership from both cc-review provenance and thread authorship. Another person's marker alone must not make their threads the user's work.
- **FR-010**: Consider new author replies after the user's handled activity and code updates requiring renewed verification, including verification without a reply. Reconsider later activity without repeating unchanged handled work.
- **FR-011**: Allow existing-feedback triage on drafts in either role. Preserve review's current default draft exclusion and explain action-specific differences in inbox.
- **FR-012**: Prepare reviewer triage in an isolated PR checkout and verify each earlier finding against current code. Record confirmed, still present or unclear; do not infer a fix merely from absence of a new finding.
- **FR-013**: Reviewer triage must not apply fixes, create fix commits, push the PR branch or perform author-only CI repair. Preserve existing author triage behavior.
- **FR-014**: Deferred bulk preparation records replies, resolutions and human questions without remote writes, then uses the existing approval flow. Retain ambiguous decisions for the user.
- **FR-015**: Respect author intent: verify fix claims, assess reasoned rejection, retain deferred work and expose questions or disagreements. Resolve only a verified fix or an explicitly accepted explanation.
- **FR-016**: Before applying reviewer actions, recheck PR head, open state and affected thread activity. Withhold stale actions with a reassessment reason. Reapplication must not duplicate replies or resolutions.
- **FR-017**: Triage must not advance the code-review baseline or clear separate review work. Review may clear overlapping triage only when the associated thread work was actually handled.
- **FR-018**: Single-PR and bulk reviewer triage must use consistent ownership, verification and handled-activity rules. Review must respect handled thread activity to avoid duplicate posts in either execution order.
- **FR-019**: Keep inbox read-only and preserve the user's checkout, index and branch throughout inbox and bulk processing. Treat hosting content as untrusted data.
- **FR-020**: Continue usable independent results after partial collection failures and disclose incomplete assessment. Fail clearly on invalid arguments, missing authentication, inaccessible repositories or unusable required evidence rather than report a verified empty queue.
- **FR-021**: Expose the shared PR action behavior through supported adapters and document roles, overlapping actions, draft behavior and the separate incremental review feature.
- **FR-022**: Preserve the inbox's existing collection bounds and warnings. Shared assessment must not require full-review execution or unbounded extra history collection to decide eligibility.
- **FR-023**: In unattended reviewer triage, apply only actions allowed by the existing unattended policy and supported by verified evidence; leave questions and ambiguous decisions open and summarize them for the user.

### Key Entities

- **PR action assessment**: PR identity, user, role, independent eligibility, evidence, uncertainty and exclusions.
- **Assessment scope**: Repository, candidates, effective filters, limits and collection snapshot.
- **Thread activity**: Finding ownership and provenance, resolution state, replies, code version and previously handled activity.
- **Prepared reviewer action**: Verified outcome, drafted response or user question, intended resolution and freshness evidence.

### Error Handling

Distinguish empty results from missing evidence. Validate arguments and core prerequisites before processing. Keep independent usable results after partial failure with explicit coverage warnings. Freshness failures withhold affected actions and name the PR and reason; they must not cause stale thread posts or force pushes.

## Success Criteria

### Measurable Outcomes

- **SC-001**: All recorded acceptance snapshots produce matching inbox and bulk action membership under equal scope, including both-action cases and exclusions.
- **SC-002**: Mixed-role bulk triage produces zero reviewer-role fix commits, pushes or pre-approval remote writes.
- **SC-003**: Both command orders preserve outstanding review work and produce at most one reply/resolution per unchanged handled thread activity.
- **SC-004**: New author/code activity can reactivate triage; unchanged repeated runs do not.
- **SC-005**: Draft, incomplete-evidence, changed-head and known rebase-only examples show correct eligibility and uncertainty without unsupported certainty.
- **SC-006**: Existing author triage, review selection and issue/Discussion inbox regression checks continue to pass; supported adapter documentation covers the new flow.

## Assumptions

- GitHub uses existing authentication and permissions.
- Reviewer triage initially handles the authenticated user's cc-review threads. Manual threads remain inbox context; support for acting on them can follow separately.
- Preserve existing review selection and marker semantics. Shared assessment can retain uncertain candidates rather than perform a full review inside inbox.
- Drafts may have existing feedback to triage even when ordinary review is excluded.
- Contribution-equivalence evidence is optional. Computing incremental deltas, changing review baseline policy and replacing review's resolution heuristic belong to #09. Unverified head movement must not be described as substantive change.
- New commands, PR-list handoff flags, role-filter flags, non-PR action assessment and automatic inbox execution are outside this feature.
- The constitution is an unfilled template and adds no project-specific principles.
