---
description: "Task list for Bulk Review and Bulk Triage"
---

# Tasks: Bulk Review and Bulk Triage

**Input**: Design documents from `specs/005-bulk-review-triage/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (cli-flags.md, scripts.md, worker-protocol.md), quickstart.md

**Tests**: Included. The project keeps a bash test suite (`tests/run.sh`, `make test`), and the plan calls for script tests with a fake `gh` and temp git repos, plus contract greps on the command Markdown. Every new test function must be added to the explicit list in `main()` of `tests/run.sh`.

**Organization**: Tasks are grouped by user story so each story can be implemented and tested on its own.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on incomplete tasks)
- **[Story]**: The user story the task belongs to (US1 to US6)

## Conventions for all tasks

- New scripts: `#!/usr/bin/env bash`, `set -euo pipefail`, subcommand CLI via `case "${1:-}"`, `do_*` functions, `Usage:` errors with exit 2, `Error:` prefix on stderr, atomic jq-to-temp-then-`mv` writes, temp cleanup trap. Follow `review/core/scripts/triage-state.sh`.
- Command Markdown: shell blocks must work under bash and zsh; pass optional values as `"${VAR:--}"` (see `review.md` Prerequisites); every shell block sets `CC_REVIEW_CORE_DIR` (the harness may start a new shell per block); no harness-specific tool names, say "dispatch a subagent".
- Tests: `test_<name>()` functions using `assert_eq/assert_contains/assert_not_contains/assert_json`, `$TEST_TMP` per test, registered in `main()`.
- Never force-push. Never write outside `.cc-review/` in the invoking repo.

---

## Phase 1: Setup

**Purpose**: Test scaffolding and reserved names that every later phase relies on.

- [x] T001 Create the fake `gh` and fixtures for bulk tests: `tests/fixtures/bulk/bin/gh` (bash script that logs its argv to `$FAKE_GH_LOG` and serves canned JSON from `$FAKE_GH_DIR` keyed by subcommand: `api user`, `pr list` with `--search` value, `pr view`, `api graphql` (by query keyword `search`/`reviewThreads`/`reviews`/`resolveReviewThread`), `api .../replies` (POST returns `{"id":<n>}` incrementing), `api .../reviews` POST returns `{"id":<n>}`), plus fixture files under `tests/fixtures/bulk/` for: review-requested list, reviewed-by list, all-open list (including a draft and a PR reviewed at head), triage GraphQL search with unresolved thread counts. Add a `with_fake_gh` helper in `tests/run.sh` that prepends `tests/fixtures/bulk/bin` to `PATH` for one command. Add a `make_bulk_repo` helper that creates a temp bare repo (the push target, used as `head_repo_url`) and a clone whose `origin` fetch URL is the bare repo but whose push and remote URL report `https://github.com/acme/widget.git` (`git remote set-url origin` to the github URL, plus `git config url.<bare>.insteadOf https://github.com/acme/widget.git`), so `detect_platform` sees GitHub while git traffic stays local. Add a 50-PR fixture `tests/fixtures/bulk/all-open-50.json` for the timing check in T047.
- [x] T002 [P] Add `bulk all-open search limit unattended resume` to `CC_REVIEW_RESERVED_NAMES` in `review/core/scripts/discover-reviewers.sh` and to the reserved-name list in `review/core/schemas/reviewer.schema.json`; run `bash tests/run.sh schema_agrees` and keep `test_schema_agrees_with_validator` green.

---

## Phase 2: Foundational (blocks all user stories)

**Purpose**: Run state, isolated checkouts, review-with-commit metadata, the orchestrator skeleton, and argument plumbing.

**⚠️ CRITICAL**: No user story work starts before this phase is complete.

### Tests for Phase 2

- [x] T003 [P] Write tests for `bulk-state.sh` in `tests/run.sh`:
  - `test_bulk_state_init_creates_run_and_gitignore`: the run dir exists, `state.json` has `version:1` and status `selecting`, and `.cc-review/bulk/.gitignore` contains `*`.
  - `test_bulk_state_set_prs_and_pr_set`: transitions recorded and `updated_at` changes.
  - `test_bulk_state_record_subactions`: `pushed_sha`, `review_id`, reply and resolved ids.
  - `test_bulk_state_find_unfinished`: newest first; finished and abandoned excluded; filtered by command.
  - `test_bulk_state_render_md`: `state.md` lists every PR with its status and counts.
  - `test_bulk_state_validate_rejects_corrupt`: the invalid file is not rewritten and the error names the file.
  - `test_bulk_state_summary`: selected and excluded PRs with reason, and kept worktrees; for a triage run, undecided human comments from `triage-plan.json` and a "CI not checked" line per pushed PR.
  - `test_bulk_state_record_forms`: each `record` form from `contracts/scripts.md` (`pending_push`, `pushed_sha` clears `pending_push` and sets `expected_head`, `review_id`, `reply`, `resolved`).
  - Use `CC_REVIEW_BULK_DIR="$TEST_TMP/bulk"`.
- [x] T004 [P] Write tests for `pr-worktree.sh` in `tests/run.sh`, using a temp bare repo as `origin`, a clone, and a ref `refs/pull/7/head` created in the bare repo:
  - `test_pr_worktree_add_detached`: a detached worktree at the sha; the user's branch and `git status --porcelain` are unchanged.
  - `test_pr_worktree_add_while_branch_checked_out`: the user has the PR's branch checked out locally and add still succeeds.
  - `test_pr_worktree_local_ahead`: returns 0, then 1 after a local commit on the branch.
  - `test_pr_worktree_push_ff`: prints `PUSHED <sha>`.
  - `test_pr_worktree_push_stale`: the remote moved first, so it prints `STALE` and the remote is unchanged.
  - `test_pr_worktree_push_already_done`: the remote already equals the local HEAD (crash after push), so it prints `PUSHED <sha>` without pushing.
  - `test_pr_worktree_add_replaces_leftover`: a leftover directory at the path is replaced.
  - `test_pr_worktree_rate_limit_exit_75`: a fake git/gh stderr containing `API rate limit exceeded` gives exit 75.
  - `test_pr_worktree_remove_idempotent`.
  - `test_pr_worktree_is_pr_branch` (stubbed `gh pr view` via fake gh).

### Implementation for Phase 2

- [x] T005 Implement `review/core/scripts/bulk-state.sh` per `contracts/scripts.md` (`init`, `find-unfinished`, `set-prs`, `pr-set`, `pr-get`, `record`, `set-status`, `render`, `validate`, `summary`; `resume-plan` comes later in T032). Use state root `${CC_REVIEW_BULK_DIR:-$(git rev-parse --show-toplevel)/.cc-review/bulk}` and run id `$(date -u +%Y%m%d-%H%M%S)-<command>`, with a numeric suffix on collision. `render` writes `state.md`: a run header (id, command, mode, selector, status), a table with columns PR, title, author, status, counts, proposed, decision, reason, report, and an Excluded section. Make T003 pass.
- [x] T006 Implement `review/core/scripts/pr-worktree.sh` per `contracts/scripts.md` (`add`, `remove`, `local-ahead`, `push`, `head`, `is-pr-branch`):
  - `add` clears a leftover path first and fetches the optional base ref.
  - `push` uses `git -C <path> push <url> HEAD:refs/heads/<branch>` (never `--force`).
  - Before pushing, `push` reads `git ls-remote <url> refs/heads/<branch>`: if it equals the local HEAD, print `PUSHED <sha>` and skip the push; if it equals neither `<expected-sha>` nor HEAD, print `STALE`.
  - Check stderr for rate limits first (exit 75), then map a "non-fast-forward"/"fetch first" rejection to `STALE`, and a 403 or "permission"/"denied" error to `DENIED`.
  - Make T004 pass.
- [x] T007 [P] Extend `_github_fetch_reviews` in `review/core/scripts/platform.sh` to request `commit { oid }` and `author { login }` on each review node, keeping the output shape a superset of today's. Add `test_platform_fetch_reviews_includes_commit` in `tests/run.sh` using the fake gh, asserting that the query text contains `commit` and that the parsed output keeps the fields.
- [x] T008 Create the orchestrator skeleton `review/core/commands/bulk.md` with these sections:
  - Prerequisites (core dir and config resolution identical to `review.md`).
  - Inputs: `BULK_COMMAND`=review|triage, `BULK_MODE`=deferred|unattended (unattended when `--unattended` is given or config `interactive` is false), the parsed bulk flags, and `PROJECT_DIR` (the invoking repo's toplevel, the single name used for it in all bulk sections).
  - `--resume` argument parsing per `contracts/cli-flags.md` (optional run id matched by pattern). With no unfinished run: unattended starts a new run with the given flags; deferred prints "No unfinished <command> run to resume." and stops.
  - Flag validation, implementing every row of `contracts/cli-flags.md` with the exact error texts. `interactive: false` maps to unattended.
  - Unfinished-run check per FR-031: deferred asks resume/abandon/cancel; unattended errors.
  - Selection hand-off: call `bulk-select.sh "$BULK_COMMAND" ...`. If nothing is selected, print "No PRs matched" with the selector and exclusion counts and stop without creating state. Otherwise `init` and `set-prs`.
  - Analysis loop: sequential; `pr-worktree.sh add "$n" "$sha" "$PR_DIR/wt" "$base_ref"` with per-PR failure handling (FR-015); worktree keep/remove rule (FR-012); exit 75 or a worker's `STATUS failed reason=rate-limited` sets the run to `paused` and stops the loop. Any early stop inside the per-PR pipeline marks only that PR as failed. Leave a placeholder sub-step "run the command's analysis worker (see Review Analysis / Triage Analysis)".
  - Before rendering the decision table, re-read each non-terminal PR's state and head (`gh pr view --json state,headRefOid`): closed or merged → `closed`; a moved head → `stale`.
  - Decision step framework per research R-009: print the table, then one choice of Apply proposed / Change actions per PR (batches of up to 4 PRs) / Skip all / Stop (resume later).
  - Apply loop framework: before every push or post, re-check state and head against `expected_head` (or a recorded `pending_push`), setting `closed`/`stale` accordingly.
  - Summary (`bulk-state.sh summary`), with the run set to `finished` when all PRs are terminal.
  - Command-specific sections are left as headings for later phases.
- [x] T009 Add the bulk hand-off to `review/core/commands/review.md`:
  - Update the `argument-hint` frontmatter with the new flags.
  - At the top of Prerequisites, add a "Bulk Mode" subsection: if `--bulk` or `--resume` is present, set `BULK_COMMAND=review`, then read and execute `commands/bulk.md` instead of Steps 1-8.
  - Reject review-only invalid combos early (`--bulk` with `--pr`, `--spec`, `--output`).
  - In the reviewer-selection parsing (R:199-203), make sure the value of `--search <query>`, `--limit <n>` and `--resume <run-id>` is consumed with its flag and never parsed as a reviewer flag or name (a query such as `--search 'no-foo'` must not disable a reviewer).
- [x] T010 Add the bulk hand-off to `review/core/commands/triage.md`: update `argument-hint`, add a "Bulk Mode" subsection in the prerequisites (`BULK_COMMAND=triage`, execute `commands/bulk.md`), and reject `--bulk` with `--pr`.
- [x] T011 [P] Add the new flags (`--bulk`, `--all-open`, `--search <query>`, `--limit <n>`, `--unattended`, `--resume [<run-id>]`) to the argument-hint and pass-through list in `review/skills/review/SKILL.md` and `review/opencode/command/review.md`. Add (`--bulk`, `--search`, `--limit`, `--unattended`, `--resume`) to `review/skills/triage/SKILL.md` and `review/opencode/command/triage.md`. Keep each file under 50 lines.
- [x] T012 [P] Add contract tests in `tests/run.sh`:
  - `test_shims_pass_bulk_flags`: every shim lists `--bulk` and `--resume`; review shims list `--all-open`; all shims stay under 50 lines.
  - `test_bulk_md_validation_errors`: each error text from `contracts/cli-flags.md` appears in `bulk.md` or in `bulk-select.sh`/`bulk-state.sh` (the qualifier and unknown-run-id errors come from the scripts).
  - `test_review_and_triage_hand_off_to_bulk`: both commands reference `commands/bulk.md` under a "Bulk Mode" heading.

**Checkpoint**: State, worktrees, and orchestrator skeleton exist; `make test` green.

---

## Phase 3: User Story 1 - Review My Review Queue in One Run (P1) 🎯 MVP

**Goal**: `/review --bulk` selects requested-or-re-review PRs not reviewed at head, analyzes each in an isolated worktree with bounded coordinator context, and posts or skips per PR from one decision table.

**Independent Test**: Quickstart Scenarios 1 and 2.

### Tests for User Story 1

- [x] T013 [P] [US1] Write `bulk-select.sh review` tests in `tests/run.sh` with the fake gh:
  - `test_bulk_select_review_default_union`: the requested set plus the re-review set (a cc-review review by the user at an older head), deduplicated.
  - `test_bulk_select_excludes_reviewed_at_head`: a marker review at the current head gives exclusion reason `reviewed-at-head`; a review at an older head is not excluded.
  - `test_bulk_select_drops_drafts`: reason `draft`.
  - `test_bulk_select_limit_and_order`: `updated_at` ascending; reason `over-limit` for the rest.
  - `test_bulk_select_authored_flag`: `authored_by_user` is true when the author equals `--user`.
- [x] T014 [P] [US1] Write tests for `bulk-apply.sh marker` and `review-push` in `tests/run.sh`:
  - `test_bulk_apply_marker_posts_comment_with_commit_id`: the fake gh log shows a POST to `/reviews` with `event=COMMENT`, `commit_id`, and a body containing `cc-review:run-id:<run>/pr-<n>`; `review_id` is recorded.
  - `test_bulk_apply_marker_skips_when_present`: the run marker is already on the PR, so there is no POST and the found id is recorded.
  - `test_bulk_apply_review_push_records_sha`: temp repos; `expected_head` is updated.

### Implementation for User Story 1

- [x] T015 [US1] Implement `review/core/scripts/bulk-select.sh` (`review` subcommand with the default selector only; `--all-open`, `--search` and `check-query` come in T039) per research R-004/R-005 and `contracts/scripts.md`:
  - Two `gh pr list --state open --search ... --limit 200 --json number,title,author,isDraft,headRefOid,headRefName,baseRefName,updatedAt,isCrossRepository,headRepository,headRepositoryOwner,reviews` calls, merged by number. `base_ref` is set from `baseRefName`.
  - When a PR's `reviews` array has 100 entries (possible truncation), re-fetch that PR's reviews with `fetch_reviews` (paginated) before deciding.
  - A re-review is kept only when a review by `--user` contains `<!-- cc-review:run-id:` with `commit.oid != headRefOid`.
  - At-head exclusion applies to any author's marker review.
  - Drafts are dropped. `head_repo_url` is built from the head repository using `origin`'s protocol (ssh vs https).
  - Output is `{selected, excluded}`.
  - Make T013 pass.
- [x] T016 [US1] Add `REVIEW_ROOT` to `review/core/commands/review.md`, following research R-002:
  - Step 1: define `REVIEW_ROOT` (default `git rev-parse --show-toplevel`; bulk passes the worktree). Run all `git diff`/`git ls-files` calls with `git -C "$REVIEW_ROOT"`. When `BASE_REF` is set (bulk, and isolated single-PR), diff against `origin/<base>` instead of the local `MAIN_BRANCH`.
  - Step 2: test-command auto-detection looks in `REVIEW_ROOT`. Discovery keeps `--project-dir "$PROJECT_DIR"` (invoking repo) and gets `--changed-files` from `REVIEW_ROOT`'s diff.
  - Step 3: Review Target lists absolute paths (`$REVIEW_ROOT/<path>`) and tells reviewers to report `file` relative to the review root. Command reviewers run inside `( cd "$REVIEW_ROOT" && ... )`.
  - Step 6: fixes edit files under `REVIEW_ROOT`.
  - Step 7.5b/c: diff hunks and `git ls-files` use `REVIEW_ROOT`.
  - When `REVIEW_ROOT` is the toplevel, behavior is byte-for-byte today's (FR-036).
- [x] T017 [US1] Add `commit_id` to the review payload in Step 7.5k of `review/core/commands/review.md`:
  - The value is the reviewed head: `gh pr view "$PR_NUMBER" --json headRefOid` captured in Step 1 as `REVIEWED_HEAD`, or `EXPECTED_HEAD` when bulk provides it.
  - Allow bulk to override the marker suffix via `RUN_MARKER` (default `$RUN_ID`), and use `RUN_MARKER` consistently in 7.5d (marker parsing must accept the `<run-id>/pr-<n>` form, not only a UUID), 7.5k, and 7.5m (recovery search).
  - In 7.5d, pick the most recent cc-review review **that has inline comments** as the previous run, so a later no-findings marker review does not hide earlier threads from 7.5e/7.5f.
  - Bulk passes the review type through `REVIEW_EVENT_OVERRIDE=COMMENT` for unattended mode.
  - On HTTP 422 mentioning the commit, report "PR head moved; review not posted" and treat the PR as stale.
- [x] T018 [US1] Add a "Worker Mode (bulk)" section to `review/core/commands/review.md` that defines, per `contracts/worker-protocol.md`:
  - (a) Steps 1-3 run in the coordinator. `$PR_DIR/reviewers.json` is written right after dispatch planning. Command reviewers run in a `( cd "$REVIEW_ROOT" && ... )` subshell with raw output kept in `$PR_DIR/commands/`, and only the exit code is recorded. Every early stop (`exit 1` paths) becomes "mark this PR failed with reason and return to bulk.md".
  - (b) the reviewer prompt's alternative Output section: write the findings JSON array to `$PR_DIR/findings/<name>.json` and positive observations to `<name>.positive.json`, and return only `STATUS ok findings=<n>`.
  - (c) the merge worker prompt, with inputs `reviewers.json`, findings files, `commands/*.out`, `RUNTIME`, `CORE_DIR`, `MIN_CONFIDENCE`. It parses command-reviewer output per each reviewer's parsing notes, normalizes with `$RUNTIME helper map_severity`, applies the `MIN_CONFIDENCE` filter and the Step 4 dedup rules, writes `merged.json`, updates the counts in `reviewers.json`, and returns the counts line.
  - (d) the meta-review workers read `merged.json` and use the existing `core/agents/meta-skeptic.md` and `meta-calibrator.md` prompts plus an explicit override to write `meta/<name>.json` instead of reporting, then return a STATUS line. Same gate as Step 4b.
  - (e) the report worker applies the Step 4b verdict rules and writes `findings.json` and `review-findings.md` (Step 7 format, including the "What Went Well" section from the positive files).
  - (f) the fix round as driven by bulk.md: a fix worker applies fixes for `findings.json`, runs the test command, commits in the worktree, writes `round-<k>/changed-files`, and returns `STATUS ok fixed=<n> commit=<sha>`; the coordinator then re-runs (a)-(e) scoped to those files, with outputs in `round-<k>/`. No worker dispatches subagents.
  - (g) the posting worker (Step 7.5 with all findings accepted, prose rewrite done inline without a further subagent, `commit_id`=`EXPECTED_HEAD`, `RUN_MARKER`, file existence checked with `git -C "$PROJECT_DIR" ls-tree -r --name-only "$EXPECTED_HEAD"` because the worktree may be gone).
  - State that in worker mode the coordinator never reads findings files into its own context (counts via `jq` only). The one exception is the interactive "review findings" drill-down in bulk.md. Step 5a and the 5b menu are skipped.
- [x] T019 [US1] Fill the "Review Analysis" section of `review/core/commands/bulk.md`. Per PR:
  - Set `REVIEW_ROOT` to the worktree, `PR_NUMBER`, `PR_DIR`, `EXPECTED_HEAD`, `BASE_REF`, `RUN_MARKER`.
  - Run review.md Steps 1-3 in worker mode (which writes `reviewers.json` before any worker runs), then the merge, meta and report workers.
  - Set the PR `analyzed` with counts, `report` and `authored_by_user`.
  - Compute `proposed` per FR-021: findings → `post`, none → `marker`.
  - Keep the worktree only when "apply fixes" can be offered: authored, not `local-unpushed` (via `pr-worktree.sh local-ahead`), no `--no-fix`.
  - A worker without a parseable `STATUS` line, or a missing output file, marks that reviewer failed. A failed merge or report marks the PR failed.
- [x] T020 [US1] Fill the "Review Decision and Apply" section of `review/core/commands/bulk.md`:
  - Table columns: PR, title, author, C/I/M/N, report path, proposed.
  - Per-PR allowed actions per FR-019: `post`, `review-findings`, `skip`, `marker`, and `fix` (+`post`) when allowed.
  - `review-findings` runs the single-PR 7.5g presentation in the coordinator from `findings.json` and writes `accepted.json`.
  - Apply order per PR: state and head check → `fix` (coordinator-driven rounds per T018(f), up to `max_fix_rounds`, stopping when no Critical or Important findings remain; then `bulk-apply.sh review-push`) → `post` (posting worker, record `review_id`; with `fix`, posts only the remaining findings) or `marker` (`bulk-apply.sh marker`) → status `actioned` and worktree removal.
- [x] T021 [US1] Implement `review/core/scripts/bulk-apply.sh` subcommands `marker` and `review-push` per `contracts/scripts.md`:
  - `marker` checks `fetch_reviews` for this run's marker before posting.
  - The marker body is "cc-review found no issues at `<short sha>`." followed by the marker line.
  - Payload: `event: COMMENT`, `commit_id`.
  - Make T014 pass.
- [x] T022 [P] [US1] Add contract tests in `tests/run.sh`:
  - `test_review_md_has_review_root`: `REVIEW_ROOT` is used in Steps 1, 2, 3 and 7.5; no bare `git diff --name-only "${MAIN_BRANCH}...HEAD"` without `-C`.
  - `test_review_md_payload_has_commit_id`.
  - `test_review_md_worker_mode_section`: it mentions `findings/<name>.json`, `merged.json`, `findings.json`, `STATUS ok`.
  - `test_review_discovery_block_under_zsh` keeps passing after the block edits; update its awk anchor if the block text changed.

**Checkpoint**: Quickstart Scenarios 1 and 2 pass; MVP shippable.

---

## Phase 4: User Story 2 - Triage All My PRs with Open Comments (P1)

**Goal**: `/triage --bulk` prepares fixes and replies per own PR in isolated worktrees, then pushes, replies and resolves only for approved PRs.

**Independent Test**: Quickstart Scenario 5.

### Tests for User Story 2

- [X] T023 [P] [US2] Write `bulk-select.sh triage` tests in `tests/run.sh`:
  - `test_bulk_select_triage_unresolved_only`: PRs with 0 unresolved threads are excluded with reason `no-open-threads`.
  - `test_bulk_select_triage_search_restricts`: the `--search` text is appended to the GraphQL search query; the fake gh log asserts `author:@me` and `is:open`.
- [X] T024 [P] [US2] Write `bulk-apply.sh triage` tests in `tests/run.sh` with temp repos and the fake gh:
  - `test_bulk_apply_triage_full`: push, then replies, then resolutions; ids recorded; status `actioned`.
  - `test_bulk_apply_triage_rerun_skips_recorded`: a second run makes no new POSTs.
  - `test_bulk_apply_triage_stale_stops`: the remote moved, so status is `stale` with no replies posted.
  - `test_bulk_apply_triage_human_decisions`: only `.human[]` entries with an approve or edit decision are posted.
  - `test_bulk_apply_triage_partial`: the fake gh fails on the second reply, giving `partially-applied`, and a rerun posts only the remaining reply.
  - `test_bulk_apply_triage_unrecorded_reply_not_duplicated`: the fake thread fixture already holds a reply by the user carrying `<!-- cc-review-triage`, but the state has no record; no POST is made and that reply's id is recorded.
  - `test_bulk_apply_triage_push_recorded_before`: `pending_push` is set before the push and cleared after; a rerun where the remote already equals the prepared commit records `pushed_sha` without a second push.

### Implementation for User Story 2

- [X] T025 [US2] Add the `triage` subcommand to `review/core/scripts/bulk-select.sh`:
  - One `gh api graphql` search `repo:<o>/<r> is:pr is:open author:@me <query>` returning number, title, author, isDraft, headRefOid, headRefName, updatedAt, isCrossRepository, headRepository{name owner{login}} and `reviewThreads(first:100){nodes{isResolved}}`.
  - Also request `baseRefName` (→ `base_ref`).
  - Unresolved count is greater than 0, giving selected; otherwise the exclusion `no-open-threads`.
  - Drafts and limit handled as for review.
  - Make T023 pass.
- [X] T026 [US2] Add a "Prepare Mode (`TRIAGE_MODE=prepare`)" section to `review/core/commands/triage.md`, per research R-007 and `data-model.md` TriagePlan:
  - Inputs: `TRIAGE_ROOT`, `TRIAGE_PLAN`, `TRIAGE_STATE_FILE` (export it for every `triage-state.sh` call), `--pr`.
  - All Edit/Read paths are absolute under `TRIAGE_ROOT`, and git runs with `-C "$TRIAGE_ROOT"`.
  - Step 3c is skipped.
  - Step 7 commits in the worktree with no push, and records `prepared_commit`.
  - Steps 8, 9, 9b, 11b reply/resolve, and 12 (collect human comments with drafted options instead of prompting) record entries in `TRIAGE_PLAN` instead of acting. Each reply entry carries `comment_id`, `thread_id`, `author`, `path`, `line`, `body`, `action`, `resolve`, `self_resolves` (data-model TriagePlan).
  - Steps 7b (CI polling and repair), 7c, 10, 12c and 14 are skipped.
  - Steps 3d and 12b only read and format, so they run unchanged and write their output into `triage-summary.md`.
  - Step 13 writes `triage-summary.md` next to the plan instead of printing.
  - The worker returns `STATUS ok valid=.. rejected=.. deferred=.. human=.. commit=<sha|none>`, or `STATUS failed reason=rate-limited` on a hosting-service rate limit.
  - Add "(prepare mode: see Prepare Mode)" next to the "MUST execute" notes on Steps 12c and 13, and on Step 12b's note where it implies posting.
- [X] T027 [US2] Fill the "Triage Analysis" section of `review/core/commands/bulk.md`:
  - Per PR, dispatch one triage worker subagent with the prepare-mode inputs (`TRIAGE_STATE_FILE="$PROJECT_DIR/.cc-review/.triage-state.json"`, `TRIAGE_PLAN="$PR_DIR/triage-plan.json"`) and parse its status line.
  - Worktree keep rule: keep while `prepared_commit` is set and the PR is undecided or partially applied; otherwise remove after analysis.
  - Set counts.
  - `proposed` = `apply` when the plan has a commit, replies, or resolutions.
  - Flag `local-unpushed` (via `pr-worktree.sh local-ahead`): then only replies are offered.
  - Flag `cross-repo` push failures as `cannot-push` at apply.
- [X] T028 [US2] Fill the "Triage Decision and Apply" section of `review/core/commands/bulk.md`:
  - Table columns: PR, title, valid/rejected/deferred/human counts, summary path, proposed.
  - Per PR: `apply`/`skip`.
  - Then each human comment is presented with the T Step 12 options (Approve, Edit with follow-up text, Skip), and the decision is written into `triage-plan.json` with `jq`.
  - Apply runs `bulk-apply.sh triage <run> <n>` per PR.
  - Offer idea-inbox capture once after apply when `--idea-inbox` was given.
- [X] T029 [US2] Implement the `triage` subcommand of `review/core/scripts/bulk-apply.sh` per `contracts/scripts.md`:
  - Push via `pr-worktree.sh push`, recording `pushed_sha` and updating `expected_head`.
  - Re-map thread and comment ids by path+line through `fetch_pr_threads` when the push changed them.
  - Set the PR status to `applying` first. Record `pending_push` before the push.
  - Then replies (`post_reply`): before posting an unrecorded reply, look in the re-fetched thread for a reply by `gh_user` carrying `<!-- cc-review-triage` and record it instead of posting. Record reply ids in bulk state and in `triage-state.sh set` (with `TRIAGE_STATE_FILE`).
  - Then resolutions (`resolve_thread`), recording each.
  - Skip already-recorded sub-actions.
  - Final status `actioned` or `partially-applied`.
  - Make T024 pass.
- [X] T030 [P] [US2] Add contract tests in `tests/run.sh`:
  - `test_triage_md_prepare_mode_section`: it names `TRIAGE_PLAN`, `TRIAGE_ROOT`, `TRIAGE_STATE_FILE`, and the skipped steps 3c, 7b, 12c, 14.
  - `test_triage_md_mandatory_steps_have_prepare_exception`: the "MUST execute" notes on Steps 12c and 13 reference prepare mode.

**Checkpoint**: Quickstart Scenario 5 passes; US1 still passes.

---

## Phase 5: User Story 3 - Resume an Interrupted Bulk Run (P2)

**Goal**: `--resume [<run-id>]` keeps valid results, re-analyzes moved or missing PRs, and never repeats completed sub-actions.

**Independent Test**: Quickstart Scenario 3.

- [X] T031 [P] [US3] Write resume tests in `tests/run.sh`:
  - `test_bulk_state_resume_plan_keeps_unchanged`.
  - `test_bulk_state_resume_plan_reanalyzes_moved_head`.
  - `test_bulk_state_resume_plan_missing_worktree_reanalyzes`.
  - `test_bulk_state_resume_plan_analyzing_and_failed_to_pending`.
  - `test_bulk_state_resume_plan_keeps_actioned_and_lists_partial_for_apply`.
  - `test_bulk_state_resume_plan_applying_to_apply_list`.
  - `test_bulk_state_resume_plan_pending_push_counts_as_pushed`: remote head equals `pending_push`, so `expected_head` advances and the PR is not stale.
  - `test_bulk_state_find_unfinished_unknown_id_error`: the message lists the known ids.
- [X] T032 [US3] Implement `resume-plan <run> <current-heads-json>` in `review/core/scripts/bulk-state.sh`, applying the transition rules in `data-model.md`:
  - `analyzed` is kept only when the head is unchanged and the required worktree and prepared commit exist.
  - `analyzing` and `failed` go to `pending`.
  - `applying`, `partially-applied`, and decided-but-unapplied go to the apply list.
  - A remote head equal to `pending_push` counts as pushed.
  - Terminal states are kept. Make T031 pass.
- [X] T033 [US3] Fill the "Resume" section of `review/core/commands/bulk.md`:
  - Resolve the run id (given, or newest unfinished of `BULK_COMMAND`; unknown id gives the error from `contracts/cli-flags.md`). If no unfinished run exists: unattended starts a new run with the flags given (selector flags allowed); deferred prints "No unfinished <command> run to resume." and stops.
  - `validate`.
  - Reject extra flags per FR-029.
  - Fetch current heads (`pr-worktree.sh head` per non-terminal PR), then `resume-plan`.
  - Print the run id, then continue at analysis for `reanalyze`, the decision for undecided analyzed PRs, and apply for the `apply` list.
  - Before re-posting an unrecorded review, the posting step checks for this run's marker (posting worker instruction plus `bulk-apply.sh marker` already does this).
  - A paused run (rate limit) resumes the same way.
- [X] T034 [P] [US3] Add contract test `test_bulk_md_resume_section` in `tests/run.sh`: `bulk.md` references `resume-plan`, `validate`, and the FR-029 error text.

**Checkpoint**: Quickstart Scenario 3 passes.

---

## Phase 6: User Story 4 - Unattended Bulk Run (P2)

**Goal**: `--unattended` (or `interactive: false`) runs end to end without prompts using the documented policy.

**Independent Test**: Quickstart Scenario 4.

- [X] T035 [US4] Fill the "Unattended Policy" section of `review/core/commands/bulk.md`:
  - Review: findings → `post` with `REVIEW_EVENT_OVERRIDE=COMMENT`; zero findings → `marker`; never `fix`.
  - Triage: `apply` for bot actions; human comments are left untouched (decision `null`, so not posted) and listed in the summary as needing attention; no idea-inbox prompt.
  - An unfinished run present means an error (FR-031).
  - Decisions are recorded in state like deferred mode, and the run resumes unattended (FR-025).
  - State that no step of review.md or triage.md may prompt when `BULK_MODE=unattended`.
- [X] T036 [US4] Add rate-limit handling to `review/core/scripts/bulk-select.sh` and `bulk-apply.sh`, using the same detection as `pr-worktree.sh` (T006): check for `API rate limit exceeded` or `secondary rate limit` in `gh`/git stderr **before** any other error mapping, then exit with code 75 and print `Error: RATE_LIMITED`. In `review/core/commands/bulk.md`, map exit 75 and a worker's `STATUS failed reason=rate-limited` to run status `paused`, plus a summary line telling the user to run `--bulk --resume` (scheduled jobs: `--bulk --resume --unattended`). Add `test_bulk_apply_rate_limit_exit_75` and `test_bulk_select_rate_limit_exit_75` in `tests/run.sh` (fake gh returns the rate-limit text).
- [X] T037 [P] [US4] Add contract test `test_bulk_md_unattended_policy` in `tests/run.sh`: `bulk.md` names `REVIEW_EVENT_OVERRIDE=COMMENT`, `marker`, and that human comments are left untouched in unattended mode.

**Checkpoint**: Quickstart Scenario 4 passes.

---

## Phase 7: User Story 5 - Choose What "Un-reviewed" Means (P3)

**Goal**: `--all-open` and `--search` selectors with qualifier guards.

**Independent Test**: Quickstart Scenario 7 plus US5 acceptance scenarios with the fake gh.

- [X] T038 [P] [US5] Write tests in `tests/run.sh`:
  - `test_bulk_select_all_open`: drafts and at-head reviewed excluded.
  - `test_bulk_select_search_passes_query`.
  - `test_bulk_select_search_drafts_opt_in`: `draft:true` or `is:draft` keeps drafts.
  - `test_bulk_select_check_query_rejects_qualifiers`: `repo:`, `org:`, `user:`, `is:closed`, `is:merged`, `state:` each give exit 2 with the contract error text.
- [X] T039 [US5] Implement `--all-open`, `--search <q>` and `check-query` handling in `review/core/scripts/bulk-select.sh` (review and triage), with the draft opt-in and `baseRefName` in the requested fields. This is the only task that implements `check-query`. Make T038 pass.

**Checkpoint**: Quickstart Scenario 7 selector errors behave as specified.

---

## Phase 8: User Story 6 - Single-PR Review of a PR Not Checked Out (P3)

**Goal**: `/review --pr <n>` reviews the PR's own code when it is not the current branch.

**Independent Test**: Quickstart Scenario 6.

- [X] T040 [US6] In Step 1 of `review/core/commands/review.md`, when `PR_NUMBER` is set and not in bulk mode:
  - If `pr-worktree.sh is-pr-branch "$PR_NUMBER"` fails, create a worktree with `pr-worktree.sh add "$PR_NUMBER" <headRefOid> "$PROJECT_DIR/.cc-review/pr-worktrees/pr-$PR_NUMBER" <baseRefName>` (which replaces a leftover from a crashed run), set `BASE_REF`, set `REVIEW_ROOT` to it, set `ISOLATED_PR=true`, and ensure `.cc-review/pr-worktrees/.gitignore` with `*`.
  - In Step 5b with `ISOLATED_PR=true`: offer fix options only when the PR author equals `gh api user`, and after Step 6 commit and push via `pr-worktree.sh push` (STALE gives an error report, no post).
  - At command end (and every early stop that removes `REVIEW_RUN_DIR`), run `pr-worktree.sh remove`.
- [X] T041 [P] [US6] Add contract test `test_review_md_isolated_pr_checkout` in `tests/run.sh`: Step 1 references `is-pr-branch` and `pr-worktrees`, and cleanup references `pr-worktree.sh remove`.

**Checkpoint**: Quickstart Scenario 6 passes; single-PR on the current branch is unchanged.

---

## Phase 9: Polish & Cross-Cutting Concerns

- [X] T042 [P] Document bulk mode in `docs/standalone-guide.md`: a new "Bulk review and triage" section covering selectors, deferred vs unattended, the decision table, resume, the state directory, and scheduled-job usage with `--resume --unattended`.
- [X] T043 [P] Add bulk usage examples to `README.md` (commands section).
- [X] T044 [P] In `CLAUDE.md`, change the commands line of the project structure to `Command definitions (review.md, init.md, triage.md, bulk.md)`.
- [X] T045 Run `make test` and fix any failures; run `bash -n` on every new script; run `shellcheck` on the new scripts if it is available.
- [X] T046 Check `bulk.md` and the scripts against every row of `contracts/cli-flags.md`: each validation row has a matching check that emits the exact error text (enforced by `test_bulk_md_validation_errors` from T012). Fix any missing row.
- [X] T047 [P] Add a timing test `test_bulk_select_50_prs_under_10s` in `tests/run.sh` (fake gh serving `all-open-50.json`; assert `bulk-select.sh review --all-open` completes in under 10 s), and add quickstart scenarios to `specs/005-bulk-review-triage/quickstart.md`:
  - SC-004: in a run of 5 PRs, delete one PR's head branch before its turn, and expect that PR `failed` with the other 4 processed.
  - SC-005: run 10 PRs in one session, and expect the run to finish with `state.md` complete.
  - SC-007: an unattended triage run with a human comment, an injected failure, and a PR closed mid-run, with zero prompts.

---

## Dependencies & Execution Order

- **Setup (T001-T002)** → **Foundational (T003-T012)** → user stories.
- **US1 (T013-T022)** depends on Foundational. It is the MVP.
- **US2 (T023-T030)** depends on Foundational. It is independent of US1 except for shared files: `bulk.md` sections are distinct, but `bulk-select.sh` and `bulk-apply.sh` gain subcommands. Do US2 after US1 to avoid edit conflicts in these files.
- **US3 (T031-T034)** depends on US1 (and US2 for triage resume paths).
- **US4 (T035-T037)** depends on US1 and US2 (policy per command).
- **US5 (T038-T039)** depends on T015/T025 (`bulk-select.sh` exists).
- **US6 (T040-T041)** depends on T006 (`pr-worktree.sh`) and T016 (`REVIEW_ROOT`).
- **Polish** last.

### Within each phase

Tests marked [P] are written first and fail; then the implementation makes them pass. Edits to the same file (`review.md`, `bulk.md`, `bulk-select.sh`, `bulk-apply.sh`, `tests/run.sh`) are sequential.

### Parallel opportunities

- T002 alongside T001.
- T003, T004 and T007 alongside each other (different files). T011 alongside T008-T010.
- In US1, T013 and T014 (tests) in parallel. T015 (`bulk-select.sh`) in parallel with T016-T018 (`review.md`).
- In US2, T025 (`bulk-select.sh`) in parallel with T026 (`triage.md`).
- Docs T042-T044 in parallel.

Note: most tests live in the single file `tests/run.sh`. The [P] markers on test tasks mean they are logically independent; when executing, append them one task at a time to avoid edit conflicts.

## Implementation Strategy

1. **MVP**: Setup + Foundational + US1 → `/review --bulk` works in deferred mode for the default selector. Validate with Quickstart Scenarios 1 and 2.
2. Add US2 (bulk triage), then US3 (resume) and US4 (unattended), the core of what the user asked for.
3. Add US5 selectors and the US6 single-PR fix.
4. Polish and full `make test`.
