# Brainstorm: Repository Inbox

**Date:** 2026-10-26
**Status:** active
**Issue:** https://github.com/rhuss/cc-review/issues/4

## Problem Framing

A developer needs to answer "what needs my attention in this repository?" before deciding which item to review, triage, or respond to. Relevant work includes PRs requesting their review, PRs they have already commented on or reviewed, their own PRs, assigned or mentioned issues, and Discussions they started or participated in.

The existing `review` and `triage` commands act on selected PRs, including bulk selections. They do not provide a personal overview across PRs, issues, and GitHub Discussions. Bulk review already finds requested reviews and older cc-review reviews; bulk triage finds the user's own PRs with unresolved review threads. Those selections cover part of the need, but participation also includes ordinary comments and reviews made outside cc-review.

Being involved does not necessarily mean the user currently needs to act. The overview should explain the situation and distinguish the user's next action from waiting on someone else. It should also retain relevant items with no current action so the user can understand where things stand.

This is a separate brainstorm from [#06: Bulk Review and Bulk Triage](06-bulk-review-triage.md), as explicitly chosen by the user.

## Approaches Considered

### A: Contextual overview (chosen)

Read relevant activity and explain why each item matters, who appears to act next, and a suggested next step, with supporting links and explicit uncertainty.

- Pros: answers the user's actual prioritization question; distinguishes participation from responsibility; covers PRs, issues, and Discussions in one report.
- Cons: requires more context than metadata queries; next-action judgments can be ambiguous and must be explained.

### B: Query dashboard

List items under metadata categories such as "Review requested," "Assigned to me," "Authored by me," and "Participated in."

- Pros: predictable, inexpensive, easy to understand.
- Cons: leaves the user to read conversations and work out who needs to act; overlapping categories can repeat the same work.

### C: Interactive inbox

Provide the contextual overview and let the user select entries to launch review, triage, or response workflows.

- Pros: connects discovery directly to doing the work.
- Cons: expands the command into execution and response management; issues and Discussions need flows beyond the existing PR commands.

## Decision

Introduce a new command named `inbox`, using Approach A: a read-only contextual overview of the user's relevant work in one repository.

The user chose:

- A separate brainstorm document.
- Coverage of PRs, issues, and GitHub Discussions, with filters for any individual type or combination.
- All relevant items grouped by who acts next, rather than only immediate action items.
- The contextual overview approach.
- The name `inbox`, over `overview` and `status`.

The report groups items into "Needs your attention," "Waiting on others," and "No current action." Each entry explains its relevance and suggested next step using evidence from activity and state. Ambiguous responsibility is explicitly marked as uncertain.

This is one focused discovery feature. Review, triage, posting replies, editing code, and merging remain separate user-invoked actions.

## Key Requirements

### Repository and item scope

- Cover one repository per invocation.
- Cover PRs, issues, and GitHub Discussions as first-class item types.
- Default to all three types; support filtering to any single type or combination.
- Working assumption proposed during the session: use the current repository by default and allow an explicit repository argument. Exact syntax belongs in the spec.
- Initial platform assumption: GitHub, consistent with the current review and triage workflows.

### Personal relevance

- Include items authored or started by the user.
- Include review requests, assignments, and mentions where applicable to the item type.
- Include items where the user previously commented or reviewed, including participation outside cc-review.
- Explain why each item appears; several relevance reasons may apply to one item.
- An item matching several reasons should appear once with those reasons preserved.
- Separate personal relevance from whether the user currently has an action to take.

### Context and grouping

- Present the three agreed groups: "Needs your attention," "Waiting on others," and "No current action."
- Consider conversation context and current state when suggesting who acts next.
- Link to the evidence behind the assessment, such as a review request, a new commit, an unresolved thread, or a question directed at the user.
- Explain uncertainty when responsibility cannot be established from available context. Do not present an inference as an explicit request.
- Participation alone, the latest comment's author, and generic recent activity are not sufficient evidence that the user owes a response.

### Report and suggested actions

- Identify each item's type, title, and link.
- Give a concise explanation of the current situation, the user's relevance, and the suggested next action or waiting state.
- For PRs, suggest the existing `review` or `triage` command when appropriate.
- For issues and Discussions, suggest a concrete next step with a link to the relevant conversation.
- Keep the overview read-only. It does not automatically launch review or triage, post replies, modify repository content, or merge PRs.
- Keep the user's working tree unchanged.

### Illustrative outcomes

These examples describe the intended usefulness; the precise classification rules belong in the spec.

| Situation | Intended explanation |
|-----------|----------------------|
| An open PR explicitly requests the user's review | Explain the outstanding review request and suggest reviewing the PR. |
| An author pushes commits after the user's review | Explain what changed since that review and whether a follow-up review appears needed; mark uncertainty where appropriate. |
| The user's own PR has unresolved feedback | Explain the feedback awaiting attention and suggest triage where appropriate. |
| Someone asks the user a question in an issue or Discussion | Link to the question and suggest responding. |
| The user has asked another participant a question and is awaiting their answer | Explain who the user is waiting on and link to that exchange. |
| An item remains relevant through past participation but has no apparent next action | Retain it under "No current action" with a brief explanation. |

## Open Questions

- What exact evidence and precedence determine the three groups, and how should uncertain or shared responsibility be displayed?
- What history window and item-state defaults keep the inbox useful, including stale participation, closed issues, merged PRs, draft PRs, and answered Discussions?
- What are the exact repository and item-type filter arguments, and should users be able to filter the resulting groups too?
- How should mentions, team review requests, bot activity, ordinary comments, and replies already addressed by later activity affect relevance and next-action judgments?
- What ordering, result limits, and summary depth make a busy repository manageable?
- How should the report disclose incomplete coverage, unavailable Discussions, missing permissions, or activity it could not inspect?
