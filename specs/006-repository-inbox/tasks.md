# Tasks: Repository Inbox

**Input**: [spec.md](spec.md), [plan.md](plan.md), research, data model and contract.
**Execution**: sequential in this session. Tests precede runtime changes. Run `make test` after each task; review after T002 and T004.

## Foundation

- [x] T001 Build the validated read-only collector entry point and authenticated scope in `review/core/scripts/inbox.py`, with offline CLI tests in `tests/test_inbox.py` for help, invalid calendar dates/types/repo/limits, host consistency, missing authentication and timeout. Register its tests in `tests/run.sh`.

  **Interfaces**: `parse_args(argv) -> Namespace`, `GitHub.call(args) -> dict`, `collect(args, github, now=None) -> dict`, `main(argv=None) -> int`; scope/snapshot keys follow `data-model.md`. Assert invalid arguments produce zero gh calls and --help exits 0.

## US1: Discover Relevant Work (P1)

- [x] T002 Implement per-type/reason discovery, relevance union, deduplication, type guards and most-recent per-type limits in `review/core/scripts/inbox.py`; extend `tests/test_inbox.py` to assert manual review/request searches, all reasons retained, deterministic ordering, draft inclusion, no PR leakage into issues and visible search/selection caps.

  **Interfaces**: `search_query(kind, repository, login, since) -> (query, variables)`; returns source coverage and item entries through `collect`. Depends on T001. Verify the real snapshot, not fake-service behavior.

## US3: Explain Participation and Activity (P2, collector prerequisite for contextual report)

- [x] T003 Collect bounded evidence in `review/core/scripts/inbox.py` and add `tests/test_inbox.py` cases for ordinary comments, manual review commit versus head, resolved threads, Discussion answers/replies, deleted actors, nested page truncation, bounded text and safe display controls.

  **Interfaces**: `detail_query(kind) -> str`, `normalize_detail(value) -> (detail, warnings)`; detail, context_complete and warnings follow the data model. Depends on T002.

## US4: Trust Partial Results and Read-Only Behavior (P1)

- [x] T004 Harden partial GraphQL alias/type/detail failures and total failure in `review/core/scripts/inbox.py`; extend `tests/test_inbox.py` with disabled Discussions, empty success versus all-source failure, partial data, malformed JSON, timeout and a real CLI fake-gh integration that verifies allowed calls and unchanged git state/content.

  **Interfaces**: `GitHub.call` preserves usable GraphQL partial data; `collect` exposes per-type and per-item coverage; `main` exits 0/1/2 as contracted. Depends on T003.

## US2: Use the Contextual Inbox Across Harnesses (P1)

- [x] T005 Add `review/core/commands/inbox.md`, `review/skills/inbox/SKILL.md`, `review/opencode/command/inbox.md`, and `speckit/commands/speckit.cc-review.inbox.md`; register in `speckit/extension.yml`. Apply the evidence, uncertainty and grouping contract; preserve argument arrays and core resolution. Test all seven type combinations and the real OpenCode installer in `tests/test_inbox.py`.

  **Interfaces**: adapters forward the documented arguments to the shared command; it consumes the collector JSON, reads per-item evidence, then returns the three-group Markdown report. It never invokes follow-up actions. Depends on T004.

## Integration and Validation

- [x] T006 Document the command and limits in `README.md`, validate generated GraphQL queries against GitHub, run a small live read-only collector smoke test, `make test`, and `make validate`; record results in `specs/006-repository-inbox/quickstart.md` and mark tasks only after passing checks.

  **Interfaces**: documented invocations match `contracts/inbox.md`. Depends on T005. No external messages or remote content writes are part of the inbox smoke test.

## Coverage

| Requirements | Tasks | Validation |
|---|---|---|
| FR-001, FR-003, FR-004 | T001, T005 | Invalid-input tests, seven combinations, adapter installation. |
| FR-002 | T001 | Explicit/default repository and matching identity host. |
| FR-005, FR-006 | T002 | Each search reason, manual reviews, deduplication. |
| FR-007, FR-010, FR-011, FR-012 | T003, T005 | Linked context/resolutions and contextual command examples. |
| FR-008, FR-009, FR-013 | T005 | Three groups, item format, suggested actions as text. |
| FR-014, FR-019 | T001, T004, T005 | Read-only call allowlist, git/content comparison, untrusted-data instructions. |
| FR-015, FR-016, FR-017, FR-018 | T001, T002, T003, T004, T005 | Scope/counts, limits, nested gaps, partial/total failures. |
| FR-020 | T006 | Full regression suite and manifest checks. |

## Dependencies and Delivery

T001 → T002 → T003 → T004 → T005 → T006. Shared collector files make parallel execution unsuitable. Adapter files are independent once the command contract exists, but this run stays sequential as requested by project guidance. The first usable increment is a read-only factual snapshot; contextual presentation completes with T005. Semantic interpretation is verified through report examples and the post-pipeline runbook, rather than asserting a deterministic language model result in unit tests.
