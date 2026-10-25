# Contract: Bulk Scripts

All scripts live in `review/core/scripts/` and use `#!/usr/bin/env bash` and `set -euo pipefail`. They are executed, not sourced (apart from `rate-limit.sh`, the rate-limit detection and `try` helper they share), and work as subcommand CLIs like `triage-state.sh`. Errors go to stderr prefixed `Error:`. Exit codes: 0 ok, 1 runtime failure, 2 usage error, 75 hosting-service rate limit (stderr `Error: RATE_LIMITED`). Rate-limit detection (`API rate limit exceeded` or `secondary rate limit` in `gh`/git stderr) happens before any other error mapping, including `DENIED`. JSON goes to stdout. All `gh` and `git` calls are inside these scripts so tests can stub `gh` on `PATH`.

## `bulk-state.sh`

State root: `$CC_REVIEW_BULK_DIR` (default `<git toplevel>/.cc-review/bulk`).

| Subcommand | Output | Behavior |
|---|---|---|
| `init <command> <mode> <selector-json> <options-json> <owner> <repo> <gh-user>` | run id | Creates the run dir and `state.json` (status `selecting`). Ensures `.gitignore` (`*`) exists in the state root. |
| `find-unfinished <command>` | run ids, newest first | Runs whose status is not `finished`/`abandoned` |
| `set-prs <run> <prs-json> <excluded-json>` | `OK` | Stores selection (`status` → `analyzing`). PRs start `pending`. |
| `pr-set <run> <n> <jq-assignments...>` | `OK` | Atomic update of one PR entry, e.g. `.status="analyzed"` `.analyzed_head="<sha>"`. A `failed` status on a PR with recorded actions is stored as `partially-applied`. A new `failed` status counts in `failed_attempts`; the third one appends "not retried after 3 failed attempts" to the reason. |
| `pr-get <run> <n> [<jq-path>]` | JSON | |
| `record <run> <n> pending_push <sha>` | `OK` | Intended push sha, written **before** pushing |
| `record <run> <n> pushed_sha <sha>` | `OK` | Clears `pending_push`, sets `expected_head` to `<sha>` |
| `record <run> <n> review_id <id>` | `OK` | |
| `record <run> <n> reply <comment_id> <reply_id>` | `OK` | |
| `record <run> <n> resolved <thread_id>` | `OK` | |
| `set-status <run> <status>` | `OK` | Run-level status |
| `reanalyze <run> <n>` | `REANALYZE` \| `STALE` | Pre-decision refresh of a PR whose head moved: resets it to `pending` and counts it in `reanalyses`, or, once it was analyzed again, marks it `stale` |
| `open-prs <run>` | PR numbers, one per line | PRs that are not terminal for the run |
| `finish <run>` | run status | Sets `finished` when the run is not paused or abandoned and every PR is terminal |
| `abandon <run>` | `OK removed=<n>` | Sets `abandoned`, removes the run's kept worktrees (`pr-worktree.sh remove`, from `repo.root`), records them in `removed_worktrees` and rewrites `summary.md` |
| `resume-plan <run> <current-heads-json>` | JSON `{reanalyze:[n], keep:[n], apply:[n], interrupted:n\|null}` (`interrupted`: the PR whose analysis was cut off) | Applies the resume transition rules (data-model) and writes them back; a `failed` PR with 3 failed attempts is kept as it is |
| `cut-short <run> [<keep-n>]` | `OK not-analyzed=<count>` | Every `pending` PR except `<keep-n>` becomes `not-analyzed` (terminal, nothing posted, selected again by a later run); a leftover `pr-<n>/wt` checkout is removed (FR-028a) |
| `render <run>` | `OK` | Regenerates `state.md` |
| `validate <run>` | `OK` or error | Schema sanity check (required fields, enums); never rewrites an invalid file |
| `summary <run>` | path | Writes `summary.md`: selected and excluded PRs, outcome, reason, what was done (review link, pushed sha, reply and resolution counts), kept worktrees, and for an abandoned run the removed worktrees. For triage runs it also lists, from each `triage-plan.json`, human comments with no decision ("needs attention") and a "CI not checked; run `/triage --pr <n>` for CI repair" line per pushed PR. |

Every mutating subcommand updates `updated_at` and re-renders `state.md`.

## `bulk-select.sh`

| Subcommand | Output |
|---|---|
| `review [--all-open \| --search <q>] [--limit <n>] --user <login>` | `{"selected":[PrEntry-seed], "excluded":[Exclusion]}` |
| `triage [--search <q>] [--limit <n>] --user <login>` | same shape |
| `check-query <q>` | exit 2 with the qualifier error when the query is not allowed (case-insensitive, negated qualifiers included); exit 0 otherwise |

PrEntry seed fields: `number, title, author, head_ref, base_ref, head_repo_url, is_cross_repo, authored_by_user` (the head is read at checkout, not at selection). Ordering: the PR's `updatedAt` ascending; `over-limit` exclusions for the remainder. A marker review counts for `reviewed-at-head` and for the re-review set only when its author is not the PR's author (FR-006).

## `pr-worktree.sh`

| Subcommand | Behavior |
|---|---|
| `add <pr> <sha> <path> [<base_ref>]` | Removes a leftover worktree or directory at `<path>` first. Runs `git fetch origin pull/<pr>/head` (and `<base_ref>` when given, so `origin/<base_ref>` is current), verifies `<sha>` is reachable, then `git worktree add --detach <path> <sha>`. Prints the absolute path. |
| `remove <path>` | `git worktree remove --force <path>` + prune; succeeds when already gone |
| `local-ahead <branch> <sha> [<head-repo-url>]` | prints the count of local commits on `refs/heads/<branch>` not reachable from `<sha>` (0 when the branch does not exist). With a head repository URL (cross-repository PRs), the branch counts only when its upstream or push remote points at that repository; otherwise 0. |
| `push <path> <url> <branch> <expected-sha>` | Non-force push of `HEAD` to `refs/heads/<branch>`. If the remote branch already equals the local `HEAD` (a push completed before a crash), it prints `PUSHED <sha>` without pushing. If the remote equals neither `<expected-sha>` nor `HEAD`, it prints `STALE`. Otherwise it pushes and prints `PUSHED <sha>`, `STALE` (non-fast-forward rejection), or `DENIED` (permission), all with exit 0. Rate limit exits 75; other failures exit 1. |
| `head <pr>` | current remote head sha of the PR |
| `is-pr-branch <pr>` | exit 0 when the current branch is the PR's head branch (FR-035). For a cross-repository PR, the branch name alone is not enough: the current branch must also track the PR's head repository. |

## `bulk-apply.sh`

| Subcommand | Behavior |
|---|---|
| `head <run> <n>` | The FR-030 head check, without changing the state: `OK <sha>` when the PR's head is `expected_head` or a recorded `pending_push`, `MOVED <sha>` otherwise, `CLOSED <state>` for a PR that is no longer open. When this run pushed to the PR and GitHub reports another head, the branch tip (`git ls-remote` of the head repository) decides. Used by the pre-decision refresh and before every push, post and marker. |
| `triage <run> <n>` | Executes `pr-<n>/triage-plan.json` in order:<br>1. Set PR status `applying`.<br>2. Push, if `prepared_commit` is set and not recorded: `record pending_push`, then `pr-worktree.sh push`, then `record pushed_sha`. After a push, the branch tip (`git ls-remote`) must equal the pushed commit; otherwise the PR is `stale` and nothing is posted.<br>3. Re-map comment and thread ids by path+line+author through `fetch_pr_threads`.<br>4. For each reply not yet recorded: if the thread already holds a reply by `gh_user` carrying `<!-- cc-review-triage` and created at or after the run's `created_at`, record that reply's id instead of posting; otherwise post (an older signed reply is an earlier exchange). Then record (bulk state and `triage-state.sh set` with `TRIAGE_STATE_FILE`).<br>5. Resolve each thread not yet recorded, and record it.<br>`STALE`/`DENIED` sets the PR status and stops for that PR. Final status is `actioned`, or `partially-applied` when any step failed. |
| `review-push <run> <n>` | Pushes fix commits for "apply fixes" with the same `pending_push` → push → `pushed_sha` sequence |
| `marker <run> <n>` | Posts the no-findings marker review (`COMMENT`, `commit_id` = expected head) unless a review by the user with this run's marker already exists on the PR; records `review_id` |

## `platform.sh` changes

- `_github_fetch_reviews` adds `commit { oid }` and `author { login }` to each review node.
- No signature change to `post_review`. The payload file gains `commit_id` (written by the review command).
