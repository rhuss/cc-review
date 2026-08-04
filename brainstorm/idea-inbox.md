# Idea Inbox

Ideas captured from code reviews for future brainstorming.

### goal-alignment-skip-behavior

- **Source**: triage
- **Date**: 2026-08-03
- **Reference**: PR rhuss/cc-spex#51 (051-extract-cc-review)
- **Summary**: The spec's user story 1 mentions goal-alignment as a review perspective but doesn't explicitly state it should be skipped when no PR context exists. The behavior is defined in research.md R-005 and tasks.md T015b but not in the spec itself.

> CodeRabbit flagged that FR-003 lists goal-alignment as a required perspective, while the no-PR flow has no defined behavior for it. The downstream artifacts (research.md, plan, tasks) already handle this correctly by skipping goal-alignment without PR context. Consider adding an explicit note to the spec's acceptance scenarios or FR-003 stating that goal-alignment is skipped gracefully when no PR body/issue metadata is available.


### spec-completeness

- **Source**: triage
- **Date**: 2026-08-03
- **Reference**: PR rhuss/cc-spex#51 (051-extract-cc-review)
- **Summary**: Spec and documentation artifacts don't fully reflect implementation decisions around triage removal and skip behaviors.

> When extracting/removing features, update all spec-level references, not just code-level ones. Pattern detected from 3 CodeRabbit findings about gaps between what the spec describes and what the code implements.
