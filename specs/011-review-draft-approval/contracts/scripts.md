# Contract: Draft and Post Scripts

## `review/core/scripts/review_draft.py`

Python 3, standard library only, invoked as `python3 -B`. Every subcommand exits 0 on success, 1 on a validation failure (lint findings, new conversation items), 2 on usage or input errors (message on stderr).

| Subcommand | Arguments | Behavior | Output |
|---|---|---|---|
| `facts-set` | `--facts <file> (--curated true\|false \| --executed '<json>')` | Atomically updates the facts file (creates it when missing); `--executed` records one entry per fix round after validating its fields (an entry of the same round is replaced). | none |
| `assemble` | `--slots <file> --facts <file> --out <draft dir> --inputs-key <sha> [--max-comments <n>]` | Builds `payload.json` from slots and facts: inline comment bodies from the fallback template (labels, then source footer), summary body in FR-004 order, findings table, Review Details with the attribution statement as first line, counts, marker and completion lines. Writes `draft.json` (fingerprint, inputs key, check attempts, inline comment limit, summary-only findings; attempts and limit start afresh when the inputs key changes) and removes a stale `lint.json` and `preview.md`. Never reads prose from anywhere but slot text. | `FINGERPRINT <sha>` |
| `attribution` | `--facts <file> [--repro]` | Prints the attribution statement (R-006). Used by `assemble` and tests. | statement |
| `preview` | `--draft <dir>` | Renders `preview.md`: review type in plain words, full body, each inline comment with `path:line` (or range), summary-only findings with reason, proposed thread actions, remaining lint findings. | path |
| `lint` | `--draft <dir> --facts <file> --expected-head <sha> --run-marker <m> [--count-attempt]` | Writes `lint.json` with the FR-012 rules (R-007). | `LINT ok` or `LINT findings=<n>`; exit 1 when findings exist |
| `fingerprint` | `--draft <dir>` | Recomputes the fingerprint of `payload.json` + `thread-actions.json`; a draft of thread actions alone has no `payload.json` (fingerprinted as `null`). | `<sha>` |
| `conversation-diff` | `--analysis <scope dir> --current <dir> --user <login> [--ignore-author <login>]...` | Lists items authored by someone other than the user, not a bot and not an ignored author, that are absent from the analysis snapshot and, when `<scope dir>/analyzed-at.json` and the item's `createdAt`/`submittedAt` are known, were created after the analysis time (minus 5 minutes for clock skew). Edits never count. | JSON array of `{kind, id, author}`; exit 1 when non-empty |
| `history-diff` | `--analysis-history <file> --current-history <file> --scope <scope dir> --user <login> [--ignore-author <login>]...` | The same rule over the items of two Follow-up Continuity histories (sources and context comments). | JSON array of `{kind, id, author}`; exit 1 when non-empty |
| `inputs-key` | `--expected-head <sha> --findings <file> --facts <file>` | Hash of the draft inputs (R-010). | `<sha>` |

## `review/core/scripts/post-review.sh`

Bash; sources `platform.sh` and `rate-limit.sh`.

```
post-review.sh --draft <dir> --owner <o> --repo <r> --pr <n> --user <login>
               --expected-head <sha> --run-marker <m> --scope <scope dir>
               --approved-fingerprint <sha> [--history <history.json>] [--just-pushed]
               [--accept-changes <hash>] [--ignore-author <login>]... [--check-only]
```

`--check-only` runs steps 1 to 5 before a thread reply or resolution and answers `OK` (exit 0) instead of posting: the draft may hold `thread-actions.json` alone, step 1 skips the payload shape check, step 2 runs only with a `payload.json`, and step 4 never stops (the run's own review is expected). `--ignore-author` (repeatable, from `pr_posting.ignore_authors`) is passed to `conversation-diff` and `history-diff`.

`--accept-changes <hash>`: step 5 passes when the SHA-256 of the current `CHANGED` reason equals `<hash>` (the user chose "post anyway" for exactly these changes). Any further change still returns `CHANGED`.

Order of operations (stops at the first non-OK result, writes nothing before step 6):

1. Copy `payload.json` and `thread-actions.json` to a private temporary directory and fingerprint the copies; differs from `--approved-fingerprint` → `REFUSED fingerprint`. The payload's `event` is not `COMMENT` or `REQUEST_CHANGES`, or its body has no line equal to `<!-- cc-review:run-id:<m> -->` → `REFUSED payload`. Later steps read and post only the copies.
2. `payload.json` has no `commit_id`, or it differs from `--expected-head` → `STALE commit`.
3. Live PR head differs from `--expected-head` (with `--just-pushed`: retry up to 3 times, about 5 s apart) → `STALE head`.
4. A review by `--user` with a body line equal to `<!-- cc-review:run-id:<m> -->` exists → `FOUND <review_id>`.
5. The threads or comments could not be read completely, `history-diff` between the analyzed history (`--history`) and the history rebuilt from the fresh data is non-empty, or `conversation-diff` against freshly fetched threads, comments and reviews is non-empty → `CHANGED <hash> <reason>` (the reason names the incomplete read, "history changed: <items>", "history could not be rechecked" or the new conversation items; `<hash>` is the SHA-256 of the reason, to pass to `--accept-changes`).
6. POST the copied `payload.json` byte for byte via `post_review`. HTTP 422 mentioning the commit → `STALE head` (with `--just-pushed`, first retry the POST up to 3 attempts about 5 s apart). Timeout or 5xx: wait about 20 s and repeat step 4; found → `FOUND <id>`. Other failure → write the recovery file (existing 7.5m content) next to the draft, `FAILED <auth|other> <message>`.
7. Success → `POSTED <review_id> <html_url>`.

A `FAILED other` line before step 6 (the PR, its reviews or its conversation could not be read) writes no recovery file.

Exit codes: 0 for `POSTED` and `FOUND`; 1 for `REFUSED`, `STALE`, `CHANGED`, `FAILED`; 2 usage; 75 rate limit (stderr `Error: RATE_LIMITED`). Stdout is exactly one result line.

Thread actions are not performed by this script; see the worker protocol.

## `review/core/scripts/bulk-state.sh`

- `PR_STATUSES` gains `withheld`; it is treated like `stale` for selection in the next run and as finished for the current run.
- `summary` lists `withheld` PRs under "Needs attention" with their reason.
