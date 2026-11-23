# Data Model: Bulk Issue Assessment

All files are JSON written atomically (temp file, fsync, rename, fsync of the directory). Paths are relative to the run directory `<root>/<run-id>/`. The state root is always the per-user directory `${XDG_STATE_HOME:-~/.local/state}/cc-review/issue-bulk/<owner>__<name>/`, never inside a checkout. `<run>/lock` holds `{session, updated_at}` of the active session (refused for other sessions for 30 minutes); `<run>/.lock` is the per-call file lock.

## Run (`state.json`, owned by `run_state.py`)

| Field | Type | Rules |
|---|---|---|
| `schema_version` | int | `1` |
| `kind` | string | `issue` for this feature; kind-agnostic module |
| `run_id` | string | `YYYYMMDD-HHMMSS-<kind>[-N]` |
| `status` | enum | `running`, `finished`, `abandoned` |
| `repository` | string | `owner/name` |
| `user` | string | posting login (`gh api user`) |
| `options` | object | normalized `search`, `limit`, `scan`, `repo` from `validate` |
| `created_at`, `updated_at` | ISO 8601 | updated on every write |
| `extra` | object | kind-specific run data; for issues: `fixes_available` (bool), `fixes_unavailable_reason`, `default_branch`, `checkout_root`, `handoff_prs` (list of int), `order`, `git_baseline` (git file digests recorded at the first fix), `git_tainted` (reason, stops all fix git), `halted` (reason, set by `guard-end`) |
| `items` | object | key = item id string (issue number), value = Item |

State transitions: `running` → `finished` (report printed) or `abandoned` (fresh start chosen while unfinished).

## Selection (`selection.json`, owned by `issue_bulk.py select`)

| Field | Type | Rules |
|---|---|---|
| `query` | string | full effective search string |
| `scanned` | int | unique candidates classified |
| `ceiling_reached` | bool | true when scanning stopped at `scan` with the batch short |
| `exhausted` | bool | no more candidates |
| `selected` | list of Candidate | at most `limit`, newest first |
| `skipped` | list of `{number, url, title, reason, pr}` | `reason` in `already_assessed`, `maintainer_replied`, `maintainer_pr`, `history_too_long`; `pr` set for `maintainer_pr` |

Invariant: `len(selected) + len(skipped) == scanned` (SC-004).

## Candidate

`{number, url, title, author, created_at, linked_prs: [{number, url, state, merged, author, maintainer_owned, open_non_maintainer}]}`. Only pull requests based on the target repository appear.

## Item (`state.json` `items[<n>]`)

| Field | Type | Written by | Rules |
|---|---|---|---|
| `number`, `url`, `title`, `linked_prs` | | `start` | from selection |
| `phase` | enum | see below | `selected` → `collected` → `assessed` → `decided` → `posted` or `fix_pending` (an open fix after a skipped or withheld reply) → `done`; or `assessment_failed` |
| `failure` | string or null | `collect`, `render-item` | reason for `assessment_failed` |
| `kind`, `recommendation`, `label` | string or null | `render-item` | from the assessment and label config |
| `fix_eligible` | bool | `render-item` | FR-013, FR-017, FR-021 |
| `fix_ineligible_reason` | string or null | `render-item` | shown in the approval prompt |
| `rendered_sha256` | string | `render-item` | hash of `rendered.md` |
| `decision` | object or null | `decide` | `{post: "post"\|"skip", action: "fix"\|"leave"\|"review"\|null, rendered_sha256}` |
| `post` | object | `decide`, `post` | `{comment: "pending"\|"posted"\|"failed"\|"withheld"\|"skipped", comment_url, label: "pending"\|"applied"\|"missing"\|"failed"\|"none", reason}` |
| `fix` | object or null | `fix-*` | Fix result |
| `attempt_session` | object | `post`, `fix-prepare`, `fix-publish`, `fix-cleanup` | session id of the last attempt; `next` skips it within that session |

Phase transitions: `start` sets `selected`; `collect` sets `collected` or `assessment_failed`; `render-item` sets `assessed` (re-render after an edit keeps `assessed` and clears `decision`); `decide` sets `decided` and, for `--post skip`, `post.comment` "skipped" (and `done` when no fix is chosen); `fail` sets `assessment_failed`; `post` sets `posted` once comment and label are final (or withheld/skipped); after the fix (or with no fix chosen) `fix-cleanup` or `post` sets `done`.

## Fix result (`items[<n>].fix`)

| Field | Type | Rules |
|---|---|---|
| `branch` | string | `cc-review/fix-issue-<n>` |
| `worktree` | string | `worktrees/<n>` |
| `snapshot` | object | checkout snapshot from `fix-prepare`: `head`, `index_sha256` (`git ls-files --stage -z`), `status_sha256` and `status_paths` (status code and content digest per listed path), `branches_sha256`, `git_sha256` and `git_metadata` (git file digests), `state_sha256` (canonical state without the run's `updated_at` and the fix snapshot) |
| `steps` | object | `{prepared, worker_done, measured, committed, pushed, pr_opened}` booleans |
| `size` | object | `{files, lines, test_lines}` from `fix-measure` |
| `tree` | string | `git write-tree` id recorded by `fix-measure` |
| `commit` | string or null | sha |
| `pr_url` | string or null | draft PR link |
| `pending` | string or null | `"push"` when the push failed or is unconfirmed, `"pr"` when pushed but the PR is not yet opened |
| `abandoned` | string or null | reason (worker gave up, bound exceeded, binary change, no change, checkout or git files changed during the fix, worktree or branch changed after measuring, issue changed before the fix, branch conflict, push URL elsewhere, commit failed) |

## Per-item files (`items/<n>/`)

- `snapshot.json`: output of `assess_issue.collect_issue` plus `linked_prs` from the selection.
- `assessment.json`: worker output, see [contracts/worker-files.md](contracts/worker-files.md).
- `rendered.md`: exact comment text that `post` publishes.
- `fix.json`: fix worker output.
- `pr-body.md`: draft PR body.

Worktrees live in `worktrees/<n>/` and are removed by `fix-cleanup`.
