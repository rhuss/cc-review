# Validation: Review Convergence

From the feature worktree:

1. Run `python3 -B tests/test_review_continuity.py`. Semantic fixtures cover manual and summary-only histories, author questions/promises, prior advice reversal, optional polish, real regressions and incomplete evidence.
2. Run `make test` to check unchanged scope, verification, bulk, adapter and approval behavior.
3. Run `make validate` and `git diff --check`.
4. In a fresh plugin session, review a PR with earlier personal discussion. Confirm history reaches reviewers, existing concerns retain source links and no optional new nits appear. Use the drafted RUNBOOK.md for the detailed walkthrough after pipeline review. Posting remains a separate approved action.
