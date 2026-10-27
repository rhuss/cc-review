# Brainstorm: Aligning Inbox Suggestions with PR Actions

**Date:** 2026-10-27
**Status:** active
**Issue:** https://github.com/rhuss/cc-review/issues/7

## Problem Framing

`inbox` ([#07](07-repository-inbox.md)) and the bulk commands ([#06](06-bulk-review-triage.md)) each decide on their own which PRs need the user. They disagree, so a PR the inbox points at may never be picked up by the command it suggests.

Observed on NVIDIA/OpenShell (2026-10-27):

- The inbox listed PRs by other authors where the author had replied to the user's cc-review threads and pushed follow-up commits (#4830, #4789). The natural next step is the reviewer side of triage: verify each claimed fix and confirm or reopen the thread. Single-PR `triage --pr <n>` already does this in Step 11b (cc-review thread management), and the user has used it that way before (#3338, #2931 carry `<!-- cc-review-triage -->` confirmations).
- `triage --bulk` selected nothing. `bulk-select.sh triage` only considers the user's own open PRs with unresolved threads. All four of the user's PRs were excluded with `no-open-threads`, and PRs by others are never candidates.
- A dry run of `bulk-select.sh review` selected #2931 (current review request), #4830 and #3338 (new commits since the user's cc-review review), and excluded #4789 as a draft. For #4830 that means a full multi-agent review when the user only needs to check that the author's replies hold. #3338 was only rebased after the user's second pass verified every finding, so a re-review there is likely wasted. #4789, the clearest reviewer follow-up, is not reachable by either bulk command.

The asymmetry has three parts:

1. **Roles.** Single-PR triage serves two roles: author (bot and human threads on my PR) and reviewer (author replies to my cc-review threads, Step 11b). Bulk triage only knows the author role.
2. **Vocabulary.** The inbox spec only defines "suggest triage" for the user's own PR with unresolved feedback. For reviewer follow-ups it says "possible follow-up review", which maps to the heavier command. In practice the inbox report also stretched this and suggested triage for other people's PRs, a command form bulk mode cannot reach.
3. **Selection logic.** Inbox relevance (`inbox.py` searches plus model judgment) and bulk selection (`bulk-select.sh` queries) are separate code paths with no shared definition of "this PR needs review / triage from you".

The intended workflow is: check the inbox, see which PRs need triage or review, then run the corresponding command. Triage continues an existing review conversation, including a focused code check of requested fixes. Review covers a first review or additional changes that warrant a further review. A PR can need both.

## Approaches Considered

### A: Shared PR action assessment (chosen)

Inbox and bulk commands share the assessment of which PR actions are available, with evidence for each action. Extend bulk triage to cover the reviewer role as well as the author role. Review and triage are independent actions, so the same PR can qualify for both.

- Pros: directly aligns the inbox with the commands it recommends; closes the reviewer triage gap; gives both workflows consistent reasons and exclusions.
- Cons: affects both existing selectors; needs a clear boundary between checking earlier findings and reviewing additional changes; requires coordination when both commands handle the same threads.

### B: Extend bulk triage only

Add reviewer follow-ups to bulk triage while leaving inbox assessment and bulk selection separate.

- Pros: closes the immediate gap with a smaller change; builds on existing thread verification.
- Cons: inbox and bulk decisions can still drift; does not establish a common selection contract.

### C: Explicit inbox handoff

Let the user pass the inbox's PR lists directly to the bulk commands. Reviewer triage support is still needed for other authors' PRs.

- Pros: predictable handoff for explicitly selected PRs; useful beyond the inbox.
- Cons: default bulk selection remains inconsistent; adds a selection step and does not resolve the underlying action definitions.

Narrowing inbox wording to the existing selectors was also considered in the initial idea. It would preserve the missing reviewer triage path and suggest unnecessarily broad reviews.

## Decision

Choose Approach A: a shared PR action assessment used by inbox and bulk selection, with reviewer follow-ups supported in bulk triage.

The user confirmed:

- The immediate scope is PR workflows. Other inbox suggestions may be explored later if the action model proves useful for them.
- The desired flow starts with the inbox and continues through triage or review.
- Triage can include focused verification of code changed to address earlier findings.
- A PR requiring both existing findings checked and substantial additional changes reviewed belongs in both action categories. Neither action takes precedence merely because both apply.
- [#09: Incremental Review](09-incremental-review.md) remains a separate, connected brainstorm. This document defines action selection; #09 explores how follow-up review examines changed code and verifies earlier findings.

### Action boundaries

| Situation | Action |
|-----------|--------|
| A first review is requested | Review |
| The user's own PR has unresolved feedback requiring attention | Triage as author |
| Another author replies to the user's earlier findings or makes changes requiring fix verification | Triage as reviewer |
| Additional changes after an earlier review warrant further examination | Review, using the follow-up behavior explored in #09 |
| Earlier findings need attention and additional changes warrant review | Both triage and review |
| A rebase changes the head without changing the author's contribution | No re-review solely because the head moved; assess any thread work independently |

The criteria for distinguishing requested fixes from additional review work remain a spec question. Uncertainty must be visible rather than presented as a confident action decision.

## Key Requirements

### Shared PR action assessment

- Assess review and triage independently, retaining evidence and the user's author or reviewer role for each applicable action.
- Use the same PR action definitions for inbox suggestions and bulk selection. Inbox relevance and conversational interpretation remain broader than the command selection rules.
- For the same user, repository, evidence snapshot and effective filters, every suggested action must correspond to eligibility in the matching bulk command.
- Explain differences caused by drafts, limits, filters, changed PR state or incomplete evidence. A suggestion must not imply that a normal bulk run will select a PR that it silently excludes.
- Distinguish explicit review requests, replies requiring attention, code changes and inferred obligations. A new head commit alone does not prove that substantial re-review is needed.

### Triage in both roles

- A normal bulk triage run can cover feedback on the user's own PRs and follow-ups on the user's earlier reviews of other authors' PRs. Make the role clear in the consolidated decision table.
- Reviewer triage covers at least the user's unresolved cc-review threads, including author replies, fix claims and questions directed at the user.
- Verify requested fixes against the current code. Record whether the finding is addressed, still present or unclear; resolve a fix only after verification. Preserve disagreements and questions for the user's decision where needed.
- Reviewer triage prepares thread responses and resolutions without making fix commits or pushing to another author's PR branch. Preserve the existing deferred decision flow before applying prepared actions.
- Already handled activity does not repeatedly create work, while a later reply or relevant code change can require fresh assessment.

### Review and overlapping work

- Review handles first reviews and further examination of changed code. Detailed incremental scope, baseline choice, rebase handling and invocation belong to #09.
- Triage's focused fix verification does not by itself satisfy an outstanding review of additional changes.
- When both actions apply, include the PR in both action categories and matching bulk selections; retain one underlying PR identity.
- Either execution order must avoid duplicate replies and resolutions for already handled thread activity. Reassess against the latest thread and code state before applying an action.
- Follow-up review may also verify earlier findings, using behavior consistent with triage. Absence of a finding from a later review is not sufficient evidence that it was fixed; #09 addresses the existing resolution heuristic.

### Inbox presentation and scope

- Explain each suggested PR action, link to its evidence and name the command form that can perform it.
- Show both actions when both apply. Keep the distinction between an item's attention group and its review or triage actions.
- Keep inbox read-only; the user invokes review or triage separately.
- This brainstorm covers PR suggestions and selection. Extending action assessment to issues or Discussions, an explicit PR-list handoff and optional role filters are possible follow-ups rather than requirements for this feature.

### Success criteria

- Representative PR snapshots produce consistent inbox suggestions and bulk eligibility, with visible reasons for every exception.
- Reviewer follow-ups that were previously unreachable through bulk triage become selectable and produce the appropriate thread actions.
- A PR with both kinds of work appears in both action categories; completing either action preserves any remaining work and causes no duplicate thread posts.
- Rebase-only changes do not create a substantial re-review obligation on their own.

## Open Questions

- What evidence establishes ownership of an earlier review thread, and should manual review threads be included alongside cc-review threads in the first version?
- Should relevant code changes without an author reply trigger reviewer triage, and how should already assessed but unresolved threads be reconsidered?
- What evidence distinguishes requested fixes from additional changes warranting review, and how should uncertain cases map consistently to inbox and bulk selection?
- Should reviewer triage include draft PRs by default, even if first reviews exclude them? How should inbox expose each action's effective filters and exclusions?
- How should review and triage recognize verification already performed at the same code and conversation state while preserving a separate outstanding review obligation?
- What shared evidence contract can inbox and bulk selection use without turning the inbox into a full review? The helper or snapshot format belongs in planning.
- What sequencing lets #08 establish useful alignment before #09's incremental review behavior is available, and which behavior requires both features?
