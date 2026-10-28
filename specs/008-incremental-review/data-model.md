# Data Model

## Completion v1

`identity` (host/repository/user/pr), `run_id`, `mode` (full/incremental/unchanged), `head_oid`, `base_oid` (merge-base), `coverage_key` (SHA-256), `complete` (true), `parent_run_id` (null for full), `root_run_id` (self for full). Match containing review author, run marker and submitted commit. Incremental parents match identity and coverage and lead without cycles to the named full root.

## Scope

`mode`, `identity`, `head_oid`, `base_oid`, `coverage_key`, validated `baseline` or null, `reason`, `complete`, `clean`, `required_reviewers`, `changes` (path/current-line intervals; old coordinates for deleted files), `diff`, `review_required`, `acknowledgment_required`. Full fallback can be complete when full inputs exist. Missing current objects or dirty pinned checkout prevents completion. Completion requires the exact expected reviewer result set, including failures rather than omissions.

## Verification

Target batch: `complete`, `identity`, `head_oid`, `targets`, `warnings`. Each target holds thread/root identity, concern and exact `activity`. Outcomes hold exact activity, `status`, concrete `evidence`, `code_checked` and accepted-explanation approval when relevant. Still-present outcomes also carry a normalized `finding`, which survives absent rediscovery and remains in reports/gates without a new inline comment. Missing, duplicate, stale or unclear outcomes prevent completion. Only confirmed-fixed or approved accepted-explanation outcomes are resolution candidates. Fresh publication rechecks current target conversations against prepared outcomes.

## Finding additions

Optional `scope` (`latest_delta`, `carried`, `unchanged_critical`), `evidence` (concrete code evidence) and `prior_thread_id` (exact verified thread). Other finding fields remain compatible.
