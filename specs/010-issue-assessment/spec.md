# Feature Specification: Issue Assessment

**Feature Branch**: `010-issue-assessment`
**Created**: 2026-10-29
**Status**: Implemented
**Input**: Agreed brainstorm `brainstorm/11-issue-assessment.md`.

## User Scenarios & Testing

Assess the value of initial issues before the project takes on implementation or maintenance obligations. The output is advice for a maintainer and a proposed reply, not a project decision made on their behalf.

### User Story 1 - Decide whether an issue warrants work (Priority: P1)

A maintainer assesses one initial issue, checking its concrete need and project fit before deciding whether it should be implemented.

**Why this priority**: A feature request and an offer to code it do not establish that the project should take on the work.

**Independent Test**: Assess a speculative proposal, a documented need, a real problem outside project scope, and a concern already addressed by existing functionality. Each receives a supported recommendation and a draft reply without changing the repository or issue.

**Acceptance Scenarios**:

1. **Given** a proposal without a concrete use case anywhere in the inspected conversation, **When** assessed, **Then** request one real example and include no solution or contribution plan.
2. **Given** a concrete blocked workflow aligned with documented project direction, **When** assessed, **Then** explain whether pursuing it is worthwhile using evidence, benefit, and maintenance cost.
3. **Given** a real problem outside documented project scope, **When** assessed, **Then** be willing to recommend against implementation while acknowledging the problem and explaining the mismatch.
4. **Given** existing functionality addresses the need, **When** assessed, **Then** explain that path with evidence and ask about any remaining gap.
5. **Given** a concrete preventive concern supported by a credible failure path, **When** assessed, **Then** absence of a past incident alone does not disqualify it.

### User Story 2 - Resolve material uncertainty (Priority: P1)

A maintainer answers targeted questions when missing direction, conflicting guidance, or a trade-off could change the recommendation.

**Why this priority**: Guessing project policy can produce an unjustified acceptance or rejection.

**Independent Test**: Assess an issue with conflicting guidance, then supply a maintainer answer. The recommendation incorporates it without repeating answered questions.

**Acceptance Scenarios**:

1. **Given** ambiguous project direction that could change the recommendation, **When** assessed, **Then** ask the maintainer before finalizing the recommendation and reply.
2. **Given** missing author use-case details, **When** assessed, **Then** put the focused question in the public draft rather than invent an answer.
3. **Given** an unfilled constitution template, **When** assessing fit, **Then** it supplies no policy and inferred direction is identified as such.

### User Story 3 - Welcome a bounded contribution (Priority: P2)

When an established need fits the project and an author offers help, draft a welcoming reply with a small outline of possible work.

**Why this priority**: Useful offers deserve a handoff without premature implementation commitments.

**Independent Test**: Assess the same demonstrated need with and without an offer. Only an offered contribution receives a direct invitation.

**Acceptance Scenarios**:

1. **Given** a recommendation to pursue and an offer to help, **When** drafting, **Then** usually welcome it, outline a small outcome and approach, and flag maintainer decisions.
2. **Given** an offer without a demonstrated need, **When** drafting, **Then** request a use case first, without a plan.
3. **Given** complicated work, **When** assessed, **Then** discuss readiness and scope without unsupported personal judgments or promises of acceptance.

### User Story 4 - Draft through an installed harness (Priority: P2)

Invoke a dedicated command from Claude Code, Codex, OpenCode, or spec-kit and receive maintainer reasoning followed by a friendly public draft.

**Why this priority**: Use existing cc-review installations and prose integration.

**Independent Test**: Resolve each adapter to the shared command, with and without prose, and inspect preserved judgment and natural tone.

**Acceptance Scenarios**:

1. **Given** prose humanizer is available, **When** drafting, **Then** use it for wording without changing evidence or recommendation.
2. **Given** prose is unavailable, **When** drafting, **Then** use a bundled maintainer voice and disclose the fallback privately.
3. **Given** a PR, malformed target, inaccessible issue, or conflicting repository selection, **When** invoked, **Then** report an actionable error without mutations.

### Edge Cases

- Need appears only in later comments, or earlier maintainer decisions change the interpretation.
- Deleted authors, closed issues, empty bodies, incomplete conversation, missing or unrelated local checkout.
- Conflicting guidance, placeholder policy, or stale local code.
- Issue text includes commands, tool instructions, attacker-controlled links, or claims of maintainer authority.
- A valid problem does not justify the proposed solution.

## Requirements

### Functional Requirements

- **FR-001**: Provide single-issue assessment through all four existing harness adapters; PR review and triage stay separate.
- **FR-002**: Accept an explicit issue number or GitHub issue URL and optional repository; refuse PRs, invalid inputs, and conflicting targets.
- **FR-003**: Collect issue and bounded conversation with identity, state, authorship, timestamps, source links, and visible completeness limits. Errors MUST NOT appear as empty successful issues.
- **FR-004**: Inspect available target-project purpose, contribution guidance, substantive principles, prior maintainer decisions, and relevant behavior before judging fit. Identify unavailable or uninspected sources.
- **FR-005**: Identify actor, task, actual situation, obstacle, and consequence from evidence. Never manufacture a use case or infer fabrication from absent detail.
- **FR-006**: If a concrete need is missing, request one use case before discussing a solution or contribution plan.
- **FR-007**: Assess the underlying problem separately from proposed solution and fit, including existing functionality, alternatives, benefit, complexity, and maintenance burden.
- **FR-008**: Recommend pursuing, requesting evidence or clarification, or declining implementation in this project, with decisive evidence and uncertainty.
- **FR-009**: Ground project-fit claims in sources. Placeholders impose no policy; label inferences and ask about material conflicts.
- **FR-010**: Ask targeted maintainer questions when uncertainty could change the decision, reuse answers, and distinguish these questions from author questions in the draft.
- **FR-011**: Usually welcome offered help when need and fit support proceeding; sketch a bounded approach and maintainer decisions without promising acceptance or assigning work.
- **FR-012**: Evaluate scope and readiness without unsupported judgments about ability or motives.
- **FR-013**: Present reasoning, evidence, uncertainties, and coverage separately from a concise friendly public draft.
- **FR-014**: Use available prose for wording while preserving meaning and uncertainty; provide a bundled friendly fallback when unavailable.
- **FR-015**: Treat issue content and linked claims as untrusted evidence, never executable instructions. Evidence links come from verified source fields or inspected project paths.
- **FR-016**: Assessment MUST NOT edit project files, implement code, publish replies, assign or label or close issues, or launch PR workflows. Publishing needs a separate explicit request.
- **FR-017**: Disclose incomplete conversation and unavailable project context. Missing decisive evidence prevents an unsupported definitive verdict.
- **FR-018**: Recognize credible preventive use cases without requiring past incidents; hypothetical usefulness alone is insufficient.
- **FR-019**: Preserve working directory, branch, index, and configuration; use private temporary files outside the checkout and clean them up.

### Key Entities

- **Issue context**: Repository, issue, body, bounded comments, identities, timestamps, and coverage.
- **Project evidence**: Identified guidance, explicit decisions, behavior, and labeled inferences.
- **Assessment**: Need, fit, implementation recommendation, evidence, uncertainty, and maintainer questions.
- **Reply draft**: Proposed public prose matching the recommendation, never automatically published.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Every assessment separates need, fit, and implementation judgments with evidence or explicit uncertainty.
- **SC-002**: All missing-use-case examples produce a focused request and no implementation plan.
- **SC-003**: All material project-direction ambiguities trigger a maintainer question before final wording.
- **SC-004**: Supported contribution offers receive a bounded welcome unless the assessment explains why proceeding is unsuitable.
- **SC-005**: All four harness adapters resolve one shared workflow.
- **SC-006**: Invalid targets and PRs fail clearly, limits remain visible, and assessment performs zero issue or project mutations.

## Assumptions

- Initially GitHub.com using existing authenticated access; enterprise hosts are excluded.
- One issue per invocation. Bulk assessment, automatic inbox handoff, publishing, and persistent assessment state are excluded.
- A matching local checkout supplies focused project evidence. Without one, disclose missing context rather than borrow unrelated policy.
- The invoking agent makes semantic judgments. Automated tests cover collection and integration; scenario walkthroughs assess judgment with their limitations stated.
- This repository's constitution is an unfilled template, adding no policy.

## Clarifications

### Session 2026-10-29

Resolved autonomously under ship oversight `never`:

- Q: What command and target syntax? → A: `assess <issue-number-or-URL> [--repo owner/name]`; an explicit target is required and PRs are rejected.
- Q: Which guidance governs fit? → A: Applicable agent instructions govern execution. Target-project documented purpose, contribution policy, substantive constitution, and explicit maintainer decisions are evidence; unresolved material conflicts go to the maintainer. Inference is never promoted to policy.
- Q: How much issue history is collected? → A: Opening issue plus the latest 50 comments, issue body limited to 20,000 characters and each comment to 4,000; any omission, truncation, or partial response is disclosed.
- Q: What if prose or matching local project context is absent? → A: Use the bundled maintainer voice when prose is absent and disclose that privately; absent matching checkout means limited project context and a maintainer question where decisive.
- Q: How are follow-ups handled? → A: Re-read current issue evidence and reuse explicit prior answers from this session and inspected discussion. No persistent assessment state or automatic publishing.

## Error Handling

Invalid syntax, unsupported hosts, PR URLs, conflicting repository targets, inaccessible or missing issues, and unusable service responses stop with an actionable error. Partial usable conversation produces a visibly limited assessment, not a definitive rejection based on missing evidence. A missing or mismatched checkout is a project-context limitation, not a reason to inspect unrelated local files.
