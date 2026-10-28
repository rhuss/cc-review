# Brainstorm: Review Convergence

**Date:** 2026-10-28
**Status:** active
**Issue:** https://github.com/rhuss/cc-review/issues/11

## Problem Framing

Follow-up reviews should move a PR toward sufficient confidence to merge. They should verify earlier concerns, assess author responses, and catch meaningful new problems without repeatedly uncovering smaller nits or contradicting earlier advice without explanation.

Issue #11 records duplicate and contradictory findings observed during bulk review: an author question was ignored, an acknowledged Notable was repeated, a suggested cleanup was already promised, and a finding asked the author to undo a change requested in the previous round. These are failures of review continuity, even when a finding is technically plausible in isolation.

The `review-round-convergence` inbox item adds the need for a stopping criterion. Once substantive concerns are addressed, optional polish and speculative improvements should not create another round. A result with no material concerns is legitimate. The shared reviewer preamble currently calls zero findings a red flag and demands a second pass over the entire codebase, which conflicts with that goal and with bounded follow-up scope.

Brainstorm #09 and implemented spec `008-incremental-review` already establish personal baselines, delta review, explicit verification of earlier unresolved cc-review findings, and a Critical-only exception for new findings in unchanged code. This feature builds on those rules with broader conversation awareness and materiality throughout follow-up review. It does not replace the incremental scope model.

## Approaches Considered

### A: Conversation-aware follow-up review (chosen)

Reviewers use earlier discussion from the start. They assess prior findings and author responses against current code, distinguish new material problems from existing concerns, and reach an explicit conclusion when substantive work is complete.

- Pros: avoids duplicate work and contradictory advice at their source; preserves context through review, meta-review, decisions and reporting; gives follow-ups a consistent stopping criterion.
- Cons: requires broader, trustworthy review history and careful treatment of incomplete or ambiguous conversations.

### B: Final convergence filter

Run reviewers as today, then assess the resulting findings against prior discussion and the materiality rule.

- Pros: smaller behavioral change concentrated at the final decision.
- Cons: reviewers still rediscover settled concerns and spend effort on optional improvements; later filtering must recover context the original assessments lacked.

### C: Explicit convergence mode

Introduce a separate final-pass mode that applies conversation awareness and stricter follow-up reporting.

- Pros: gives the user explicit control over when to conclude review.
- Cons: adds a command or mode choice; ordinary follow-ups can continue producing churn until the user selects it.

## Decision

Choose Approach A as normal follow-up review behavior for both single-PR and bulk runs. The user selected material issues only, assessment of author responses against code, and conversation awareness from the start. The user confirmed the scope below.

Follow-ups verify earlier concerns and report material new issues. They use the authenticated user's earlier manual and cc-review comments, review summaries, inline discussions and author replies. Existing concerns continue in their original conversations. Reversals of earlier advice require an explicit explanation.

Conclude **"no outstanding material concerns"** when verification is complete and no material concerns remain. Missing evidence and unresolved substantive questions remain visible and prevent an unsupported clean conclusion. This conclusion is a review assessment, not an automatic GitHub approval or permission to merge.

## Key Requirements

### Review history and continuity

- Account for the authenticated user's earlier manual and cc-review findings, including review summaries, inline discussions and author replies. Include resolved discussions and replies to summary-only findings when relevant to understanding a current concern or earlier decision.
- Give reviewers, meta-review and the decision/reporting stages the relevant prior discussion so continuity shapes assessment from the start.
- Distinguish genuinely new findings from duplicate concerns, already-answered concerns, accepted deferrals and suggestions that contradict earlier advice. Link existing conversations where applicable.
- Assess author explanations against current code; an author response alone does not establish that a material concern is fixed or an explanation is accepted.
- When a concern remains, continue in its existing thread instead of posting it again as new. An unanswered author question should be addressed in that conversation rather than replaced by a duplicate demand.
- An acknowledged or promised fix is not a completed fix. Preserve the concern's actual state without repeating it as a new finding.
- When current evidence warrants reversing earlier advice, explain the reversal and its reason. Do not silently ask the author to undo a requested change.

### Materiality and code scope

- Report new follow-up findings only for concrete, consequential problems, such as correctness defects, security problems or material regressions. Suppress minor preferences, optional polish and speculative improvements, including in changed code.
- Continue reviewing the entire author delta, including requested fixes, for material problems introduced or exposed by those changes.
- Preserve the existing evidence-backed Critical-only exception for new findings in code unchanged since the review baseline. This feature does not broaden that exception to every material issue.
- Keep earlier minor suggestions nonblocking; optional polish is not required to conclude review. Do not inflate severity or manufacture findings to justify another round.
- Material problems remain reportable regardless of the number of previous rounds, within the applicable code-scope rules. Convergence does not impose a fixed round limit or excuse a real defect.

### Completion and reporting

- Treat a clean result as valid after sufficient review and verification; zero findings must not itself trigger a broader search or a demand to find something.
- Conclude "no outstanding material concerns" only when required verification is complete and there are no remaining material concerns or unresolved substantive questions.
- Explain incomplete history, unavailable evidence or incomplete reviewer coverage. Do not treat missing evidence or absence from a new finding list as proof that an earlier concern is resolved.
- Present follow-up rounds as such: distinguish verified addressed concerns, still-open material concerns, new material findings and nonblocking prior suggestions. Link related conversations and explain uncertainty.
- A review can finish its assessment with unresolved findings; it must then report those findings rather than claim the PR is clear. A clean conclusion does not require every earlier minor suggestion to be implemented.

### Workflow boundaries

- Apply the same continuity and materiality rules to single-PR and bulk follow-ups.
- Retain conversation history and the follow-up reporting policy when a follow-up falls back to full review or the user passes `--full`. A wider code-review scope does not erase earlier discussion or turn the run into a first review.
- Preserve existing posting permissions, user approval steps, personal baseline semantics and the independent responsibilities of review and triage.
- Keep initial-review behavior outside this feature's scope. Do not add automatic approval, automatic merge, a fixed round limit or a new command/mode.
- This brainstorm defines behavior only. Formal specification, implementation planning and code follow separately, tracked by existing issue #11.

## Success Criteria

- A follow-up with verified substantive fixes and only optional polish remaining can conclude with no outstanding material concerns.
- A material regression in a requested fix remains reportable; convergence never hides a real problem to meet a round quota.
- A previously raised concern, acknowledged Notable or unanswered author question is handled in its existing conversation without a duplicate finding.
- An author explanation is assessed against code, and a change requested in an earlier round is not silently criticized for complying with that request.
- Summary-only findings and their replies influence the next review alongside inline threads.
- Incomplete evidence produces visible uncertainty instead of a claim that earlier concerns were cleared.
- Single-PR, bulk, full-fallback and explicitly full follow-ups apply the same conversation-aware behavior.

## Open Questions

- What evidence identifies a follow-up when earlier reviews are manual, summary-only or lack a trustworthy incremental baseline, without confusing conversation history with completed code coverage?
- How should materiality map to existing severity and gate settings, including older findings whose severity or blocking status was misclassified?
- How should summary-only concerns and their replies retain identity and decision history when no inline thread exists?
- What evidence distinguishes an accepted explanation or agreed deferral from an unaccepted author claim, and when does new evidence justify revisiting it?
- How should incomplete or very large review histories be bounded and disclosed without silently omitting relevant decisions?
- What minimum conversation context and final checks ensure the same policy for prompt and command reviewers, meta-review and reporting?
