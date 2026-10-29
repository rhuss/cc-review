# Issue Assessment Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline; repository guidance permits subagents only when the user requests parallel work.

**Goal:** Assess whether one issue demonstrates a concrete need and belongs in the project, then draft a welcoming maintainer reply.
**Architecture:** A bounded Python collector returns trusted identity and explicitly untrusted issue text. A shared Markdown command performs semantic assessment using verified local project evidence. Thin adapters expose it through every existing harness.
**Tech Stack:** Python 3.9+ standard library, authenticated gh, Bash, Markdown, jq.
**Spec:** [spec.md](spec.md)
**Branch:** `010-issue-assessment` | **Date:** 2026-10-29

## Summary

Add `assess <issue-number-or-URL> [--repo owner/name]`. Reuse the existing inbox transport's bounded JSON calls and text sanitation, without changing inbox behavior. Fetch one issue-or-PR union through a typed GraphQL query, reject PRs, and retain the latest 50 comments with explicit limits. The agent evaluates need, fit, and implementation value separately. Publishing is excluded.

## Global Constraints

- GitHub.com only, explicit single-issue target, no additional dependencies.
- Keep invocation checkout, branch, index, configuration, and remote issue unchanged.
- Python uses argument arrays and typed variables; never interpolate issue text into shell or queries.
- Body 20,000 characters; latest 50 comments, each 4,000 characters. Disclose all omissions and partial responses.
- Incomplete evidence is uncertainty, never proof of fabrication or lack of project fit.
- Use substantive target-project policy only. Clarify materially uncertain direction with the maintainer.
- Run `make validate`, `make test`, focused collector tests, and a documented semantic walkthrough before completion.

## Technical Context

Python 3.9+ matches inbox. `inbox.GitHub.call(args)` supplies 30-second bounded gh execution, JSON/error checks, and readable dependency failures. `inbox.clean_text(value)` removes terminal controls. The collector uses a static query with `-F number=N` and `-f` string variables. Local evidence is available only when a bounded git origin/root preflight matches the selected repository. No database or persistent assessment state.

## Constitution Check

The constitution is an unfilled template. Follow AGENTS.md and CLAUDE.md architecture, including concise adapters with no assessment logic. Pre- and post-design checks: no invented policy, no new dependencies, no mutation path, four shared-core adapters. No deviations requiring justification.

## Project Structure

- Create `review/core/scripts/assess_issue.py`: argument validation, target resolution, local-context provenance, bounded issue snapshot.
- Create `review/core/commands/assess.md`: evidence-driven assessment, material clarification, draft-only output, lifecycle/cleanup.
- Create `review/core/templates/maintainer-voice.md`: prose integration constraints and friendly fallback.
- Create `review/skills/assess/SKILL.md`, `review/opencode/command/assess.md`, `speckit/commands/speckit.cc-review.assess.md`: thin resolution/argument-forwarding adapters; register spec-kit command in `speckit/extension.yml`.
- Create `tests/test_issue_assessment.py`; connect its behavior suite to `tests/run.sh`.
- Update `README.md`, `docs/standalone-guide.md`, `docs/speckit-guide.md`.
- Feature artifacts: spec, plan, research, data-model, contracts, tasks, quickstart, RUNBOOK, verification/review evidence.

## Interfaces

- `parse_args(argv: list[str]) -> argparse.Namespace`: validates target and optional repository before I/O.
- `collect(args: argparse.Namespace) -> dict`: read-only snapshot; raises `InboxError` for unusable targets or service responses.
- `main(argv=None) -> int`: prints exactly one JSON object on success, actionable stderr and nonzero status on failure.
- Shared transport: `GitHub.call(args: list[str], deadline=None) -> dict`; no transport changes.
- Snapshot contract is [contracts/assess.md](contracts/assess.md). All adapters consume the shared command, not collector internals.

## Review Focus

1. PR numbers occupy the same namespace as issues: test valid issue URL and numeric PR rejection.
2. A target URL and --repo can disagree: test rejection before any gh call.
3. Missing or truncated conversation could invert judgment: test totals, limits, malformed comments, and partial GraphQL errors.
4. Untrusted instructions and output controls: test argument-array calls and sanitation while retaining evidence text as quoted data.
5. Unrelated local checkout or stale origin: test that mismatched origin never becomes local evidence; disclose actual branch/revision limitations in the workflow.

## Validation Strategy

Collector behavior is tested with a fake gh executable and controlled git context: argument/help paths, identity, typed variables, read-only operations, errors, body/comment bounds, missing actors, source URLs, and local-repository provenance. Adapter discovery and installation use existing harness structure; smoke-check OpenCode install into a temporary directory and spec-kit registration. Semantic examples are evaluated inline using a saved RUNBOOK; no fixture verdict is claimed as an actual agent integration test.

## Complexity Tracking

No violations. Keep semantic decisions in the command; no deterministic score or keyword classifier.
