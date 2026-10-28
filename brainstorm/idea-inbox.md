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

### reviewer-schema-single-source

- **Source**: deep-review
- **Date**: 2026-10-13
- **Reference**: 004-reviewer-plugins
- **Summary**: Frontmatter rules live twice, in the jq validator and in reviewer.schema.json, which no code or test reads; the reserved-name list is copied into the script, schema, docs and data model.

> Adding a field or flag means editing four or five places with nothing catching drift. A test that validates fixtures against the schema, or compares the schema's reserved list with CC_REVIEW_RESERVED_NAMES, would keep one source honest.

### goals-report-section-contract

- **Source**: deep-review
- **Date**: 2026-10-13
- **Reference**: 004-reviewer-plugins
- **Summary**: The report's Goal Delivery section is keyed on the generic `goals` context block but assumes goal-alignment's own table output.

> A contributed reviewer declaring `context: [goals]` would trigger the section without producing those tables. A reviewer-declared report-section contract would remove the last reviewer-shaped assumption from the review command.

### command-finding-path-validation

- **Source**: deep-review
- **Date**: 2026-10-13
- **Reference**: 004-reviewer-plugins
- **Summary**: Findings from command reviewers carry a `file` taken verbatim from external tool output and feed the autonomous fix loop without a containment check.

> LLM-backed tools read the untrusted diff and could be steered to emit absolute or `..` paths. Dropping findings whose file is absolute, has a `..` segment, or is not in CHANGED_FILES before the fix loop would close this.

### deterministic-command-output-parsing

- **Source**: deep-review
- **Date**: 2026-10-13
- **Reference**: 004-reviewer-plugins
- **Summary**: The `json` and `delimited` formats have no deterministic converter, so the orchestrator must read whole tool output; detection also runs for reviewers later disabled by config or --no-external.

> A shipped parse-command-output.sh for json/delimited would keep tool output out of the orchestrator's context, and passing config-disabled names to discovery would skip their network auth probes.

### timeout-process-group-detach

- **Source**: deep-review
- **Date**: 2026-10-13
- **Reference**: 004-reviewer-plugins
- **Summary**: The perl timeout backend now leaves the caller's process group like coreutils timeout, so a harness interrupt no longer reaches a running tool; it stops at its own bound.

> Recording the timeout wrapper's PID so the orchestrator can send TERM (now forwarded to the tool's group) would allow prompt cancellation of slow external reviewers.

### bulk-worktrees-outside-tree

- **Source**: deep-review
- **Date**: 2026-10-25
- **Reference**: 005-bulk-review-triage
- **Summary**: Bulk worktrees and run state live inside the user's working tree, and finished or abandoned runs are kept forever with no retention.

> Tools that ignore nested .gitignore files (linters, test runners, IDE indexers) see full nested checkouts while a run keeps them; placing worktrees under the git common dir and offering a prune option for old runs would bound disk use and avoid that.

### review-round-convergence

- **Source**: user
- **Date**: 2026-10-28
- **Reference**: Issue #8 (incremental PR review)
- **Summary**: Later review rounds should converge on a reasonable level of diligence instead of uncovering progressively smaller nits after a successful first round.

> Tighten the filter against nitpicks in follow-up rounds: focus on verifying earlier findings, meaningful problems introduced by changes, and material regressions. Once the first round's substantive concerns are addressed, avoid reopening unchanged code for minor style preferences, optional polish, or speculative improvements. Keep reporting material correctness and security issues whenever discovered. The goal is sufficient confidence to merge, not perfection; consider an explicit stopping criterion so repeated rounds can conclude successfully.
