# Deep Review Findings

**Date:** 2026-10-28
**Branch:** `009-review-convergence`
**Rounds:** 2 fix cycles
**Gate Outcome:** PASS
**Invocation:** ship, Smart oversight

## Summary

| Severity | Found | Fixed | Remaining |
|----------|-------|-------|-----------|
| Critical | 0 | 0 | 0 |
| Important | 5 | 5 | 0 |
| Minor | 2 | 2 | 0 |
| Notable | 0 | 0 | 0 |

## Review coverage

These are sequential review passes by the same agent, not six independent subagents. Project instructions prohibit unrequested Codex subagents.

| Pass / tool | Found | Fixed | Remaining | Status |
|-------------|-------|-------|-----------|--------|
| Correctness | 5 | 5 | 0 | reviewed in-session |
| Architecture | 0 | 0 | 0 | reviewed in-session |
| Security | 0 | 0 | 0 | reviewed in-session |
| Production readiness | 0 | 0 | 0 | reviewed in-session |
| Test quality | 0 | 0 | 0 | reviewed in-session |
| Goal alignment | 0 | 0 | 0 | 19/19 requirements mapped in REVIEW-CODE.md |
| CodeRabbit | 2 | 2 | 0 | initial review: seven source files; follow-up: three changed source files, zero findings |
| Codex external | - | - | - | not spawned under project subagent restriction |
| Copilot | - | - | - | disabled in configuration |
| Test suite | - | - | - | 1312 passed, 0 failed (163 tests); 37 focused tests passed |

## Corrected findings

1. **Important — Initial reviews could inherit material-only prompting.** The prompt now conditions that policy on follow-up/uncertain history and explicitly preserves normal first-review severities. Existing initial-review regression retains Minor findings.
2. **Important — Canonical carried concerns could be classified as new.** The assessor now requires their exact thread source and a non-new relation. The new regression failed before the change and now passes.
3. **Important — Pending inline draft threads could establish follow-up.** Fetch parent review state and exclude PENDING roots. A real history-normalization regression demonstrated the bug and its fix.
4. **Important — Fresh history could relabel old judgments.** The coordinator now retains assessment-context.json from the time of semantic assessment instead of rebuilding provenance from refreshed history. An executable coordinator regression prevents a false clean conclusion.
5. **Minor, CodeRabbit — Calibrator's direct input list omitted history.** Added the absolute history/scope/verification inputs to match the Skeptic and the global dispatch contract.
6. **Minor, CodeRabbit — Manual comment ID wording was ambiguous.** Specify string GraphQL node IDs, never databaseId, matching collector output and normalized attribution validation.

7. **Important, regression — Context capture ran in local non-PR review.** The existing scope regression caught the missing PR guard after context binding was added. The block now has the same PR-only guard as the other evidence blocks; that previously failing regression passes.

## Validation and limits

See REVIEW-CODE.md for the requirement map and verification results. Earlier integration tests also caught malformed GraphQL connection handling and Bash 3.2 nounset pagination. Baseline/unchanged-code semantics remain in the unchanged scope engine.

CodeRabbit's follow-up review completed with zero findings before the final assessment-context correction; that small wiring change is covered by the executable regression and in-session review. No independent Codex worker or live PR walkthrough was run. No remaining material findings or deferred implementation work were identified.
