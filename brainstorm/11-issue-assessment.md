# Brainstorm: Issue Assessment

**Date:** 2026-10-29
**Status:** active

## Problem Framing

Maintainers need to decide whether an initial issue describes a real problem, fits the project's purpose and principles, and should be implemented. A plausible feature proposal or an offer to write code does not by itself justify adding that feature. Assessing the need before discussing a solution helps avoid speculative functionality and maintenance obligations without discouraging contributors who bring useful ideas.

The desired command reads an issue and its discussion, examines relevant project context, makes a reasoned recommendation for the maintainer, and drafts a friendly public reply using the prose plugin. It should be willing to recommend against pursuing an issue. Its purpose is to help decide whether work should happen, as well as suggest a useful next step when it should.

The existing `inbox` command discovers issues needing attention but does not assess whether their proposals belong in the project. Existing `review` and `triage` commands focus on PRs. This is a separate issue workflow, adjacent to [#07: Repository Inbox](07-repository-inbox.md) and the explicitly deferred issue workflows in [#08: Inbox Action Alignment](08-inbox-action-alignment.md).

## Approaches Considered

### A: Maintainer assessment plus a draft reply (chosen, with clarification when needed)

Read the issue, discussion, relevant project guidance, and enough code or documentation to assess its claims. Present the maintainer with the reasoning and a recommendation, then draft a concise public reply. Ask the maintainer targeted questions when uncertainty could materially affect the decision.

- Pros: makes the judgment reviewable; supports a real decision about project fit and implementation; keeps the public response natural and welcoming; handles ambiguous intent without guessing.
- Cons: requires more investigation than merely rewriting the issue and may need an interactive exchange for uncertain cases.

### B: Reply only

Perform the assessment internally and present only the proposed comment.

- Pros: concise and quick to use for routine issues.
- Cons: hides assumptions and evidence behind the recommendation, making consequential decisions harder to assess.

### C: Interactive assessment for every issue

Discuss the assessment with the maintainer before drafting any reply.

- Pros: gives the maintainer direct control over ambiguous project-direction decisions.
- Cons: adds friction when the issue and project context already support a clear recommendation.

## Decision

Choose Approach A, incorporating targeted clarification from C whenever uncertainty matters. The command must assess whether the issue is a good fit and should be implemented, rather than assume implementation is desirable and only discuss how to proceed.

The user explicitly chose:

- When an issue supplies no concrete use case, request one before discussing a solution.
- Once a real need and project fit are established, usually welcome an offer to implement, sketch a bounded approach, and identify decisions requiring maintainer input.
- Present a maintainer assessment and a proposed public reply.
- Ask the maintainer about uncertain questions instead of forcing a recommendation from incomplete context.

The proposed operating boundary is assessment and drafting. Publishing the comment requires an explicit user request. This brainstorm does not implement a command or create a formal specification.

## Key Requirements

### Establish the need before exploring a solution

- Identify who needs to accomplish what, in which real situation, what blocks them, and what consequence or cost they experience.
- Look for concrete use cases in the whole issue conversation, not just the opening description. Recognize an adequate explanation even when it does not follow an issue template.
- Separate the underlying problem from the proposed solution. A real need may deserve support through a smaller or different solution.
- If no concrete use case is supplied, draft a focused request for one. Hold off on solution sketches and contribution plans until the need is established.
- Distinguish missing evidence from evidence that a claim is false. Do not invent a use case to rescue a proposal or call a problem imaginary merely because its report lacks detail.
- Evaluate consequences and relevant technical evidence. Concrete preventive concerns can be substantiated without waiting for an incident; generic claims that something might someday be useful are insufficient.

### Assess project fit and whether to proceed

- Consult the target project's actual goals, principles, scope, contribution guidance, and relevant existing behavior. Use a substantive constitution where one exists; an unfilled template is not project policy.
- Ground judgments in identifiable sources. Separate explicit project decisions from inferences, and ask the maintainer when undocumented direction or conflicting guidance affects the result.
- Consider whether existing functionality or a practical workaround already meets the need, whether another project is the appropriate home, and whether the benefit warrants the complexity and ongoing maintenance.
- Make a reasoned recommendation: pursue the need, request evidence or clarification, or do not pursue it in this project. Explain the decisive evidence and remaining uncertainty. Exact outcome labels belong in the specification.
- Treat problem validity and project fit separately: a real problem may still fall outside the project's purpose, and an attractive solution may lack a demonstrated need.
- Do not equate an offer to contribute with evidence that the feature belongs in the project.

### Ask useful questions when uncertain

- Ask the maintainer when a missing fact, ambiguous principle, scope choice, or trade-off could change whether the issue should be pursued.
- Distinguish questions for the maintainer about project direction from missing use-case details that the issue author should supply in the drafted reply.
- Reuse answers and decisions already present in the conversation. Do not turn every assessment into a mandatory interview or silently resolve material ambiguity.

### Welcome bounded contributions

- Where the need and fit support proceeding and the reporter offers help, usually welcome the contribution and sketch a small approach with a clear intended outcome.
- Identify important boundaries and decisions needing maintainer input. Keep the sketch at the level of a useful handoff, rather than producing a full implementation plan.
- Assess whether the work is understood and scoped enough for a contributor to start. Avoid unsupported judgments about the contributor's competence or personal characteristics.
- An invitation to contribute does not promise acceptance, assign the issue, or commit the maintainer to implementing it.

### Produce a reviewable assessment and welcoming reply

- Show the maintainer the recommendation, decisive evidence, project-fit reasoning, and material uncertainties separately from the public comment draft.
- Use the prose plugin to formulate a concise, natural, friendly reply that preserves the assessment's meaning and uncertainty. Do not inherit PR-specific severity labels or the inline-review format automatically.
- Match the reply to the outcome: request a concrete use case, welcome a bounded contribution, or explain why the project should not pursue the proposal.
- Address the proposal and evidence without speculating about motives. A firm recommendation against implementation can remain respectful and leave room for new information.
- Keep the workflow focused on initial issues. Do not implement code, create PRs, close or label issues, or publish comments as a side effect of assessment.

### Illustrative outcomes

| Situation | Expected assessment and reply |
|---|---|
| A feature proposal describes only hypothetical usefulness | Request one concrete use case before suggesting a solution. |
| A concrete workflow is blocked and fits the project's goals; the reporter offers help | Recommend pursuing the need, welcome the offer, and sketch a bounded approach. |
| The problem is real but the requested feature conflicts with documented project scope | Recommend against this proposal in the project, explain the mismatch, and mention a supported alternative where one exists. |
| A documented use case is convincing but project direction is ambiguous | Ask the maintainer the question that could change the decision before finalizing the recommendation. |
| Existing functionality appears to address the need | Explain the existing path with evidence and ask about any remaining gap rather than assume a new feature is needed. |

## Open Questions

- What should the command be named, and what issue-number, URL, and repository inputs should it accept?
- What precedence and discovery rules should apply to project principles, contribution guidance, review hints, and maintainer decisions when sources conflict or are incomplete?
- What bounded investigation and evidence presentation are sufficient to check issue claims without turning assessment into an implementation or full code review?
- What should happen when the prose plugin is unavailable, and should issue replies use a dedicated maintainer voice?
- How should later invocations incorporate new use-case evidence and prior maintainer answers without repeating questions or contradicting earlier decisions?
- Should the inbox eventually suggest this command for relevant issues? Automatic invocation and bulk issue assessment are outside the initial agreed workflow.
