# Quickstart: Inbox PR Action Alignment

## Prerequisites

Use Python 3.9+, jq, Git and the existing gh/Claude CLI tools. Work from this feature worktree. Regression scenarios use recorded activity and fake service calls; they do not post to a real PR or write real user state.

## Validate the shared contract

Run `make test`. The PR action tests must show requested review, own-PR triage, reviewer replies, both actions, draft differences, uncertain changed heads, known unchanged contribution, wrong-owner markers and incomplete context. Inbox and bulk paths must agree for equal canonical snapshots and filters.

## Validate reviewer apply

Fixture coverage: `test_bulk_apply_reviewer_plan_rejected_before_writes` rejects reviewer commits and role mismatches before service writes; `test_bulk_apply_reviewer_stale_activity_has_zero_writes` withholds actions on a moved head; `test_bulk_apply_reviewer_exact_marker_recovers_post_before_local_record` reuses the exact authenticated reply ID without reposting; and `test_bulk_apply_reviewer_no_post_outcome_is_recorded` persists still-present activity, rejects resolving it, and leaves an externally resolved thread incomplete when no approved reply was posted. `test_exact_activity_marker_recovers_only_matching_authenticated_reply` checks that a mismatched marker changes the fingerprint. Deferred questions and incomplete outcomes are not recorded.

## Inspect the user flow

`test_shared_actions_use_raw_bodies_and_independent_coverage` and `test_handled_activity_then_review_keeps_actions_independent` exercise the inbox against fixture PRs, including both action categories, handled cache reads, head/reply reactivation and read-only behavior. `test_bulk_select_handled_activity_workflow_order` confirms bulk triage skips only exact handled activity while review remains independently selectable. `test_owned_roots_drafts_and_incomplete_reply_windows` covers draft triage and incomplete coverage. Review the displayed collection bounds before comparing it with a bulk run under a different scope.

Use deferred bulk triage to inspect prepared author/reviewer plans and the role column. Approve only intended actions. Reviewer triage must never offer or perform a fix commit or push to another author's branch. Use a disposable test repository for any live apply walkthrough.

## Quality gate

Final verification on 2026-10-28: `make test` passed **1,293 assertions across 155 tests, 0 failed**; `make validate` passed both plugin validations (it reported the existing optional missing-icon warning); and `git diff --check` passed. Incremental diff computation remains a separate follow-up; this feature labels uncertain re-review candidates honestly rather than claim it computed a substantive delta.
