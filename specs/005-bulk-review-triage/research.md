# Research: Bulk Review and Bulk Triage

Line references: `R` = `review/core/commands/review.md`, `T` = `review/core/commands/triage.md` (state at branch point `782556a`).

## R-001: Bounding coordinator context (FR-010)

**Decision**: The coordinator runs each PR's review pipeline itself, one PR at a time, but in a **file-backed worker mode**: every subagent it dispatches (prompt reviewers, merge, meta-review critics, report writer, poster) reads its inputs from and writes its outputs to the PR's run directory `.cc-review/bulk/<run-id>/pr-<n>/`, and returns only a one-line status (counts, path). Command reviewers already write to files (R:392). Bulk triage runs one **triage worker subagent per PR** (triage dispatches no subagents of its own), which writes a prepared-action plan to the PR directory and returns a one-line status.

**Rationale**:
- Review dispatches reviewer subagents (R:281) and meta-review subagents (R:463). A "subagent per PR" would need nested subagents, which Claude Code does not support. File-backed dispatch keeps the existing dispatch shape.
- An inline single-PR run costs an estimated 20 to 40k coordinator tokens per PR (findings returned to context, 5a presentation, report text). In file-backed mode the coordinator sees about 10 short status lines per PR.
- It stays harness-agnostic: it only uses "dispatch a subagent" and file writes, the same primitives the plugin already relies on in all three harnesses.

**Alternatives considered**:
- *Headless child session per PR* (`claude -p`, `codex exec`, `opencode run`) running the single-PR command inside the worktree. It reuses the pipeline verbatim and solves the CWD problem, but it needs per-harness CLI detection, headless permission configuration, and background-process supervision longer than the shell timeout. It would also break the "shims add no logic" rule. Rejected for v1.
- *Inline, relying on harness auto-compaction*. Not every harness compacts, and compaction loses detail mid-run. Rejected.
- *Script-based dedup instead of a merge subagent*. Deterministic, but it would diverge from the single-PR LLM merge rules (R:418-425). Rejected; the merge subagent applies the same Step 4 text.

## R-002: Review root instead of CWD (FR-009, FR-035)

**Decision**: Introduce `REVIEW_ROOT` (absolute path of the tree under review). Default: `git rev-parse --show-toplevel` (today's behavior). In bulk mode and for single-PR `--pr` when the current branch is not the PR's head branch, `REVIEW_ROOT` is an isolated worktree. All file-reading steps use it: changed-file diff (`git -C "$REVIEW_ROOT"`), test detection, command reviewers (`cd "$REVIEW_ROOT"` in a subshell), and reviewer prompts (Review Target lists **absolute** paths under `REVIEW_ROOT`, because the harness Read tool resolves relative paths against the session directory, not a shell `cd`). Config, hints and project-layer reviewer discovery keep using the invoking repository (`PROJECT_DIR`), per FR-011.

**Rationale**: It is the smallest change that fixes the wrong-tree bug for both bulk and single-PR mode, and it keeps the user's checkout untouched.

## R-003: Isolated checkouts

**Decision**: `git fetch origin "pull/<n>/head"` then `git worktree add --detach <path> <sha>`. Path: `.cc-review/bulk/<run-id>/pr-<n>/wt` (bulk) or `.cc-review/pr-worktrees/pr-<n>` (single-PR, removed at the end of the run). Detached HEAD avoids the "branch already checked out" error when the user's own PR branch is the current branch (edge case from review-spec finding 7). `pull/<n>/head` works for fork PRs.

**Push**: `git -C <wt> push <head-remote-url> HEAD:refs/heads/<headRefName>` without force. A rejected non-fast-forward push means the remote moved → PR marked `stale`. A permission error marks it `cannot-push`. The head-repo URL is built from the PR's `headRepositoryOwner`/`headRepository`, using the same protocol as `origin`. The push itself is the atomic expected-head check for FR-030. Before posting, the coordinator additionally compares `headRefOid` with the expected head.

**Local branch check**: if `refs/heads/<headRefName>` exists locally and `git rev-list --count <prHead>..<local>` is greater than 0, the PR is marked `local-unpushed` and fix/push actions are not offered.

**Alternatives**: worktrees under `$TMPDIR` (lost on reboot, so resume could not keep prepared commits); a shallow clone per PR (slow, no shared objects).

## R-004: "Reviewed at head" detection (FR-004, FR-006, FR-030)

**Finding**: posted reviews never set `commit_id` (platform.sh `_github_post_review` sends `{body, event, comments}`, R:969-973), and `_github_fetch_reviews` does not fetch the commit. GitHub then records the head at submission time, which is close but racy.

**Decision**:
- Step 7.5k adds `commit_id: <reviewed head SHA>` to the payload, in single-PR and bulk mode alike. This is a harmless addition that makes the marker exact.
- Selection reads reviews through `gh pr list --json number,title,author,isDraft,headRefOid,headRefName,updatedAt,isCrossRepository,headRepository,headRepositoryOwner,reviews`. Each review carries `body`, `author.login`, `commit.oid`. A PR counts as reviewed at head when any review body contains `<!-- cc-review:run-id:` and `commit.oid == headRefOid`.
- Re-review set (FR-004): open PRs where `reviews[]` has a review by `GH_USER` with the marker and `commit.oid != headRefOid`. They come from a second query, `reviewed-by:@me`.
- The no-findings marker (FR-021a) reuses the same marker line, so detection is uniform.

## R-005: Selection queries

- Review default: union of `gh pr list --state open --search "review-requested:@me" ...` and `gh pr list --state open --search "reviewed-by:@me" ...` (the latter filtered to PRs with a cc-review review by the user at an older head). `review-requested:@me` includes team requests (clarification Q1).
- `--all-open`: `gh pr list --state open --limit 200 ...`.
- `--search '<q>'`: `gh pr list --state open --search "<q>" ...`. The script rejects `repo:`, `org:`, `user:`, `is:closed`, `is:merged`, `state:` qualifiers.
- Drafts are dropped unless the query contains `draft:true` or `is:draft`.
- Triage: one GraphQL search `repo:<o>/<r> is:pr is:open author:@me <q>` returning `reviewThreads(first:100){nodes{isResolved}}` to count unresolved threads.
- Sorting: `updatedAt` ascending. Cap at `--limit`.
- All `gh` calls live in `bulk-select.sh`, so tests can stub `gh` on `PATH` with fixture JSON.

## R-006: State format and atomicity

**Decision**: `.cc-review/bulk/<run-id>/state.json` is the source of truth. `state.md` is rendered from it by `bulk-state.sh render` after every mutation. Updates go through jq to a temp file, then `mv` (triage-state.sh pattern). Run id: `<YYYYMMDD-HHMMSS>-<review|triage>`, which sorts by time. `.cc-review/bulk/.gitignore` contains `*`, written by `bulk-state.sh init`. The unfinished-run check scans `*/state.json` for `.command == cmd and (.status | IN("finished","abandoned") | not)`.

**Sub-action idempotency (FR-028)**: each action records its identifier the moment it completes: `pushed_sha`, `review_id`, `replies[<comment_id>]`, `resolved[<thread_id>]`. Before re-posting a review on resume, `fetch_reviews` is checked for this run's marker `cc-review:run-id:<run-id>/pr-<n>`. For replies, triage-state already stores `ourReplyId` per comment.

## R-007: Triage prepare mode (FR-014, FR-014a)

**Decision**: the triage worker runs triage.md with `TRIAGE_MODE=prepare`, `TRIAGE_ROOT=<wt>`, and `TRIAGE_STATE_FILE=<invoking repo>/.cc-review/.triage-state.json` (the env override already exists, triage-state.sh:15). In prepare mode:
- Steps 3 to 6 run as usual. Edits use absolute paths under `TRIAGE_ROOT`.
- Step 3c (local CodeRabbit fallback) is skipped, because it posts to the PR.
- Step 7 commits in the worktree but **does not push**.
- Steps 7b, 7c, 8, 9, 9b, 10, 11b-2b/11b-5 (reply/resolve parts), 12 (presentation), 12b, 12c and 14 are replaced by **recording prepared actions** in `pr-<n>/triage-plan.json` (replies with bodies, threads to resolve, human comment items with drafted options).
- Step 13 writes `pr-<n>/triage-summary.md` instead of printing.

**Apply** runs as a script (`bulk-apply.sh triage`): push, re-fetch thread ids (7c logic, by path+line), post replies, resolve threads, recording each id. Human-comment decisions taken in the decision step are added to the plan before apply.

## R-008: Review posting in bulk

**Decision**: the posting step runs per PR in a **posting worker subagent** that executes R Step 7.5 with `INTERACTIVE=false` semantics (all findings accepted, so 7.5g is skipped). It reads findings from `pr-<n>/findings.json` (or `accepted.json` after a drill-down) and does the prose rewrite inline (no nested subagent). It sets `commit_id` and the review type: unattended mode is always `COMMENT` (clarification Q3); deferred mode uses the single-PR rule (R:906-908). The drill-down ("review findings") runs in the coordinator: it presents the PR's findings from file in the single-PR 7.5g format, writes `accepted.json`, then hands it to the posting worker.

**7.5f** (auto-resolve earlier cc-review threads without a matching finding) stays as it is, since it only touches cc-review's own threads.

## R-009: Interaction for the decision table

The harness choice widget allows few options per question. **Decision**: print the full table as text (PR, title, author, counts, report path, proposed action), then ask one question: `Apply proposed actions` / `Change actions per PR` / `Skip all` / `Stop (resume later)`. "Change actions" asks per PR in batches of up to 4 PRs per prompt, offering that PR's allowed actions (FR-019, FR-020). Human comments (triage) follow, one prompt per comment, as in T Step 12. This all counts as one decision step (SC-001).

## R-010: Flags and reserved names

New flags: `--bulk`, `--all-open`, `--search`, `--limit`, `--unattended`, `--resume`. `discover-reviewers.sh:46` reserves names so that `--no-<name>` cannot collide. Add `bulk all-open search limit unattended resume` to `CC_REVIEW_RESERVED_NAMES` and to `reviewer.schema.json` (kept in agreement by `test_schema_agrees_with_validator`). Shims (2 SKILL.md, 2 OpenCode command files) list the new flags and stay under 50 lines.

## R-011: Testing approach

Following `tests/run.sh` conventions (plain bash, `run_test`, explicit list in `main()`):
- Script tests for `bulk-state.sh` (init, ignore file, transitions, unfinished detection, abandon, render, corrupt-state refusal), `bulk-select.sh` (fake `gh` on `PATH` with fixtures: default/requested + re-review, at-head exclusion, drafts, qualifier rejection, limit and ordering, triage thread filter), `pr-worktree.sh` (real temp repos with a bare "origin": add detached, local-unpushed detection, push ff vs rejected → stale, remove), `bulk-apply.sh triage` (fake gh: records ids, skips recorded actions on rerun).
- Contract greps on R, T and `bulk.md` (bulk entry point, worker-mode sections, `commit_id`, prepare-mode exceptions).
- Shim flag pass-through and reserved names.
- End-to-end LLM behavior is validated manually through `quickstart.md`, as in earlier features.
