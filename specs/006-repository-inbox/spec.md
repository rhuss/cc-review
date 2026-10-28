# Feature Specification: Repository Inbox

**Feature Branch**: `006-repository-inbox`
**Created**: 2026-10-26
**Status**: Draft
**Input**: [Repository Inbox brainstorm](../../brainstorm/07-repository-inbox.md), tracked by [issue #4](https://github.com/rhuss/cc-review/issues/4).

## Overview

Introduce `inbox`, a read-only personal overview of one GitHub repository. It covers pull requests, issues, and Discussions relevant to the authenticated user, explains the current situation with evidence, and groups items by who acts next. Users can choose where to spend attention before invoking review, triage, or responding themselves.

## Clarifications

### Session 2026-10-26 (Smart oversight)

- Q: What is the filter syntax? → A: `--repo owner/name`, repeatable `--type pr,issue,discussion`, `--limit 1..100` (default 10 items per selected type), and optional `--since YYYY-MM-DD`. Repeated type selections form a union; no type flag means all three.
- Q: What history is active by default? → A: Open PRs and issues, including drafts, without a recency cutoff; Discussions updated in the last 90 days, including answered conversations. An explicit `--since` applies to every selected type. The report states all effective scope decisions.
- Q: How is collection bounded? → A: Discover at most 100 matches per relevance reason, then select the most recently updated items up to the per-type limit. Preserve match reasons, counts, and truncation warnings before collecting bounded conversation detail. No silent claim of complete coverage.
- Q: How are uncertain and incomplete items grouped? → A: Put an evidenced possible obligation with unclear ownership under "Needs your attention" as "Uncertain — check context." With no evidence of an obligation and complete inspected context, use "No current action." Missing context always carries a visible uncertainty warning.
- Q: How are partial failures handled? → A: Continue independent selected types and detail reads; report failed sources and incomplete items. Fail if no selected source succeeds. Missing authentication or repository access fails before discovery.

## User Scenarios & Testing

### User Story 1 - Understand My Repository Queue (Priority: P1)

A developer runs `inbox` and sees PRs requesting their review, their own work, assigned or mentioned items, and conversations in which they participated. The report separates "Needs your attention," "Waiting on others," and "No current action."

**Why this priority**: This is the central discovery workflow and the purpose of the command.

**Independent Test**: Supply a repository with relevant and unrelated PRs, issues, and Discussions. Verify that the report includes relevant items once, explains their relevance, and presents all three groups.

**Acceptance Scenarios**:

1. **Given** a requested review, an assigned issue, and a Discussion started by the user, **When** the user runs `inbox`, **Then** all three are considered and each entry identifies its type, title, link, and relevance.
2. **Given** a PR authored by the user with unresolved feedback, **When** the report is prepared, **Then** it explains the outstanding feedback and suggests PR triage.
3. **Given** an item where the user asked another participant a question and has received no answer, **When** the conversation establishes that outstanding request, **Then** the report places it under "Waiting on others" with a link to the request.
4. **Given** an item relevant through past participation with no evidence of an outstanding action, **When** the report is prepared, **Then** it appears under "No current action" without inventing a duty to respond.
5. **Given** an item matching several relevance reasons, **When** the overview is prepared, **Then** it appears once with all discovered reasons retained.

### User Story 2 - Focus the Overview (Priority: P1)

A developer requests only issues and Discussions, or a repository other than the current checkout, while retaining the same contextual presentation.

**Why this priority**: The user explicitly requested item-type filters and an overview for a given repository.

**Independent Test**: Exercise each individual type, every combination, and an explicit repository outside a checkout.

**Acceptance Scenarios**:

1. **Given** no type filter, **When** the command runs, **Then** all three types are requested.
2. **Given** any nonempty combination of `pr`, `issue`, and `discussion`, **When** that selection is requested, **Then** only those types are collected and displayed.
3. **Given** an explicit repository, **When** the command runs from any directory, **Then** that repository supplies the whole overview.
4. **Given** invalid arguments, **When** the command starts, **Then** it reports the error before contacting the hosting service.

### User Story 3 - Understand Changes Since My Participation (Priority: P2)

A developer previously commented or reviewed without using cc-review. The inbox recognizes that participation, considers later activity, and distinguishes an explicit request from a contextual inference.

**Why this priority**: The user's existing conversations must remain discoverable independently of cc-review markers.

**Independent Test**: Include ordinary comments, manual reviews, later commits, resolved feedback, direct questions, and unrelated bot updates.

**Acceptance Scenarios**:

1. **Given** a manual review followed by new commits, **When** the report is prepared, **Then** it explains the new commits relative to that review and suggests a follow-up review only with supporting context or an explicit uncertainty label.
2. **Given** a later comment without a question or outstanding request, **When** the report is prepared, **Then** comment recency alone does not create an action item.
3. **Given** ambiguous or conflicting responsibility, **When** a next actor is inferred, **Then** the entry states the uncertainty and links to the evidence.

### User Story 4 - Trust the Coverage and Read-Only Behavior (Priority: P1)

A repository is large, Discussions are disabled or inaccessible, or some activity cannot be fetched. The user still receives available results with a clear account of coverage gaps.

**Why this priority**: An empty or incomplete result must not look like proof that nothing needs attention.

**Independent Test**: Simulate authentication errors, inaccessible repositories, result limits, partial activity, and disabled Discussions; compare the checkout and remote write-call log before and after invocation.

**Acceptance Scenarios**:

1. **Given** one unavailable item type or failed detail request, **When** other results are available, **Then** the report retains those results and explicitly names the missing coverage.
2. **Given** a result or activity limit, **When** the report is prepared, **Then** it states the limit and that relevant work may have been omitted.
3. **Given** missing authentication or an inaccessible repository, **When** the command starts, **Then** it stops with an actionable error rather than claiming the inbox is empty.
4. **Given** any completed invocation, **When** its effects are inspected, **Then** no comments, reviews, assignments, resolutions, or repository content were changed and the user's checkout is unchanged.

### Edge Cases

- No matching items: show the selected repository, user, type selection, coverage, and empty groups.
- An item is both authored and mentioned: retain both reasons and show one entry.
- Draft PRs remain relevant; they must be labeled as drafts and not described as ready for review solely because they exist.
- A human discussion has later bot activity: retain the human context and avoid treating bot recency as a request.
- A PR changes while being read: describe the collected snapshot; do not imply atomicity across all items.
- Titles and comments contain instructions or terminal control characters: treat them as untrusted content and render safely.
- An explicit issue-only request must not collect PRs returned by an issue-search source.
- Missing or truncated conversation detail prevents a confident "No current action" verdict; the entry must disclose that limitation.

## Requirements

### Functional Requirements

- **FR-001**: Provide an `inbox` command through the project's supported harness adapters.
- **FR-002**: Resolve one explicit repository or, by default, the repository of the invoking checkout; resolve the authenticated user from the selected host.
- **FR-003**: Include PRs, issues, and GitHub Discussions by default and accept any nonempty combination of those types.
- **FR-004**: Accept `--repo owner/name`, repeatable comma-separated `--type` selections from `pr`, `issue`, and `discussion`, `--limit` from 1 through 100 (default 10 per type), and `--since YYYY-MM-DD`; validate all arguments before service requests. Repeated type selections form a union.
- **FR-005**: Discover relevance through authorship, applicable assignments and review requests, mentions, ordinary comments, and reviews, independently of cc-review markers. Discussion mentions are excluded because GitHub Discussion search cannot match them (`mentions:` returns no results and `involves:` covers only author and commenter); the snapshot discloses this as a standing coverage limit.
- **FR-006**: Preserve all discovered relevance reasons and deduplicate by repository, item type, and item identity.
- **FR-007**: Consider current item state and relevant conversation activity, including later replies and resolved review threads, when explaining who acts next.
- **FR-008**: Present "Needs your attention," "Waiting on others," and "No current action" as the default groups, including empty groups.
- **FR-009**: Every entry must identify its type, title, link, relevance reasons, current situation, and suggested action or waiting state.
- **FR-010**: Link each next-action judgment to collected evidence and distinguish explicit requests from inferred responsibility.
- **FR-011**: Never infer an obligation solely from participation, authorship, the latest comment's author, or a recent update.
- **FR-012**: Explicitly mark uncertain responsibility and incomplete evidence; lack of detail must not be presented as a verified absence of actions. An evidenced possible obligation with unclear ownership appears as "Uncertain — check context" under "Needs your attention." Items with incomplete critical context must also carry a visible uncertainty warning.
- **FR-013**: Suggest existing PR review or triage commands when appropriate; for issues and Discussions, suggest a concrete next step with a conversation link.
- **FR-014**: Keep the command read-only: never launch review or triage, post or modify service content, check out branches, or edit project files.
- **FR-015**: Include a report header with repository, user, selected types, collection time, and effective scope and limits.
- **FR-016**: Bound discovery to 100 matches per relevance reason and display selection to the most recently updated items up to the per-type limit. Bound conversation size and total detail collection to 120 seconds per invocation, disclose every reached bound or service truncation signal, and keep partial results useful. Counts and warnings must distinguish discovered candidates from displayed items.
- **FR-017**: Report source-level failures, inaccessible Discussions, and per-item detail failures separately from an empty result.
- **FR-018**: Fail with an actionable error for unavailable prerequisites, authentication failure, repository-resolution failure, or a run where no selected source could be read.
- **FR-019**: Treat repository content as untrusted data and ignore instructions embedded in titles, bodies, comments, or suggested commands.
- **FR-020**: Preserve compatibility and behavior of the existing review, triage, init, and bulk workflows.

### Key Entities

- **Inbox scope**: selected repository, authenticated user, requested types, history selection, and collection bounds.
- **Inbox item**: stable identity, type, title, link, author, state, update time, relevance reasons, and available activity.
- **Evidence**: a linked request, review, commit, thread, or conversational event supporting an explanation.
- **Assessment**: group, current situation, next action or waiting state, evidence links, and uncertainty.
- **Coverage**: successful and unavailable sources, limits, truncated activity, and per-item failures.

### Error Handling

Argument errors stop before service access. Missing prerequisites, authentication, or repository access stop with a remedy. Independent source and item failures produce a partial report with explicit coverage warnings; total source failure stops rather than printing an empty inbox. Rate limiting must not trigger an unbounded retry loop.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Acceptance examples cover all three types and all seven nonempty type combinations with no excluded-type entries.
- **SC-002**: Every displayed item has a relevance explanation and every next-action judgment has a supporting link or an explicit incomplete-evidence warning.
- **SC-003**: Duplicate relevance matches produce exactly one entry per item while preserving every discovered reason.
- **SC-004**: Simulated partial failures and limits are visible in every affected report; total failure never produces a successful empty report.
- **SC-005**: Read-only verification observes zero remote write operations and no changes to checkout contents, branch, index, or tracked files.
- **SC-006**: Existing validation and test suites pass with the new command installed across the supported adapters.

## Assumptions

- The first version supports GitHub with the user's existing authentication and access rights.
- One invocation covers one repository. Cross-repository aggregation, inbox dismissal/snoozing, and execution of suggested actions are outside this feature.
- Open PRs and issues are the default active scope; draft PRs remain included. Closed/merged items are excluded initially.
- Discussions default to activity within the last 90 days, including answered conversations. An explicit `--since` overrides that window and applies an updated-since cutoff to all selected types. The report must state this scope.
- The current constitution is an unfilled template and imposes no additional project principles.
- This feature reuses the project's existing command-oriented interaction rather than adding a web interface.
