# Research

## Baseline evidence

Decision: portable versioned metadata in actual posted reviews, tied to reviewer, PR, commit and completed full-rooted coverage chain. Existing review commits/run markers identify work but do not prove completion. Reject bare legacy markers and foreign reviews. Complete no-findings reviews qualify. A local-only cache was rejected because it does not travel with the PR and triage state must remain independent.

## Rebase comparison

Decision: use direct head diff only with unchanged merge-base and ancestry; otherwise apply the old binary contribution patch onto current upstream with a temporary index and `git apply --cached --3way`. Compare resulting tree to current head. Conflicts and unavailable objects trigger full fallback. Plain head diff includes upstream changes. Text-patch equality can miss equivalent changed context. Range-diff is diagnostic, not a directly reviewable source diff. Existing local Git supports cached three-way application.

## Verification

Decision: reuse `reviewer_activity.py` ownership, conversation completeness, exact fingerprints and idempotency. Reconcile explicit code-backed outcomes, never absence from review. Existing review Step 7.5f still infers fixes; existing triage/bulk guards provide the freshness foundation. Fuzzy line matching cannot prove concern identity or resolution.

## Reviewer scope

Decision: use existing portable command workflows, disclose full-input command reviewers and filter all findings by effective scope. A new descriptor capability requirement would needlessly break existing plugins. Skipping required tools loses coverage. Failed required reviewers make completion unavailable.

No new hosted-service or library dependencies are introduced. Research uses existing source and local tool behavior.
