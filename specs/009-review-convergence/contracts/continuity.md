# Internal Continuity Contract

No new user-facing flags or services. Commands read JSON files and print JSON, returning nonzero for malformed input.

- `python3 review/core/scripts/review_continuity.py prepare --input history-input.json`
- `python3 review/core/scripts/review_continuity.py assess --input assessment-input.json`

`prepare_history(snapshot: dict) -> dict` consumes identity/head, `reviews`, `threads`, `comments`, and the three `*_complete` booleans. Optional `review_comment_ids` identifies manually written review findings after semantic inspection of the collected issue comments; validate IDs and personal ownership, never infer review from casual participation. Returns normalized History in data-model.md. Source links use hosted URLs, with identity-derived GitHub fallback URLs when IDs permit. No personal code baseline is created.

`assess(history: dict, head_oid: str, fingerprint: str, findings: list, decisions: list, concerns: list, coverage_complete: bool, verification_complete: bool) -> dict` returns Result. Unknown, duplicate, missing or stale assessments prevent a clean conclusion. Relation and materiality are semantic inputs whose evidence contract is checked; the engine never infers acceptance from author prose.

`fetch_issue_comments(owner, repo, pr_number)` follows the same array-plus-exit-status convention as existing platform collectors. It includes author, body, id/databaseId, URL, timestamps; handles at most 20 pages of 100. API failures, malformed GraphQL connections and truncation return valid partial arrays with failure status and warnings. Reads only, no hosting mutations.

The coordinator passes absolute history/result paths through prompt reviewers, merge, critics, report and fix-round workers. After scope filtering/calibration it prepares exact candidate/concern assessments and invokes `assess`. Before publication it recollects history at the live head; mismatched head/fingerprint invalidates prepared actions. Existing verification alone authorizes owned thread resolution. Bulk keeps all artifacts under each PR's existing scope directory.

Semantic concerns/decisions retain their original `assessment-context.json` (head and history fingerprint captured before assessment). The coordinator uses that fingerprint, not a newly fetched history fingerprint, when constructing assessor input. Fresh history cannot relabel old judgments; it requires actual semantic reassessment.
