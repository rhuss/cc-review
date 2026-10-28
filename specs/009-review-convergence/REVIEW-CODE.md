# Code Review: Review Convergence

**Spec:** [spec.md](spec.md)
**Date:** 2026-10-28
**Branch:** `009-review-convergence`
**Reviewer:** Codex, in-session review; independent CodeRabbit review
**Gate Outcome:** PASS

## Compliance

Source and contract review: 19/19 functional requirements implemented. This is an implementation assessment, not a claim that a live agent walkthrough has run.

| Requirement | Implementation and evidence | Status |
|-------------|-----------------------------|--------|
| FR-001 | `review_continuity.py:prepare_history`; personal submitted/manual sources, draft/foreign exclusion tests | Compliant |
| FR-002 | platform review/thread/comment collectors; source/context preservation and manual summary attribution tests | Compliant |
| FR-003 | collection flags, pagination bounds, duplicate/missing source checks and history fingerprint | Compliant |
| FR-004 | Prior Review Context dispatch, both critic input lists and bulk worker boundaries | Compliant |
| FR-005 | `assess` relation validation and exact carried-thread constraint | Compliant |
| FR-006 | concern code/evidence checks and explicit approval for accepted explanations | Compliant |
| FR-007 | linked continuations, unresolved-question check and original-conversation posting instructions | Compliant |
| FR-008 | required source/evidence/reversal reason; regression test | Compliant |
| FR-009 | post-calibration material impact and Critical/Important filter | Compliant |
| FR-010 | optional suggestions excluded from new findings/mandatory fixes; nonblocking concern count | Compliant |
| FR-011 | existing scope engine unchanged; full/delta contract fixtures and scope regression suite | Compliant |
| FR-012 | zero-result quota removed; legitimate clean-result fixture | Compliant |
| FR-013 | complete history, coverage, verification and question/material checks | Compliant |
| FR-014 | progress report contract, source counts, continuation links and excluded/unassessed candidates | Compliant |
| FR-015 | shared executable blocks and bulk contract; full fallback/override preserve history | Compliant |
| FR-016 | retained assessment context prevents stale judgments being rebound; final-code and pre-publication checks | Compliant |
| FR-017 | no mutation in the new engine; existing verification remains sole resolution authority | Compliant |
| FR-018 | initial findings passed unchanged, explicit first-review prompt policy, no new mode/round limit | Compliant |
| FR-019 | 37 semantic/CLI/collector/executable-contract tests registered in full runner; public docs updated | Compliant |

## Edge cases and quality

- Complete empty history is distinguished from unavailable evidence. Pending personal drafts and foreign reviewers cannot establish a personal follow-up.
- Manual summaries and inline roots preserve conversation context. Author promises are not verified fixes; accepted explanations need approval.
- Missing/duplicate/unknown/stale decisions, unresolved questions and incomplete coverage cannot yield a clean conclusion. A context captured before semantic assessment remains attached to its judgments through refresh/resume.
- Malformed GraphQL connections fail with explicit incomplete collection rather than an empty success. Pagination caps and partial arrays are visible.
- Existing incremental scope and thread ownership remain outside the new history engine. Source conversations are not misrepresented as unique defect counts.
- Source content is explicitly untrusted evidence; the new Python engine performs no network, Git, shell or hosting mutations. JSON data is passed through quoted file arguments.
- macOS system Bash 3.2 with nounset is exercised by a boundary test.

## Review outcome

Five Important issues found by in-session review were corrected: initial-review prompt overreach, carried concerns recast as new, pending draft threads treated as prior feedback, refreshed history relabeling stale semantic judgments, and an unguarded context write during local non-PR review. Both CodeRabbit wording findings were verified and corrected. Its follow-up review of the changed source files reported zero remaining findings. The final assessment-context wiring correction is verified by the executable regression and reviewed in-session; it was made after that external pass.

Separate passes covered correctness, architecture, security, production readiness, test quality and goal delivery. They were performed by the same agent to respect the project's restriction on unrequested Codex subagents. CodeRabbit provided the independent external source review. External Codex was not spawned; Copilot is disabled in configuration.

## Verification

- Focused continuity suite: 37 tests passed.
- Existing incremental scope suite: 29 tests passed; full runs also include it.
- Previous complete integration and review-fix suites: 1312 passed, 0 failed (163 tests).
- Latest full regression: 1312 passed, 0 failed (163 tests). The preceding run caught the local non-PR guard regression (1311 passed, 1 failed); that exact regression and the final complete rerun now pass.
- `make validate`: passed; existing missing-icon directory warning remains unrelated to this change.
- Shell syntax and whitespace checks: passed.
- Local runbook: 5/5 steps passed during finish, including six shared coordinator scenarios. A live hosted-PR/agent interpretation session was not run.
