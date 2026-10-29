# Tasks: Issue Assessment

**Input**: spec.md, plan.md, research.md, data-model.md, contracts/assess.md.
**Execution**: Inline, sequential. Every task includes implementation and its relevant checks. Existing repository setup is reused.

## Phase 1: Setup and Foundation / User Story 1

Goal: Supply a trustworthy read-only issue snapshot. Independent test: execute the real CLI against controlled GitHub responses.

- [x] T001 [US1] Add bounded collection in `review/core/scripts/assess_issue.py` and behavior tests in `tests/test_issue_assessment.py`.

**Interfaces**: Produces `parse_args(argv) -> Namespace`, `collect(args) -> dict`, `main(argv=None) -> int`; consumes existing `inbox.GitHub.call` and `clean_text`.

1. Write tests for help and invalid arguments with zero service calls, explicit and inferred repositories, URL conflict, typed issue number, PR rejection, partial/malformed responses, missing actors, text bounds, untrusted commands, and local-origin mismatch.
2. Run `python3 -B tests/test_issue_assessment.py` and observe failure because the collector does not exist.
3. Implement the collector and snapshot contract. Use only read-only gh calls, 30-second transport timeouts and 5-second local git timeouts; latest 50 comments, body 20,000 characters, comment 4,000 characters.
4. Run focused tests and `make test`. Checkpoint 1: correctness review of target validation, transport arguments, and coverage metadata; record findings and fixes.

Exact behavioral assertions include:

```python
assert invalid.returncode != 0 and calls == []
assert snapshot["issue"]["number"] == 42
assert snapshot["conversation_complete"] is False  # omitted or shortened evidence
assert snapshot["local_context"]["matching"] is False  # unrelated origin
assert "--method" not in graphql_args and "number=42" in graphql_args
```

## Phase 2: User Stories 1, 2, and 3

Goal: Decide whether work belongs in the project and compose a respectful draft. Independent test: inspect the scenario walkthrough for each supported outcome.

- [x] T002 [US1] Implement assessment and clarification in `review/core/commands/assess.md`, contribution handling and fallback wording in `review/core/templates/maintainer-voice.md`, and scenario walkthroughs in `specs/010-issue-assessment/RUNBOOK.md`.

**Interfaces**: Consumes T001 snapshot. Produces a maintainer assessment and separate public draft; material maintainer uncertainty instead produces a focused question before final wording.

1. Establish the tool/data boundary, matching-checkout inspection, private temp lifecycle, and cleanup on success/error/cancellation.
2. Define need, fit, and implementation recommendation separately; no-use-case means one author question and no plan.
3. Cover project direction questions, prior answers, preventive concerns, existing features, and bounded welcoming contribution outlines.
4. Use exposed prose humanizer inline when available, otherwise bundled maintainer voice; preserve evidence and judgment.
5. Walk through speculative, supported contribution, out-of-scope, conflicting-policy, existing-functionality, later-comment, preventive, and incomplete-context cases. Run `make test`. Checkpoint 2: correctness of semantic boundaries and read-only behavior; record findings and fixes.

## Phase 3: User Story 4 and Cross-Cutting Verification

Goal: Make the shared workflow available through every supported installation. Independent test: resolve all adapters and install OpenCode into a temporary project.

- [x] T003 [US4] Add `review/skills/assess/SKILL.md`, `review/opencode/command/assess.md`, `speckit/commands/speckit.cc-review.assess.md`; register `speckit/extension.yml`, integrate `tests/run.sh`, and document in `README.md`, `docs/standalone-guide.md`, and `docs/speckit-guide.md`.

**Interfaces**: All adapters consume T002 core command, verify T001 script, preserve CWD, and forward target and --repo unchanged. Native manifests discover skills automatically.

1. Keep shims under 50 lines and free of assessment logic; spec-kit command works outside ship and adds no spec/review flags.
2. Register the collector suite with `tests/run.sh`; smoke-check OpenCode installation and spec-kit registration.
3. Document invocation, requirements, genuine go/no-go judgment, author versus maintainer questions, prose fallback, and draft-only behavior.
4. Run focused tests, `make test`, `make validate`, and `git diff --check`; record exact verification evidence and limitations.

## Coverage

| Requirements | Tasks |
|---|---|
| FR-001 | T003 |
| FR-002, FR-003 | T001 |
| FR-004 | T001, T002 |
| FR-005 through FR-014 | T002 |
| FR-015 | T001, T002 |
| FR-016 | T001, T002, T003 |
| FR-017 | T001, T002 |
| FR-018 | T002 |
| FR-019 | T001, T002 |

SC-001 through SC-004: T002 scenario walkthrough. SC-005: T003 adapter installation. SC-006: T001 automated behavior and T002/T003 boundary review.

## Dependencies and Implementation Strategy

T001 → T002 → T003. MVP is T001 plus the US1 portion of T002. US2 material clarification and US3 contributions share the same semantic workflow and are reviewed there. US4 adapters depend on the shared command. No parallel delegation is requested.

## Plan Review

All 19 requirements and six success criteria are covered. Review Focus cases belong to T001 tests and T002 walkthroughs. Interface names, bounds, and file paths match plan and contract. No placeholder decisions, excessive implementation transcript, or unowned dependencies remain.
