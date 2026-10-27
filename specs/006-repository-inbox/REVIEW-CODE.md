# Code Review: Repository Inbox

**Spec:** [spec.md](spec.md)
**Date:** 2026-10-26
**Reviewer:** Codex, in-session sequential review
**Functional compliance:** 100% (20/20 requirements implemented)
**Gate outcome:** PASS

## Requirement Coverage

| Requirement | Implemented behavior | Evidence | Status |
|---|---|---|---|
| FR-001 | Shared command and all harness adapters | [review/skills/inbox/SKILL.md:6](../../review/skills/inbox/SKILL.md#L6) | Pass |
| FR-002 | Canonical repo and matching-host identity | [review/core/scripts/inbox.py:300](../../review/core/scripts/inbox.py#L300) | Pass |
| FR-003 | All types, any union of filters | [review/core/scripts/inbox.py:39](../../review/core/scripts/inbox.py#L39) | Pass |
| FR-004 | Argument validation before service calls | [review/core/scripts/inbox.py:39](../../review/core/scripts/inbox.py#L39) | Pass |
| FR-005 | Separate provenance searches for all applicable roles | [review/core/scripts/inbox.py:115](../../review/core/scripts/inbox.py#L115) | Pass |
| FR-006 | Typed identity deduplication with reason union | [review/core/scripts/inbox.py:141](../../review/core/scripts/inbox.py#L141) | Pass |
| FR-007 | Linked conversation, review/commit and resolution facts | [review/core/scripts/inbox.py:210](../../review/core/scripts/inbox.py#L210) | Pass |
| FR-008 | Three groups including empty groups | [review/core/commands/inbox.md:109](../../review/core/commands/inbox.md#L109) | Pass |
| FR-009 | Item identity, relevance, situation, action and links | [review/core/commands/inbox.md:115](../../review/core/commands/inbox.md#L115) | Pass |
| FR-010 | Evidence and explicit/inferred distinction | [review/core/commands/inbox.md:79](../../review/core/commands/inbox.md#L79) | Pass |
| FR-011 | No obligation based only on participation/recency | [review/core/commands/inbox.md:77](../../review/core/commands/inbox.md#L77) | Pass |
| FR-012 | Recursive incompleteness plus uncertain report rule | [review/core/scripts/inbox.py:238](../../review/core/scripts/inbox.py#L238) | Pass |
| FR-013 | PR-only review/triage suggestions; conversation next steps | [review/core/commands/inbox.md:101](../../review/core/commands/inbox.md#L101) | Pass |
| FR-014 | Only read requests and private temporary output | [review/core/commands/inbox.md:24](../../review/core/commands/inbox.md#L24) | Pass |
| FR-015 | Scope/identity/time/limits header | [review/core/commands/inbox.md:107](../../review/core/commands/inbox.md#L107) | Pass |
| FR-016 | Bounded search, selection, nested context and text | [review/core/scripts/inbox.py:141](../../review/core/scripts/inbox.py#L141) | Pass |
| FR-017 | Source and item failures retained as explicit warnings | [review/core/scripts/inbox.py:278](../../review/core/scripts/inbox.py#L278) | Pass |
| FR-018 | Actionable prerequisites/auth/repo/total-failure errors | [review/core/scripts/inbox.py:71](../../review/core/scripts/inbox.py#L71) | Pass |
| FR-019 | No shell evaluation; untrusted-content boundaries | [review/core/commands/inbox.md:24](../../review/core/commands/inbox.md#L24) | Pass |
| FR-020 | Existing command source unchanged; regression suite passes | [tests/run.sh:3670](../../tests/run.sh#L3670) | Pass |

## Errors and Edge Cases

- Argument errors stop before gh calls, including empty values, impossible dates, invalid types and out-of-range limits.
- Missing gh, unavailable authentication and repository-resolution failures produce actionable errors without a successful empty snapshot.
- Independent type/alias failures preserve usable results. Total source failure exits nonzero. Partial GraphQL data remains usable even when gh exits nonzero.
- Missing detail, null/deleted actors, empty activity, nested pagination and trimmed bodies are represented honestly; incomplete context prevents a confident no-action verdict.
- Duplicate reasons are unioned, draft PRs are retained, stale closed issue/PR search hits are excluded, and issue results cannot include PR nodes.
- Bot activity and participation are facts, not automatic human obligations; resolution and Discussion answer state are available for assessment.
- Collection describes observed state and does not lock items or promise an atomic repository transaction.
- User text is never evaluated by a shell. The real CLI preserves staged, unstaged and untracked content, and only read-only hosting operations are permitted.

## Review Perspectives

Six perspectives were reviewed sequentially in this session to respect the repository instruction restricting Codex subagents. No independent subagents were used.

| Perspective | Result |
|---|---|
| Correctness | Query provenance, type/identity guards, selection, nested evidence and failure paths match the spec. |
| Architecture | Shared core plus thin adapters follows the existing project pattern; no extra service or persistent inbox store. |
| Security | Argument arrays, named query operations, control-character sanitization and untrusted-content instructions preserve the read-only boundary. |
| Production readiness | Every request has a finite timeout; result/activity/text bounds and partial failures are visible. |
| Test quality | Tests execute the collector through a fake hosting boundary and real subprocesses; they verify observable behavior, not Markdown source wording. |
| Goal alignment | All selected item types, filters, personal relevance and who-acts-next groups are implemented; actions remain suggestions. |

## External Review and Fix

CodeRabbit reviewed the changed files under review/. It reported one Minor compatibility finding: identifier validation rejected underscores in managed account names. Verified against [GitHub's managed-user naming rules](https://docs.github.com/en/enterprise-cloud%40latest/admin/managing-iam/iam-configuration-reference/username-considerations-for-external-authentication). Fixed the login and owner allowlists while preserving their leading-character restrictions and query-safe character set.

Both regression tests failed before the fix and pass afterwards. CodeRabbit's targeted re-review completed with zero findings. See [review-findings.md](review-findings.md).

External Codex review was not launched under the repository's restriction on Codex subagents. Copilot was disabled in project configuration.

## Verification

- 31 inbox unittest cases pass.
- Full project suite: 1,164 assertions pass, zero failures, across 141 runner tests.
- make validate passes both marketplace and plugin checks. The existing optional missing-icon warning is unchanged.
- Search and detail queries for all three types validated against GitHub.
- Live issue-only and all-type snapshots succeeded for rhuss/cc-review.
- OpenCode installation resolves the new command and its core.
- Python 3.9 syntax checks pass; tests ran with the locally installed Python.

## Practical Limits

Contextual judgments are produced by the harness from the collected evidence, not a deterministic classifier. Automated tests verify collection, coverage and packaging; the native harness walkthrough remains drafted for interactive use.

The live repository had no matching PRs and had Discussions disabled. It contained one authored issue with a shortened body. A report must therefore mark that issue's context as incomplete and retain the unavailable-Discussions warning, rather than inferring an obligation from authorship or claiming a complete empty queue.

No unresolved spec deviations or review findings remain.
