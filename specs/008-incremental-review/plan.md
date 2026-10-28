# Implementation Plan: Incremental PR Review

**Branch**: `008-incremental-review` | **Date**: 2026-10-28 | **Spec**: [spec.md](spec.md)

## Summary

Add a deterministic Python scope/verification helper to the existing portable command engine. Commands collect personal completion evidence, compute contribution deltas in isolated checkouts, dispatch reviewers with explicit scope, verify all owned earlier findings and publish baseline evidence only for complete work.

## Technical Context

Python 3.9+ standard library, Bash 3.2-compatible wiring, Markdown command instructions; existing Git, gh, jq and yq. No new runtime dependencies. Store completion metadata in GitHub review bodies and intermediate scope/diff/verification JSON in existing run directories. Test with real temporary Git repositories, unittest, existing Bash tests and `make validate`. Support existing macOS/Linux and Claude Code/Codex/OpenCode adapters. Inbox performs no local contribution comparison and keeps existing bounded collection.

## Global Constraints

- Personal completed baselines only; full fallback on unavailable or incompatible coverage.
- Entire delta including fixes; critical-only concrete-evidence exceptions outside it.
- No fix inferred from absence; no duplicate thread actions or triage baseline advancement.
- Preserve existing approval, unattended, checkout-isolation and draft policies.
- Python 3.9+ standard library and existing tools only.

## Constitution Check

The constitution is an unfilled template. AGENTS.md requires validation and committed/pushed work, and prohibits subagents without a request for parallel work. Run stages/review perspectives inline. Pre-design and post-design checks pass.

## Project Structure

| File | Responsibility |
|------|----------------|
| `review/core/scripts/review_scope.py` | Completion validation, coverage fingerprint, read-only scope comparison, finding policy, exact verification reconciliation and JSON CLI |
| `review/core/scripts/platform.sh` | Make incomplete thread pagination explicit |
| `review/core/scripts/pr_actions.py` | Preserve explicit requests despite unchanged-contribution evidence |
| `review/core/commands/review.md` | Shared single/bulk scope, dispatch, verification, reporting and completion lifecycle |
| `review/core/commands/triage.md` | Shared verification contract with existing activity/role guards |
| `review/core/commands/bulk.md` | Forward `--full`, retain artifacts and distinguish unchanged/incomplete outcomes |
| `review/core/scripts/bulk-apply.sh` | Attach validated completion evidence to no-findings reviews |
| `review/core/schemas/finding.schema.json` | Optional scope, concrete evidence and exact previous-thread attributes |
| `review/core/agents/{preamble,meta-skeptic,meta-calibrator}.md` | Scope/verification evidence policy |
| Review adapters under `review/skills/`, `review/opencode/`, `speckit/` | Public `--full` pass-through |
| `tests/test_review_scope.py`, `tests/test_pr_actions.py`, `tests/run.sh` | Semantic Git, baseline, verification, selector and adapter regressions |
| `README.md`, `docs/standalone-guide.md` | Behavior, evidence requirements and fallbacks |

## Design

### Baseline and cumulative coverage

Use an exact standalone `cc-review-scope:v1` JSON marker beside the existing run marker. Validate author, PR identity, submitted review commit, object IDs, completion, coverage fingerprint and chain to a completed full review. Reject quoted/fenced/duplicate/malformed markers and marked incomplete runs. Legacy run markers alone cannot prove completion. Complete no-findings runs can establish baselines. Fingerprint effective reviewer metadata/bodies/references/parser contents, settings, shared prompts, hints and spec context; installation paths are not coverage. Changed coverage forces full review.

### Contribution comparison

Store each reviewed head and merge-base. Compare heads directly only with ancestry and unchanged merge-base. Otherwise reconstruct the old contribution on the current merge-base using a temporary Git index and three-way cached application of its binary patch, then compare the reconstructed tree to the current head. Conflicts, missing objects or ambiguous merge-bases trigger full scope. Empty comparison proves unchanged contribution. Preserve renamed/deleted/binary paths. Never mutate the checkout, refs or user index. Dirty local PR checkouts receive full scope and cannot publish pinned completion evidence.

### Findings and verification

Keep the original full changed-file list for discovery/trust and PR inline anchors. Delta paths and current-line intervals drive prompt scope. Command reviewers without incremental support receive disclosed full input. One deterministic classifier applies after merge/meta-review and before fixing/posting: ordinary findings intersect delta lines; carried findings refer to exact verified threads; unchanged-critical findings require Critical severity and concrete evidence.

Collect all owned unresolved cc-review threads, including older runs, using existing activity ownership/completeness/fingerprint machinery. Explicit outcomes contain exact activity, code-check evidence and fixed/still-present/unclear or explicitly accepted explanation status. Reconciliation rejects missing, duplicate or stale results. Absence from new findings and line proximity never prove resolution. Review and triage share this contract. Verify before fixing and refresh after code changes. Existing approval and remote freshness guards remain authoritative.

Completion requires all required reviewers, complete comparison/verification, clean pinned code and fresh publication evidence. Remaining findings do not imply incompleteness. No incomplete or unposted run advances hosted baseline evidence. Review/triage selection stays independent and lightweight.

## Interfaces

- `plan_scope(repo: Path, snapshot: dict) -> dict`: mode, baseline, head/base, coverage key, completeness, changes, diff and explanation.
- `coverage_key(reviewers: list, settings: dict, context_files: list) -> str`: stable fingerprint of effective coverage.
- `verification_targets(snapshot: dict) -> dict`: complete, exact targets, warnings.
- `reconcile_verifications(batch: dict, outcomes: list) -> dict`: complete, verified outcomes, resolution candidates and warnings.
- `filter_findings(scope: dict, findings: list, verified: list) -> dict`: accepted scoped findings and exclusions.
- `completion_marker(scope: dict, run_id: str, reviewers: list, verification: dict) -> dict`: marker/evidence only when all completion requirements hold.
- JSON CLI subcommands `prepare`, `targets`, `reconcile`, `filter`, `marker`; `prepare --repo PATH --input FILE --output DIR`, others `--input FILE`.

## Review Focus

Forged or quoted metadata, foreign identities, cyclic/missing coverage chains, changed settings; real pure/mixed rebases and conflicts; missing objects; renamed/deleted/binary/spaced paths; dirty index/worktree preservation; missing/duplicate/stale verification; moved/absent findings; failed required tools and incomplete pagination; renewed explicit requests on unchanged contribution.

## Validation

Write semantic tests before code. Run focused unittest cases for each behavior, then `make test` after each completed task. Run `make validate`, inspect diff, perform a separate six-perspective code review sequentially, and publish committed work. Never post to live PRs merely for tests.
