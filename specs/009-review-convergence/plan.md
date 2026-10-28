# Implementation Plan: Review Convergence

**Branch**: `009-review-convergence` | **Date**: 2026-10-28 | **Spec**: [spec.md](spec.md)

## Summary

Add a read-only conversation-history and convergence engine beside the existing scope engine. Preserve source conversations for semantic code-backed assessment; enforce completeness, evidence, materiality and duplicate handling deterministically. Wire one contract through single and bulk review, critics, fix rounds and reporting. Coverage markers and automatic thread resolution remain governed by the existing scope/verification engine.

## Technical Context

- Language: Python 3 standard library and Bash; Markdown defines the harness workflow.
- Dependencies: existing `gh`, `jq`, Git and Python. No new package or service.
- Storage: per-run JSON artifacts under the existing scope directory.
- Testing: unittest semantic/CLI scenarios, stubbed read-only `gh` boundary, wiring assertions, `make test`, `make validate`.
- Platform: existing macOS/Linux shell workflow. No new public CLI flag.
- Scale: reuse bounded paginated collection; disclose all truncation. No LLM matching by text heuristics in deterministic code.

## Global Constraints

- Preserve the evidence-backed Critical-only unchanged-code exception and existing full-review scope semantics.
- Preserve personal baseline semantics, review/triage independence, posting permissions, user approval steps and worktree restrictions.
- No automatic approval, merge, fixed round limit or new command/mode.
- Earlier manual reviews establish conversation context, not coverage.
- Existing issue #11 tracks implementation; no live hosting writes in tests.

## Constitution Check

The constitution is an unfilled template. No project principles are silently invented. Pre- and post-design checks pass: changes follow existing Bash/Python/Markdown boundaries and use no new dependency.

## Research and Design

See [research.md](research.md), [data-model.md](data-model.md) and [contracts/continuity.md](contracts/continuity.md).

The collector preserves reviews, resolved and unresolved threads, and all issue comments as conversation context. Only personal submitted reviews, personal root findings or explicitly marked personal review comments establish a follow-up. Every relevant source has a stable identity and link. Context-only issue comments do not become findings automatically.

A semantic assessor evaluates each source and each candidate against actual code. The deterministic assessor requires one assessment per source and candidate, exact history fingerprint and head, code evidence, explicit approval for accepted explanations and an explanation for reversed advice. New follow-up findings require Critical/Important plus material impact evidence. Existing substantive concerns stay in their original conversations; nonblocking prior suggestions remain report data. The clean conclusion requires complete history/assessment, existing verification and required coverage.

Run the existing scope filter first, then continuity assessment after calibration and again after fixes. Keep its output artifacts separate from coverage markers. Exact carried findings remain available to existing gates and thread verification; manual/summary continuation counts also inform the gate. Never fabricate `prior_thread_id` for a manual summary. Publication refresh must compare history and head again, not merely reuse a clean flag.

## File Structure and Responsibilities

- `review/core/scripts/review_continuity.py`: normalize history (`prepare_history`) and validate semantic decisions (`assess`), CLI `prepare`/`assess`; no network or filesystem mutations beyond stdout.
- `review/core/scripts/platform.sh`: new `fetch_issue_comments` bounded GraphQL pagination; enrich review/thread source URLs without changing their existing fields or writes.
- `review/core/commands/review.md`: collect before dispatch, semantic assessment instructions and executable helper invocations, gate/report/fix/publication contract.
- `review/core/commands/bulk.md`: retained continuity artifacts and stale-analysis checks.
- `review/core/agents/preamble.md`, `meta-skeptic.md`, `meta-calibrator.md`: conversation-aware evidence and materiality, legitimate zero result.
- `tests/test_review_continuity.py`: semantic normalization, assessment, CLI, collection and workflow-wiring regressions.
- `tests/run.sh`: register the new suite.
- `README.md`, `docs/standalone-guide.md`: public behavior and limits.

## Review Focus

Pin pending versus submitted personal reviews, foreign history, manual roots, summary replies, resolved threads, empty complete versus failed collection, missing/duplicate IDs, pagination caps and GraphQL errors, removed/changed evidence, malformed decisions, unknown/duplicate source references, severity calibration, promised fixes, accepted explanations without approval, unanswered questions, and clean versus complete semantics. Existing scope tests prove unchanged-code filtering and baseline rules remain unchanged.

## Validation Strategy

Each task begins with failing behavioral tests, implements its contract, then runs focused tests and `make test`. Review checkpoints inspect code against spec after tasks 1 and 2. Final review includes correctness, architecture, security, production readiness, test quality and goal delivery as separate passes in-session; the user prohibits unrequested subagents. External tools run as configured when installed/authenticated. Record unavailability without claiming their coverage.
