# Data Model: Review Convergence

## History

`identity` uses the existing host/repository/user/pr contract; `head_oid` pins current code. `follow_up` is true for personal submitted review evidence, false only with complete empty personal history, and null when that determination is incomplete. `complete`, `limitations`, `sources`, `context_comments` and `fingerprint` retain collection quality and exact evidence.

A source has `source_id` (`review:<id>`, `thread:<id>`, `comment:<id>`), `url`, `kind`, and original `data`. Reviews must be submitted by the personal reviewer; pending drafts are excluded. Threads with a personal root include their entire resolved/unresolved conversation. Explicit personal cc-review comments and owned manual findings attributed in `review_comment_ids` count as summary sources; ordinary issue comments remain context. Missing or duplicate source IDs invalidate completeness. No code is executed from source content.

## Semantic assessment input

`history`, `head_oid`, `fingerprint`, `findings`, `decisions`, `concerns`, `coverage_complete`, `verification_complete`.

The semantic arrays are paired with `assessment-context.json`, captured before code/history assessment. Its original fingerprint is preserved through refresh/resume, so stale judgments cannot be silently rebound to new history.

Each concern assessment has `source_id`, `status` (`addressed`, `accepted-explanation`, `open`, `nonblocking`, `unclear`), `code_checked`, `evidence`, `material` boolean and `question_open` boolean. `accepted-explanation` also requires `approved:true`. Assess every constituent concern in a summary; use open/unclear if any substantive constituent remains. An open material concern cannot be downgraded by a promise.

Each candidate decision has `finding_id`, `relation` (`new`, `duplicate-of`, `already-answered`, `contradicts-earlier-advice`), `source_id` for a non-new relation, `code_checked`, `evidence`, `material` boolean and `impact` for a material candidate. A reversal also has `reversal_reason`. Metadata is kept in assessment artifacts, outside the existing strict finding schema.

## Result

`complete`, `conclusion` (`initial-review`, `no outstanding material concerns`, `outstanding material concerns`, `incomplete`), `findings`, `excluded`, `continuations`, `concerns`, `counts`, `limitations`, `fingerprint`, `head_oid`.

`findings` retains eligible new material findings and exact scope-verified carried material findings; other overlaps become continuations, excluded from new inline comments. `counts` includes addressed sources, open material concerns, nonblocking sources and new material findings. An incomplete result retains material candidates conservatively in reports, but never authorizes publication or resolution. Initial reviews pass their existing findings through unchanged. Coverage completion is independent of a clean conclusion.
