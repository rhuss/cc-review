# Deep Review Findings

**Date:** 2026-10-26
**Branch:** 006-repository-inbox
**Fix rounds:** 1
**Gate Outcome:** PASS
**Invocation:** speckit-spex-ship (Smart)

## Summary

| Severity | Found | Fixed | Remaining |
|---|---|---|---|
| Critical | 0 | 0 | 0 |
| Important | 0 | 0 | 0 |
| Minor | 1 | 1 | 0 |
| Notable | 0 | 0 | 0 |
| Total | 1 | 1 | 0 |

Review used six in-session perspectives and CodeRabbit. Independent Codex subagents were not used, following project instructions. CodeRabbit's initial review completed with one finding; its targeted re-review completed with zero findings. Both outputs passed the bundled JSON-lines parser.

## FINDING-1: Managed account identifiers rejected

- **Severity:** Minor
- **Confidence:** 75
- **File:** review/core/scripts/inbox.py:19 and authenticated login validation
- **Category:** compatibility
- **Source:** CodeRabbit
- **Resolution:** fixed and re-reviewed

The owner and login allowlists accepted letters, digits and hyphens but rejected underscores. This prevented collection for valid managed account identifiers before discovery.

GitHub documents an underscore suffix for managed accounts in its [username considerations](https://docs.github.com/en/enterprise-cloud%40latest/admin/managing-iam/iam-configuration-reference/username-considerations-for-external-authentication). The fix accepts underscores without permitting whitespace, query operators, shell syntax or an arbitrary leading character.

Regression tests cover both authenticated managed usernames and underscore namespaces. They failed before the fix and pass afterwards. Full project tests and manifest validation pass after the fix.

**External tool rationale:**

> Update the login validation used by collect() and the owner portion of REPO_PATTERN to accept underscores alongside letters, digits, and hyphens. Preserve the existing leading-character and repository-name restrictions so underscores remain safe in search_query qualifiers.

## Post-Fix Compliance

All 20 functional requirements remain implemented. The fix changes two character allowlists and adds focused tests; no feature behavior was removed. Remaining Critical, Important and Minor findings: zero.

CodeRabbit was limited to changed source/command files under review/. The changed test integration, extension registration, documentation and specification were reviewed in-session. The native harness walkthrough is drafted separately and has not been executed.
