---
name: bulk
description: Bulk review and bulk triage orchestrator. Executed by review.md and triage.md when --bulk or --resume is given; not a user-facing command.
---

# Bulk Review and Triage

This file is executed by the "Bulk Mode" hand-off of `commands/review.md` (`BULK_COMMAND=review`) or `commands/triage.md` (`BULK_COMMAND=triage`), with the user's original arguments. It runs one command over several PRs:

1. select the PRs (`bulk-select.sh`) and record a resumable run under `.cc-review/bulk/<run-id>/` (`bulk-state.sh`)
2. analyze each PR in turn in its own detached worktree (`pr-worktree.sh`), with every subagent writing its result to the PR's directory and returning one status line
3. show one decision table (deferred mode) or apply the fixed policy (unattended mode)
4. apply the decided actions, checking the PR head before every push or post
5. print and write a summary

**Context discipline (FR-010).** The coordinator (you) keeps only a short per-PR summary: status, counts, report path. Findings, reviewer output and triage details stay in files under the PR's directory and are read with `jq` for counts only. The single exception is the interactive "review findings" drill-down in the decision step. Never read a findings file, report or plan into your own context otherwise.

**The user's checkout is never touched.** Every PR is analyzed in `<run dir>/pr-<n>/wt`, a detached worktree. Nothing in this command checks out, stashes, resets or commits in `PROJECT_DIR` itself, and nothing writes outside `.cc-review/bulk/` in it, apart from the shared triage state `.cc-review/.triage-state.json` that bulk triage updates exactly as single-PR triage does (FR-014a).

## Prerequisites

### Shell Blocks

All shell blocks work under bash and zsh. The harness may start a new shell for every block, so each block below begins with the same header line that sets the values you keep in your own context; replace the `{...}` placeholders with their current values (`{RUN_ID}` stays empty until the run exists):

```bash
export CC_REVIEW_CORE_DIR="{CORE_DIR}"; PROJECT_DIR="{PROJECT_DIR}"; RUN_ID="{RUN_ID}"
S="$CC_REVIEW_CORE_DIR/scripts"; RUN_DIR="$PROJECT_DIR/.cc-review/bulk/$RUN_ID"; cd "$PROJECT_DIR" || exit 1
```

Pass free text (titles, reasons) to `bulk-state.sh pr-set` through the environment and read it with `env.<NAME>`, never by pasting it into the jq expression: `REASON="$REASON" "$S/bulk-state.sh" pr-set "$RUN_ID" "$N" '.reason=env.REASON'`.

### Core Directory and Project

The command shim resolved the core directory (the directory that contains `commands/bulk.md`). Resolve `CORE_DIR` and the invoking repository once:

```bash
if [ -n "${CC_REVIEW_CORE_DIR:-}" ] && [ -f "$CC_REVIEW_CORE_DIR/commands/bulk.md" ]; then
  CORE_DIR="$CC_REVIEW_CORE_DIR"
else
  echo "Error: cc-review core directory unknown; set CC_REVIEW_CORE_DIR to the core path the shim resolved" >&2; exit 1
fi
export CC_REVIEW_CORE_DIR="$CORE_DIR"
PROJECT_DIR="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "Error: bulk mode must run inside a git repository" >&2; exit 1; }
echo "CORE_DIR=$CORE_DIR"
echo "PROJECT_DIR=$PROJECT_DIR"
```

Keep `CORE_DIR` and `PROJECT_DIR` for the header line. `PROJECT_DIR` is the one name for the invoking repository in all bulk sections: configuration, review hints, project reviewers, triage state and the run directory all come from it (FR-011, FR-014a).

### Config Resolution

Configuration is resolved from `PROJECT_DIR` with the same layers and flags as `review.md` and applies to every PR. `CONFIG_FLAG` and `PROFILE_FLAG` come from the arguments (empty when not given). A block that needs a config value re-runs the init, which is cheap and gives the same result:

```bash
export CC_REVIEW_CORE_DIR="{CORE_DIR}"; PROJECT_DIR="{PROJECT_DIR}"; RUN_ID=""
S="$CC_REVIEW_CORE_DIR/scripts"; cd "$PROJECT_DIR" || exit 1
source "$S/resolve-config.sh"
resolve_config_init --config "${CONFIG_FLAG:--}" --profile "${PROFILE_FLAG:--}" || exit 1
resolve_config_validate_types || exit 1
echo "INTERACTIVE=$(resolve_config "interactive" "true")"
echo "MAX_FIX_ROUNDS=$(resolve_config "max_fix_rounds" "3")"
echo "MIN_CONFIDENCE=$(resolve_config "severity.min_confidence" "70")"
```

Show deprecation warnings from `resolve_config_init` to the user once.

## Inputs

Parse the user's arguments. Every value flag consumes the next argument as its value, so a value is never read as a flag or a reviewer name (`--search 'no-foo'` does not disable a reviewer called `foo`):

| Argument | Variable | Notes |
|---|---|---|
| (set by the hand-off) | `BULK_COMMAND` | `review` or `triage` |
| `--bulk` | `BULK_FLAG=true` | |
| `--all-open` | `ALL_OPEN_FLAG=true` | |
| `--search <query>` | `SEARCH_GIVEN=true`, `SEARCH_QUERY=<query>` | |
| `--limit <n>` | `LIMIT_FLAG=<n>` | default 10 |
| `--unattended` | `UNATTENDED_FLAG=true` | |
| `--resume [<run-id>]` | `RESUME_FLAG=true`, `RESUME_ID` | the next argument is the run id only if it matches `^[0-9]{8}-[0-9]{6}-(review\|triage)(-[0-9]+)?$`; otherwise `RESUME_ID` stays empty and the argument is parsed normally |
| `--pr <n>` | `PR_FLAG=<n>` | always rejected |
| `--spec <path>`, `--output <path>` | `SPEC_FLAG`, `OUTPUT_FLAG` | rejected: `--spec` for bulk review and bulk triage (a spec belongs to one change), `--output` for bulk review |
| `--config <path>`, `--profile <name>` | `CONFIG_FLAG`, `PROFILE_FLAG` | apply to every PR |
| `--no-fix` | `NO_FIX=true` | review: "apply fixes" is not offered |
| `--idea-inbox <path>` | `IDEA_INBOX_FLAG` | triage: offered once after the decision step (deferred only) |
| `--no-coverage-fix` | | triage: accepted, no effect (coverage remediation never runs in bulk) |
| every other argument | `PER_PR_OPTIONS` | review: reviewer selection (`--only`, `--no-<name>`, `--external`, `--no-external`), `--no-meta-review`, `--max-rounds`, `--hints`, `--sequential`, `--parallel`; applied to every PR exactly as the single-PR command reads them |

`PER_PR_OPTIONS` holds only the "every other argument" row. The run's recorded `options` are `RECORDED_OPTIONS` (see Selection): `PER_PR_OPTIONS` plus `--no-fix`, `--config`, `--profile` and `--idea-inbox` with their values, so a resumed run uses the same options.

**Mode.** `BULK_MODE=unattended` when `--unattended` is given or the config value `interactive` is `false`; otherwise `BULK_MODE=deferred`.

## Flag Validation

All of these stop before any PR is touched. The last column names where each check runs; some run twice (in the hand-off and again below), which changes nothing:

| Condition | Error | Checked in |
|---|---|---|
| bulk flags (`--all-open`, `--search`, `--limit`, `--unattended`) without `--bulk`/`--resume` | `Error: --<flag> requires --bulk` | the Bulk Mode hand-off of `review.md` and `triage.md` (this file only runs with `--bulk` or `--resume`) |
| `--bulk` with `--pr` | `Error: --bulk and --pr cannot be combined; --pr names a single PR` | the hand-off, and the block below |
| `--all-open` with `--search` | `Error: --all-open and --search are mutually exclusive` | below |
| `--all-open` on triage | `Error: --all-open is not supported by triage; bulk triage always selects your own PRs` | below |
| `--limit` not a positive integer | `Error: --limit must be a positive integer, got '<v>'` | below |
| `--search` with `repo:`, `org:`, `user:`, `is:closed`, `is:merged`, `state:` | `Error: --search may not contain '<qualifier>'; bulk mode always uses open PRs of the current repository` | `bulk-select.sh check-query`, called below |
| `--spec` (bulk review and bulk triage) or `--output` (bulk review) | `Error: --<flag> is not supported with --bulk` | the hand-off, and the block below |
| `--resume` with selector or per-PR flags while an unfinished run exists | `Error: --resume continues run <id> with its recorded options; remove <flags>` | Resume |
| `--resume --unattended` on a deferred run, or `--resume` without `--unattended` on an unattended run in a non-interactive context | `Error: run <id> was started in <mode> mode` | Resume |
| `--resume <id>` unknown | `Error: no unfinished <command> run '<id>'; unfinished runs: <ids or "none">` | `bulk-state.sh find-unfinished` |

For a new run (no `--resume`, or `--resume --unattended` with no unfinished run), validate the flags:

```bash
export CC_REVIEW_CORE_DIR="{CORE_DIR}"; PROJECT_DIR="{PROJECT_DIR}"; RUN_ID=""
S="$CC_REVIEW_CORE_DIR/scripts"; cd "$PROJECT_DIR" || exit 1
bulk_fail() { echo "Error: $1" >&2; exit 1; }
if [ -n "${PR_FLAG:-}" ]; then
  bulk_fail "--bulk and --pr cannot be combined; --pr names a single PR"
fi
if [ "${ALL_OPEN_FLAG:-}" = true ] && [ "$BULK_COMMAND" = triage ]; then
  bulk_fail "--all-open is not supported by triage; bulk triage always selects your own PRs"
fi
if [ "${ALL_OPEN_FLAG:-}" = true ] && [ "${SEARCH_GIVEN:-}" = true ]; then
  bulk_fail "--all-open and --search are mutually exclusive"
fi
if [ -n "${LIMIT_FLAG:-}" ]; then
  case "$LIMIT_FLAG" in
    *[!0-9]*) bulk_fail "--limit must be a positive integer, got '$LIMIT_FLAG'" ;;
  esac
  [ "$LIMIT_FLAG" -gt 0 ] 2>/dev/null || bulk_fail "--limit must be a positive integer, got '$LIMIT_FLAG'"
fi
if [ -n "${SPEC_FLAG:-}" ]; then bulk_fail "--spec is not supported with --bulk"; fi
if [ "$BULK_COMMAND" = review ] && [ -n "${OUTPUT_FLAG:-}" ]; then
  bulk_fail "--output is not supported with --bulk"
fi
if [ "${SEARCH_GIVEN:-}" = true ]; then
  "$S/bulk-select.sh" check-query "$SEARCH_QUERY" || exit 1
fi
echo "FLAGS OK"
```

## Platform and Authentication

Bulk mode needs a GitHub repository and an authenticated `gh`, like the single-PR commands. Stop with their errors before anything is selected:

```bash
export CC_REVIEW_CORE_DIR="{CORE_DIR}"; PROJECT_DIR="{PROJECT_DIR}"; RUN_ID=""
S="$CC_REVIEW_CORE_DIR/scripts"; cd "$PROJECT_DIR" || exit 1
source "$S/platform.sh"
if [ "$(detect_platform 2>/dev/null)" != github ]; then
  echo "Error: Could not extract owner/repo from origin URL. Ensure the remote points to a GitHub repository." >&2; exit 1
fi
GH_USER=$(gh api user -q .login 2>/dev/null) || GH_USER=""
[ -n "$GH_USER" ] || { echo "Error: gh CLI not authenticated, run \`gh auth login\`" >&2; exit 1; }
OWNER=$(gh repo view --json owner -q .owner.login 2>/dev/null) || OWNER=""
REPO=$(gh repo view --json name -q .name 2>/dev/null) || REPO=""
[ -n "$OWNER" ] && [ -n "$REPO" ] || { echo "Error: Could not extract owner/repo from origin URL. Ensure the remote points to a GitHub repository." >&2; exit 1; }
echo "GH_USER=$GH_USER OWNER=$OWNER REPO=$REPO"
```

Keep `GH_USER`, `OWNER` and `REPO`.

## Unfinished-Run Check

At most one unfinished run per command and repository exists at a time (FR-031). Look it up:

```bash
export CC_REVIEW_CORE_DIR="{CORE_DIR}"; PROJECT_DIR="{PROJECT_DIR}"; RUN_ID=""
S="$CC_REVIEW_CORE_DIR/scripts"; cd "$PROJECT_DIR" || exit 1
"$S/bulk-state.sh" find-unfinished "$BULK_COMMAND" "${RESUME_ID:-}"
```

The output lists unfinished run ids, newest (most recently updated) first. With a `RESUME_ID`, it prints that id, or fails with `Error: no unfinished <command> run '<id>'; unfinished runs: ...`; show that error and stop.

**With `--resume`:**
- An unfinished run exists (the given id, or the newest one): print `Resuming run <id>.` and continue at [Resume](#resume).
- None exists and `BULK_MODE=unattended`: start a new run with the flags given (validate them as a new run above, selector flags allowed), so a scheduled `--bulk --resume --unattended` job always makes progress.
- None exists and `BULK_MODE=deferred`: print `No unfinished <command> run to resume.` and stop.

**Without `--resume`:**
- None exists: continue at Selection.
- One exists and `BULK_MODE=unattended`: stop with an error that fits the run's recorded mode (`jq -r .mode` on its `state.json`): for an unattended run `Error: unfinished bulk <command> run <id> exists; continue it with --bulk --resume --unattended`; for a deferred run `Error: unfinished deferred bulk <command> run <id> exists; resume it interactively with --bulk --resume, or abandon it` (a deferred run cannot be resumed unattended).
- One exists and `BULK_MODE=deferred`: ask the user, in plain words, naming the run id, its age and how many PRs it has left:
  - **Resume it**: continue at [Resume](#resume) with that id. The run keeps its recorded options; say so when the user passed other flags.
  - **Abandon it and start a new run**: `"$S/bulk-state.sh" abandon <id>` marks it abandoned (its state stays on disk), removes the worktrees it kept and lists them under "Removed worktrees" in its `summary.md`; tell the user how many were removed (`OK removed=<n>`), then continue at Selection.
  - **Cancel**: stop without changes.

## Selection

```bash
export CC_REVIEW_CORE_DIR="{CORE_DIR}"; PROJECT_DIR="{PROJECT_DIR}"; RUN_ID=""
S="$CC_REVIEW_CORE_DIR/scripts"; cd "$PROJECT_DIR" || exit 1
SELECT_ARGS=(--user "$GH_USER" --limit "${LIMIT_FLAG:-10}")
if [ "${ALL_OPEN_FLAG:-}" = true ]; then SELECT_ARGS+=(--all-open); fi
if [ "${SEARCH_GIVEN:-}" = true ]; then SELECT_ARGS+=(--search "$SEARCH_QUERY"); fi
# The selection is kept inside the ignored state root until the run exists (FR-033)
mkdir -p "$PROJECT_DIR/.cc-review/bulk"
[ -f "$PROJECT_DIR/.cc-review/bulk/.gitignore" ] || printf '*\n' > "$PROJECT_DIR/.cc-review/bulk/.gitignore"
SELECTION_FILE="$PROJECT_DIR/.cc-review/bulk/.selection-$BULK_COMMAND.json"
"$S/bulk-select.sh" "$BULK_COMMAND" "${SELECT_ARGS[@]}" > "$SELECTION_FILE"; RC=$?
if [ "$RC" -ne 0 ]; then
  rm -f "$SELECTION_FILE"
  [ "$RC" -eq 75 ] && echo "Error: GitHub rate limit reached before any PR was selected; try again later." >&2
  exit 1
fi
jq -r '"SELECTED=\(.selected | length)", "EXCLUDED=\(.excluded | length)",
  (.excluded | group_by(.reason) | map("  \(.[0].reason): \(length)") | .[])' "$SELECTION_FILE"
```

The selectors (FR-004 to FR-007): bulk review by default takes the PRs that request the user's review plus re-reviews of PRs with new commits since the user's last cc-review review; `--all-open` takes every open PR; `--search` takes the open PRs of the current repository that match the query. Bulk triage takes the user's own open PRs with unresolved threads, narrowed by `--search`. Drafts are dropped unless the query contains `draft:true` or `is:draft`, and bulk review never selects a PR that already has a cc-review review at its current head by someone other than the PR's author (a marker review by the author counts only when the author is the user; bulk triage goes by unresolved threads instead).

If `SELECTED` is 0, print `No PRs matched` with the selector used (`default`, `all-open`, or the search query) and the exclusion counts by reason (for example "3 already reviewed at their current head", "2 without open threads", "1 draft"), remove `$SELECTION_FILE`, and stop. No state directory is created.

Otherwise create the run:

```bash
export CC_REVIEW_CORE_DIR="{CORE_DIR}"; PROJECT_DIR="{PROJECT_DIR}"; RUN_ID=""
S="$CC_REVIEW_CORE_DIR/scripts"; cd "$PROJECT_DIR" || exit 1
SELECTION_FILE="$PROJECT_DIR/.cc-review/bulk/.selection-$BULK_COMMAND.json"
KIND=default
if [ "${ALL_OPEN_FLAG:-}" = true ]; then KIND=all-open; fi
if [ "${SEARCH_GIVEN:-}" = true ]; then KIND=search; fi
SELECTOR=$(jq -nc --arg k "$KIND" --arg q "${SEARCH_QUERY:-}" --argjson l "${LIMIT_FLAG:-10}" \
  '{kind: $k, query: (if $q == "" then null else $q end), limit: $l}')
OPTIONS=$(printf '%s\n' ${RECORDED_OPTIONS[@]+"${RECORDED_OPTIONS[@]}"} | jq -Rnc '[inputs | select(length > 0)]')
RUN_ID=$("$S/bulk-state.sh" init "$BULK_COMMAND" "$BULK_MODE" "$SELECTOR" "$OPTIONS" "$OWNER" "$REPO" "$GH_USER") || exit 1
"$S/bulk-state.sh" set-prs "$RUN_ID" "$(jq -c .selected "$SELECTION_FILE")" "$(jq -c .excluded "$SELECTION_FILE")" >/dev/null || exit 1
rm -f "$SELECTION_FILE"
echo "RUN_ID=$RUN_ID"
echo "STATE=$PROJECT_DIR/.cc-review/bulk/$RUN_ID/state.md"
```

Before the block, set `RECORDED_OPTIONS` as a shell array (empty when there is nothing to record): every element of `PER_PR_OPTIONS`, then `--no-fix` when `NO_FIX=true`, `--config <value>`, `--profile <value>` and `--idea-inbox <value>` when given, each value as its own element (for example `RECORDED_OPTIONS=(--only security --no-fix --config ./ci.yml)`). Every later step reads these four flags from the recorded `options` (the "apply fixes" keep rule, the fix-round config, Resume), so leaving one out changes the run. Keep `RUN_ID`. Tell the user in one line how many PRs were selected and excluded, the run id, and that `state.md` shows progress at any time.

## Analysis Loop

Process the PRs whose status is `pending`, one at a time, in state order (FR-016). In deferred mode nothing in this loop asks the user anything (FR-017); in unattended mode nothing does either. List them with:

```bash
export CC_REVIEW_CORE_DIR="{CORE_DIR}"; PROJECT_DIR="{PROJECT_DIR}"; RUN_ID="{RUN_ID}"
S="$CC_REVIEW_CORE_DIR/scripts"; RUN_DIR="$PROJECT_DIR/.cc-review/bulk/$RUN_ID"; cd "$PROJECT_DIR" || exit 1
"$S/bulk-state.sh" set-status "$RUN_ID" analyzing >/dev/null
jq -r '.prs[] | select(.status == "pending") | "\(.number)\t\(.title)"' "$RUN_DIR/state.json"
```

For each PR `N`, print one progress line (`PR 2/5 #123 <title>: analyzing...`), then:

**1. Check out.** Read the current head, create the worktree, and flag local commits that are not on the remote (the user's local branch of the PR is ahead of it):

```bash
export CC_REVIEW_CORE_DIR="{CORE_DIR}"; PROJECT_DIR="{PROJECT_DIR}"; RUN_ID="{RUN_ID}"
S="$CC_REVIEW_CORE_DIR/scripts"; RUN_DIR="$PROJECT_DIR/.cc-review/bulk/$RUN_ID"; cd "$PROJECT_DIR" || exit 1
N="{N}"
PR_DIR="$RUN_DIR/pr-$N"
mkdir -p "$PR_DIR"
# A new analysis starts from an empty PR directory: files of an earlier analysis
# (curated accepted.json, meta verdicts, findings, plans) belong to another head.
# The worktree is replaced by pr-worktree.sh add below.
find "$PR_DIR" -mindepth 1 -maxdepth 1 ! -name wt -exec rm -rf {} +
"$S/bulk-state.sh" pr-set "$RUN_ID" "$N" '.status="analyzing"' '.reason=null' >/dev/null
HEAD_SHA=$("$S/pr-worktree.sh" head "$N" 2>"$PR_DIR/checkout.err"); RC=$?
if [ "$RC" -eq 0 ]; then
  BASE=$("$S/bulk-state.sh" pr-get "$RUN_ID" "$N" .base_ref)
  WT=$("$S/pr-worktree.sh" add "$N" "$HEAD_SHA" "$PR_DIR/wt" "$BASE" 2>"$PR_DIR/checkout.err"); RC=$?
fi
case "$RC" in
  0)
    HEAD_SHA="$HEAD_SHA" WT="$WT" "$S/bulk-state.sh" pr-set "$RUN_ID" "$N" \
      '.analyzed_head=env.HEAD_SHA' '.expected_head=env.HEAD_SHA' '.worktree=env.WT' >/dev/null
    HEAD_REF=$("$S/bulk-state.sh" pr-get "$RUN_ID" "$N" .head_ref)
    # For a fork PR, only a local branch tracking the fork is the PR's branch
    HEAD_URL=$("$S/bulk-state.sh" pr-get "$RUN_ID" "$N" 'if .is_cross_repo then (.head_repo_url // "-") else "" end')
    if [ -n "$HEAD_URL" ]; then
      AHEAD=$("$S/pr-worktree.sh" local-ahead "$HEAD_REF" "$HEAD_SHA" "$HEAD_URL" 2>/dev/null || echo 0)
    else
      AHEAD=$("$S/pr-worktree.sh" local-ahead "$HEAD_REF" "$HEAD_SHA" 2>/dev/null || echo 0)
    fi
    if [ "${AHEAD:-0}" -gt 0 ]; then
      "$S/bulk-state.sh" pr-set "$RUN_ID" "$N" '.flags=((.flags + ["local-unpushed"]) | unique)' >/dev/null
    fi
    echo "CHECKOUT ok wt=$WT head=$HEAD_SHA base=origin/$BASE" ;;
  75)
    echo "CHECKOUT rate-limited" ;;
  *)
    REASON="checkout failed: $(tail -n 1 "$PR_DIR/checkout.err")" \
      "$S/bulk-state.sh" pr-set "$RUN_ID" "$N" '.status="failed"' '.reason=env.REASON' >/dev/null
    echo "CHECKOUT failed" ;;
esac
```

- `CHECKOUT failed`: the PR is `failed` with the reason (branch deleted, fork not reachable, ...); go to the next PR (FR-015).
- `CHECKOUT rate-limited`: see Rate Limits below.
- `CHECKOUT ok`: continue with the analysis.

**2. Analyze.** Run the command's analysis worker: [Review Analysis](#review-analysis) for `review`, [Triage Analysis](#triage-analysis) for `triage`. It sets the PR to `analyzed` (with counts, report path and proposed action) or `failed` (with a reason).

**Any early stop inside the per-PR pipeline marks only that PR as failed.** Every place where the single-PR command would stop (`exit 1`, "stop", "report and stop"), a worker that fails or returns no parseable `STATUS` line, a missing output file: set the PR to `failed` with the reason and continue with the next PR. Never end the bulk run because one PR failed. A failed PR keeps its worktree for inspection (FR-012).

**3. Worktree.** The record block of the command's analysis section applies its keep rule and removes the worktree when the PR does not need it until the decision (FR-012); nothing else is done here.

**4. Progress.** Print one line with the outcome (`PR 2/5 #123: 0 critical, 2 important, 4 minor, 1 notable` or `PR 2/5 #123: failed (<reason>)`). `state.md` is re-rendered by every state change.

### Rate Limits

A script exit code 75 (`Error: RATE_LIMITED`) or a worker's `STATUS failed reason=rate-limited` means the hosting service is rate limiting every remaining PR, so failing them one by one would be wrong. Pause the run, stop the loop, and go to Summary. What happens to the current PR depends on the phase.

**During analysis** (checkout or an analysis worker): the analysis is incomplete, so put the PR back to `pending` and remove its worktree; a resume analyzes it again:

```bash
export CC_REVIEW_CORE_DIR="{CORE_DIR}"; PROJECT_DIR="{PROJECT_DIR}"; RUN_ID="{RUN_ID}"
S="$CC_REVIEW_CORE_DIR/scripts"; RUN_DIR="$PROJECT_DIR/.cc-review/bulk/$RUN_ID"; cd "$PROJECT_DIR" || exit 1
N="{N}"
"$S/pr-worktree.sh" remove "$RUN_DIR/pr-$N/wt"
"$S/bulk-state.sh" pr-set "$RUN_ID" "$N" '.status="pending"' '.worktree=null' >/dev/null
"$S/bulk-state.sh" set-status "$RUN_ID" paused >/dev/null
```

**During apply** (head check, push, post, marker, triage apply, or the pre-decision refresh): only pause the run. The PR keeps its status (`analyzed`, `applying` or `partially-applied`), its decision, its recorded actions and its worktree, so a resume applies what is left:

```bash
export CC_REVIEW_CORE_DIR="{CORE_DIR}"; PROJECT_DIR="{PROJECT_DIR}"; RUN_ID="{RUN_ID}"
S="$CC_REVIEW_CORE_DIR/scripts"; cd "$PROJECT_DIR" || exit 1
"$S/bulk-state.sh" set-status "$RUN_ID" paused >/dev/null
```

The summary then tells the user: "GitHub rate limit reached; the run is paused. Continue later with `--bulk --resume` (scheduled jobs: `--bulk --resume --unattended`)." A rate limit by an external reviewer tool (a command reviewer over its usage limit) is not this case: it fails only that reviewer, as in single-PR review.

### Review Analysis

For a PR with `CHECKOUT ok`, run `commands/review.md` in worker mode: read its section "Worker Mode (bulk)" once per run and follow it for every PR.

**1. Worker inputs.** Set them for this PR (keep them in your context; every block re-sets them):

| Variable | Value |
|---|---|
| `WORKER_MODE` | `true` |
| `REVIEW_ROOT` | the worktree path from `CHECKOUT ok` |
| `PR_NUMBER` | `N` |
| `PR_DIR` | `$RUN_DIR/pr-$N` |
| `EXPECTED_HEAD` | the analyzed head from `CHECKOUT ok` |
| `BASE_REF` | `origin/<base_ref>` from `CHECKOUT ok` |
| `RUN_MARKER` | `$RUN_ID/pr-$N` |
| `MIN_CONFIDENCE` | from Config Resolution |
| `UNTRUSTED_CHECKOUT` | `true` when the PR comes from a fork (`"$S/bulk-state.sh" pr-get "$RUN_ID" "$N" '.is_cross_repo // false'`), otherwise `false`: command reviewers then run only with `allow_untrusted_checkout.<name>: true` (`review.md` Step 2, Untrusted Checkout) |
| per-PR options | the run's recorded `options` (`jq -r '.options[]' "$RUN_DIR/state.json"`), parsed exactly as `review.md` parses its arguments |

**2. Pipeline.** In this order, as `review.md` "Worker Mode (bulk)" describes:
1. (a) Steps 1 to 3 in your shell: changed files from the worktree, discovery, enablement, selection and detection, then `$PR_DIR/reviewers.json` is written **before any worker runs**; command reviewers run inside the worktree with their output kept in `$PR_DIR/commands/`
2. (b) the prompt reviewer workers, each writing `$PR_DIR/findings/<name>.json` and returning `STATUS ok findings=<n>`
3. (c) the merge worker (`$PR_DIR/merged.json`)
4. (d) the Skeptic and Calibrator workers, when the Step 4b gate passes on the merged count
5. (e) the report worker (`$PR_DIR/findings.json`, `$PR_DIR/review-findings.md`)

Failure handling (`review.md` Worker Mode):
- A reviewer worker without a parseable `STATUS` line, or whose findings file is missing or not a JSON array, is marked `failed` in `reviewers.json`; the PR continues with the other reviewers.
- An early stop in Steps 1 to 3, or a merge or report worker that fails, returns no `STATUS` line or leaves its output file missing, fails the PR: set `failed` with a reason naming the step (`REASON="merge worker failed: <detail>"`), keep the worktree, and go to the next PR.
- `STATUS failed reason=rate-limited` from any worker: see Rate Limits.

**3. Record the result.** Counts come from `findings.json` with `jq`; do not read the findings themselves. The proposed action follows FR-021: findings, so `post`; no findings, so `marker`:

```bash
export CC_REVIEW_CORE_DIR="{CORE_DIR}"; PROJECT_DIR="{PROJECT_DIR}"; RUN_ID="{RUN_ID}"
S="$CC_REVIEW_CORE_DIR/scripts"; RUN_DIR="$PROJECT_DIR/.cc-review/bulk/$RUN_ID"; cd "$PROJECT_DIR" || exit 1
N="{N}"
PR_DIR="$RUN_DIR/pr-$N"
if ! jq -e 'type == "array"' "$PR_DIR/findings.json" >/dev/null 2>&1 || [ ! -s "$PR_DIR/review-findings.md" ]; then
  REASON="report worker failed: findings.json or review-findings.md missing" \
    "$S/bulk-state.sh" pr-set "$RUN_ID" "$N" '.status="failed"' '.reason=env.REASON' >/dev/null
  echo "ANALYSIS failed"; exit 0
fi
COUNTS=$(jq -c '{critical: map(select(.severity == "Critical")) | length,
  important: map(select(.severity == "Important")) | length,
  minor: map(select(.severity == "Minor")) | length,
  notable: map(select(.severity == "Notable")) | length}' "$PR_DIR/findings.json")
PROPOSED=marker
[ "$(jq 'length' "$PR_DIR/findings.json")" -gt 0 ] && PROPOSED=post
# Fixable findings: a concrete suggested fix, or a gate finding (Critical,
# Important), as single-PR review offers "Apply the important fixes" for those
FIXABLE=$(jq '[.[] | select((((.fix // "") | test("\\S")) or .severity == "Critical" or .severity == "Important")
  and .resolution != "fixed")] | length' "$PR_DIR/findings.json")
COUNTS="$COUNTS" PROPOSED="$PROPOSED" FIXABLE="$FIXABLE" "$S/bulk-state.sh" pr-set "$RUN_ID" "$N" \
  '.status="analyzed"' '.counts=(env.COUNTS | fromjson)' '.fixable=(env.FIXABLE | tonumber)' \
  '.report="pr-\(.number)/review-findings.md"' '.proposed=env.PROPOSED' >/dev/null
# The worktree stays only when "apply fixes" can be offered for this PR (FR-012, FR-019)
KEEP=$(jq -r --argjson n "$N" '. as $run | .prs[] | select(.number == $n)
  | .authored_by_user and ((.flags | index("local-unpushed")) | not)
    and (($run.options | index("--no-fix")) | not) and ((.fixable // 0) > 0)' "$RUN_DIR/state.json")
if [ "$KEEP" != true ]; then
  "$S/pr-worktree.sh" remove "$PR_DIR/wt" && "$S/bulk-state.sh" pr-set "$RUN_ID" "$N" '.worktree=null' >/dev/null
fi
echo "ANALYSIS ok counts=$COUNTS fixable=$FIXABLE proposed=$PROPOSED keep_worktree=$KEEP"
```

`fixable` counts the findings that have a concrete suggested fix (a non-empty `fix`) or are Critical or Important (prompt reviewers report no `fix` text, so gate findings count on their own, as for the single-PR "Apply the important fixes"); "apply fixes" is offered only when it is above 0. `authored_by_user` comes from selection (the PR author equals the authenticated user). `local-unpushed` was flagged at checkout: the user's local branch of this PR has commits that are not on the remote, so only posting is offered for it (fixes pushed from the worktree would bypass those commits).

### Triage Analysis

For a PR with `CHECKOUT ok`, dispatch **one triage worker** subagent (triage dispatches no subagents of its own, so this is the only level). Give it the absolute path of `commands/triage.md` and these inputs, and tell it to execute that file in its "Prepare Mode (`TRIAGE_MODE=prepare`)" section:

| Input | Value |
|---|---|
| `TRIAGE_MODE` | `prepare` |
| `--pr` | `N` |
| `TRIAGE_ROOT` | the worktree path from `CHECKOUT ok` |
| `TRIAGE_PLAN` | `$PR_DIR/triage-plan.json` |
| `TRIAGE_STATE_FILE` | `$PROJECT_DIR/.cc-review/.triage-state.json` (the invoking repository's triage state, FR-014a) |
| `PROJECT_DIR`, `CORE_DIR` | as in your header line |
| `--config`, `--profile` | from the run's recorded options, when present |

The prompt ends with the return contract: "Your final reply is exactly one line: `STATUS ok valid=<n> rejected=<n> deferred=<n> human=<n> commit=<sha or none>`, `STATUS failed reason=rate-limited`, or `STATUS failed reason=<short reason>`. Do not push, post, resolve or ask anything."

Map the reply:
- `STATUS failed reason=rate-limited`: see Rate Limits.
- `STATUS ok ...`: record the result with the block below (it checks the plan file itself).
- anything else (another failure, no parseable `STATUS` line): set the PR `failed` with `REASON="triage worker failed: <reason>"`, keep the worktree, and go to the next PR.

Counts come from the plan with `jq`, never by reading it. The proposed action follows FR-021: anything prepared (a commit, replies, resolutions, human comments to answer) gives `apply`; an empty plan gives `skip`:

```bash
export CC_REVIEW_CORE_DIR="{CORE_DIR}"; PROJECT_DIR="{PROJECT_DIR}"; RUN_ID="{RUN_ID}"
S="$CC_REVIEW_CORE_DIR/scripts"; RUN_DIR="$PROJECT_DIR/.cc-review/bulk/$RUN_ID"; cd "$PROJECT_DIR" || exit 1
N="{N}"
PR_DIR="$RUN_DIR/pr-$N"
PLAN="$PR_DIR/triage-plan.json"
if ! jq -e 'type == "object" and (.replies | type) == "array" and (.human | type) == "array"' "$PLAN" >/dev/null 2>&1; then
  REASON="triage worker failed: triage-plan.json missing or invalid" \
    "$S/bulk-state.sh" pr-set "$RUN_ID" "$N" '.status="failed"' '.reason=env.REASON' >/dev/null
  echo "ANALYSIS failed"; exit 0
fi
COUNTS=$(jq -c '{bot_valid: ([.replies[] | select(.action == "accepted")] | length),
  bot_rejected: ([.replies[] | select(.action == "rejected")] | length),
  deferred: ([.replies[] | select(.action == "deferred")] | length),
  human: (.human | length)}' "$PLAN")
PROPOSED=$(jq -r 'if .prepared_commit != null or (.replies | length) > 0 or ((.cc_review_threads // []) | length) > 0
  or ((.stale_resolutions // []) | length) > 0 or (.human | length) > 0 then "apply" else "skip" end' "$PLAN")
PREPARED=$(jq -r '.prepared_commit // ""' "$PLAN")
# The summary is recorded only when the worker wrote it, so the resume check
# for an intact analysis means something
REPORT=""
if [ -s "$PR_DIR/triage-summary.md" ]; then REPORT="pr-$N/triage-summary.md"; fi
COUNTS="$COUNTS" PROPOSED="$PROPOSED" REPORT="$REPORT" "$S/bulk-state.sh" pr-set "$RUN_ID" "$N" \
  '.status="analyzed"' '.counts=(env.COUNTS | fromjson)' '.report=(if env.REPORT == "" then null else env.REPORT end)' '.proposed=env.PROPOSED' >/dev/null
# The worktree holds the prepared commit until the PR is decided and pushed (FR-012)
if [ -z "$PREPARED" ]; then
  "$S/pr-worktree.sh" remove "$PR_DIR/wt" && "$S/bulk-state.sh" pr-set "$RUN_ID" "$N" '.worktree=null' >/dev/null
fi
echo "ANALYSIS ok counts=$COUNTS proposed=$PROPOSED commit=${PREPARED:-none}"
```

Worktree keep rule: the worktree stays while the PR has a `prepared_commit` and is undecided or `partially-applied`; it is removed after analysis when nothing was committed, and after apply once the PR is `actioned`, `skipped`, `stale` or `cannot-push`.

Two flags limit what apply can do; both are shown in the decision table:
- `local-unpushed` (set at checkout through `pr-worktree.sh local-ahead`): the user's local branch of this PR has commits that are not on the remote. Apply then posts only the replies that do not depend on the prepared fixes (rejections, deferrals, human replies, cc-review thread replies); the prepared commit is not pushed and acceptance replies are skipped.
- `cross-repo`: the PR comes from a fork. The push may be refused; `bulk-apply.sh triage` then answers `DENIED`, keeps the fixes unpushed, posts only the replies that do not depend on them (as for `local-unpushed`), and the PR becomes `cannot-push`.

## Pre-Decision Refresh

Before the decision table, re-read every PR that is still `analyzed` or `failed` with the head check of `bulk-apply.sh head` (the same check as before every push and post, see [Apply](#apply)): a PR closed or merged in the meantime becomes `closed` (no action is offered). An analyzed PR whose head moved no longer matches its analysis (FR-030): `bulk-state.sh reanalyze` puts it back to `pending` for one more analysis in this run (`REANALYZE`), or, when it was already analyzed again once (its `reanalyses` count in the state), marks it `stale` (`STALE`):

```bash
export CC_REVIEW_CORE_DIR="{CORE_DIR}"; PROJECT_DIR="{PROJECT_DIR}"; RUN_ID="{RUN_ID}"
S="$CC_REVIEW_CORE_DIR/scripts"; RUN_DIR="$PROJECT_DIR/.cc-review/bulk/$RUN_ID"; cd "$PROJECT_DIR" || exit 1
for N in $(jq -r '.prs[] | select(.status == "analyzed" or .status == "failed") | .number' "$RUN_DIR/state.json"); do
  OUT=$("$S/bulk-apply.sh" head "$RUN_ID" "$N" 2>"$RUN_DIR/refresh.err"); RC=$?
  if [ "$RC" -eq 75 ]; then echo "RATE_LIMITED"; break; fi
  if [ "$RC" -ne 0 ]; then echo "#$N: could not refresh ($(tail -n 1 "$RUN_DIR/refresh.err"))"; continue; fi
  STATUS=$("$S/bulk-state.sh" pr-get "$RUN_ID" "$N" .status)
  case "$OUT" in
    "CLOSED "*)
      REASON="PR is ${OUT#CLOSED }" "$S/bulk-state.sh" pr-set "$RUN_ID" "$N" '.status="closed"' '.reason=env.REASON' '.proposed=null' >/dev/null
      "$S/pr-worktree.sh" remove "$RUN_DIR/pr-$N/wt" && "$S/bulk-state.sh" pr-set "$RUN_ID" "$N" '.worktree=null' >/dev/null
      echo "#$N: closed" ;;
    "MOVED "*)
      if [ "$STATUS" = analyzed ]; then
        "$S/pr-worktree.sh" remove "$RUN_DIR/pr-$N/wt"
        echo "#$N: $("$S/bulk-state.sh" reanalyze "$RUN_ID" "$N")"
      fi ;;
  esac
done
```

- `RATE_LIMITED` pauses the run as in Rate Limits (no PR is put back; analyzed PRs keep their results).
- A `REANALYZE` line: run the [Analysis Loop](#analysis-loop) again (it takes only the `pending` PRs), then this refresh again, and only then go on to the decision table. A PR whose head moves again before the decision is then `stale` ("stale, re-run needed"), with no action offered.

## Decision Step

```bash
export CC_REVIEW_CORE_DIR="{CORE_DIR}"; PROJECT_DIR="{PROJECT_DIR}"; RUN_ID="{RUN_ID}"
S="$CC_REVIEW_CORE_DIR/scripts"; RUN_DIR="$PROJECT_DIR/.cc-review/bulk/$RUN_ID"; cd "$PROJECT_DIR" || exit 1
"$S/bulk-state.sh" set-status "$RUN_ID" deciding >/dev/null
jq -c '.prs[] | {number, title, author, status, reason, counts, report, proposed, decision, flags, authored_by_user}' "$RUN_DIR/state.json"
```

Only PRs with status `analyzed` and no recorded `decision` are decided; `failed`, `closed`, `stale` and finished PRs appear in the table with their status and no action.

**Unattended mode**: no table and no question; apply the [Unattended Policy](#unattended-policy) and record its decisions, then continue at Apply.

**Deferred mode.** The whole decision is one step (SC-001):

1. Print the full table as text, one row per PR in the run, with the command's columns (see its Decision and Apply section) and the per-PR report path, so the user can read full findings before deciding.
2. Ask one question with these choices:
   - **Apply proposed actions**: every undecided analyzed PR gets its `proposed` action.
   - **Change actions per PR**: ask per PR, in batches of up to 4 PRs per prompt, offering exactly that PR's allowed actions (see the command's section). PRs the user does not change keep their proposed action.
   - **Skip all**: every undecided analyzed PR gets `skip`.
   - **Stop (resume later)**: record nothing, leave the run in `deciding`, print the summary and how to continue (`--bulk --resume`), and stop.
3. Follow-up questions that a choice needs (the "review findings" drill-down, triage human comments, edits) belong to this same step.

Record each decision as soon as it is made, so an interrupted decision step loses nothing (the value is a JSON array, for example `["post"]`, `["fix","post"]`):

```bash
export CC_REVIEW_CORE_DIR="{CORE_DIR}"; PROJECT_DIR="{PROJECT_DIR}"; RUN_ID="{RUN_ID}"
S="$CC_REVIEW_CORE_DIR/scripts"; RUN_DIR="$PROJECT_DIR/.cc-review/bulk/$RUN_ID"; cd "$PROJECT_DIR" || exit 1
N="{N}"
DECISION='["post"]' "$S/bulk-state.sh" pr-set "$RUN_ID" "$N" '.decision=(env.DECISION | fromjson)'
```

### Unattended Policy

`BULK_MODE=unattended` (`--unattended`, or config `interactive: false`) runs the whole run without a single prompt (FR-022). **No step of `review.md`, `triage.md` or this file may ask the user anything when `BULK_MODE=unattended`**: wherever a step would ask (an unfinished-run choice, the decision table, a per-finding drill-down, a human comment, the idea-inbox capture, a next-step menu), the default below applies instead.

The policy, per undecided analyzed PR:

| Command | PR | Decision | What happens |
|---|---|---|---|
| review | with findings | `["post"]` | the posting worker posts all new findings with `REVIEW_EVENT_OVERRIDE=COMMENT`: a non-blocking comment review, never a request for changes (FR-023) |
| review | without findings | `["marker"]` | the no-findings marker (`bulk-apply.sh marker`) |
| review | any | never `fix` | unattended mode changes no code on any PR branch |
| triage | with a prepared plan (`proposed` is `apply`) | `["apply"]` | the bot part of the plan: push the prepared commit, post the bot and cc-review thread replies, resolve the handled threads (FR-024) |
| triage | empty plan | `["skip"]` | nothing |

Human comments are left untouched in unattended mode: their `decision` stays `null`, so `bulk-apply.sh triage` posts nothing for them, and the summary lists each one under "Needs attention" with its PR, file, line and author. The idea-inbox capture is not offered.

Record the policy decisions in the state exactly as deferred mode records the user's (FR-025), so an interrupted unattended run resumes with `--bulk --resume --unattended` and applies what is left:

```bash
export CC_REVIEW_CORE_DIR="{CORE_DIR}"; PROJECT_DIR="{PROJECT_DIR}"; RUN_ID="{RUN_ID}"
S="$CC_REVIEW_CORE_DIR/scripts"; RUN_DIR="$PROJECT_DIR/.cc-review/bulk/$RUN_ID"; cd "$PROJECT_DIR" || exit 1
for N in $(jq -r '.prs[] | select(.status == "analyzed" and .decision == null) | .number' "$RUN_DIR/state.json"); do
  PROPOSED=$("$S/bulk-state.sh" pr-get "$RUN_ID" "$N" '.proposed // "skip"')
  case "$PROPOSED" in
    post) DECISION='["post"]' ;;
    marker) DECISION='["marker"]' ;;
    apply) DECISION='["apply"]' ;;
    *) DECISION='["skip"]' ;;
  esac
  DECISION="$DECISION" "$S/bulk-state.sh" pr-set "$RUN_ID" "$N" '.decision=(env.DECISION | fromjson)' >/dev/null
  echo "#$N: $DECISION"
done
```

The proposed actions already follow this policy (`post`, `marker`, `apply` or `skip`; `fix` is never proposed), so the block maps them one to one. An unfinished run of the same command makes a new unattended run stop with an error (FR-031, see Unfinished-Run Check); `--bulk --resume --unattended` continues it instead.

## Apply

```bash
export CC_REVIEW_CORE_DIR="{CORE_DIR}"; PROJECT_DIR="{PROJECT_DIR}"; RUN_ID="{RUN_ID}"
S="$CC_REVIEW_CORE_DIR/scripts"; RUN_DIR="$PROJECT_DIR/.cc-review/bulk/$RUN_ID"; cd "$PROJECT_DIR" || exit 1
"$S/bulk-state.sh" set-status "$RUN_ID" applying >/dev/null
jq -r '.prs[] | select(.decision != null and (.status == "analyzed" or .status == "applying" or .status == "partially-applied")) | "\(.number)\t\(.decision | join(","))"' "$RUN_DIR/state.json"
```

Apply PR by PR, in state order. For each PR:

**1. Skip.** A `["skip"]` decision sets the status `skipped` and removes the worktree; nothing is posted (a skipped PR gets no marker and is selected again by the next run, FR-021a):

```bash
export CC_REVIEW_CORE_DIR="{CORE_DIR}"; PROJECT_DIR="{PROJECT_DIR}"; RUN_ID="{RUN_ID}"
S="$CC_REVIEW_CORE_DIR/scripts"; RUN_DIR="$PROJECT_DIR/.cc-review/bulk/$RUN_ID"; cd "$PROJECT_DIR" || exit 1
N="{N}"
"$S/bulk-state.sh" pr-set "$RUN_ID" "$N" '.status="skipped"' >/dev/null
"$S/pr-worktree.sh" remove "$RUN_DIR/pr-$N/wt" && "$S/bulk-state.sh" pr-set "$RUN_ID" "$N" '.worktree=null' >/dev/null
```

**2. Head check.** Run this check **immediately before every push, every post and every marker** (not only once per PR, and whether or not this run pushed before), re-reading the PR (FR-030). The command's apply section names each place. `bulk-apply.sh head` compares the PR's head with `expected_head`, or a recorded `pending_push` (a push this run started; the remote at that sha means the push completed). Right after this run pushed, GitHub may still report the pre-push head for a moment, so when the reported head differs and this run has pushed to the PR, the branch tip read with `git ls-remote` from the PR's head repository decides:

```bash
export CC_REVIEW_CORE_DIR="{CORE_DIR}"; PROJECT_DIR="{PROJECT_DIR}"; RUN_ID="{RUN_ID}"
S="$CC_REVIEW_CORE_DIR/scripts"; RUN_DIR="$PROJECT_DIR/.cc-review/bulk/$RUN_ID"; cd "$PROJECT_DIR" || exit 1
N="{N}"
OUT=$("$S/bulk-apply.sh" head "$RUN_ID" "$N" 2>"$RUN_DIR/refresh.err"); RC=$?
case "$RC:$OUT" in
  "0:OK "*) echo "HEAD ok ${OUT#OK }" ;;
  "0:CLOSED "*)
    REASON="PR is ${OUT#CLOSED }" "$S/bulk-state.sh" pr-set "$RUN_ID" "$N" '.status="closed"' '.reason=env.REASON' >/dev/null
    echo "HEAD closed" ;;
  "0:MOVED "*)
    "$S/bulk-state.sh" pr-set "$RUN_ID" "$N" '.status="stale"' '.reason="stale, re-run needed: the head moved after analysis"' >/dev/null
    echo "HEAD stale" ;;
  75:*) echo "HEAD rate-limited" ;;
  *) echo "HEAD unknown: $(tail -n 1 "$RUN_DIR/refresh.err")" ;;
esac
```

- `HEAD ok`: continue with the command's apply steps (its Decision and Apply section).
- `HEAD closed` or `HEAD stale`: nothing is pushed or posted for this PR; remove its worktree and go to the next PR.
- `HEAD rate-limited`: pause the run as in Rate Limits (the PR keeps its decision, so a resume applies it).
- `HEAD unknown`: set the PR `failed` with that reason and go to the next PR.

**3. Command apply.** Set the status `applying` first (`'.status="applying"'`), then run the command's apply steps, with the head check above again immediately before each push, post and marker. Each completed sub-action is recorded by its id the moment it completes (`bulk-state.sh record`), so a resumed run never repeats it. The command's section sets the final status (`actioned`, `partially-applied`, `stale`, `cannot-push`) and removes the worktree when the PR is done.

## Review Decision and Apply

### Decision table

Print one row per PR in the run:

```bash
export CC_REVIEW_CORE_DIR="{CORE_DIR}"; PROJECT_DIR="{PROJECT_DIR}"; RUN_ID="{RUN_ID}"
S="$CC_REVIEW_CORE_DIR/scripts"; RUN_DIR="$PROJECT_DIR/.cc-review/bulk/$RUN_ID"; cd "$PROJECT_DIR" || exit 1
jq -r --arg dir "$RUN_DIR" '
  def cell: tostring | gsub("\\|"; "\\|");
  "| PR | Title | Author | C/I/M/N | Status | Report | Proposed |",
  "|---|---|---|---|---|---|---|",
  (.prs[] | "| #\(.number) | \(.title | cell) | \(.author | cell) | \(if .counts then "\(.counts.critical)/\(.counts.important)/\(.counts.minor)/\(.counts.notable)" else "-" end) | \(.status)\(if .reason then " (\(.reason | cell))" else "" end) | \(if .report then "\($dir)/\(.report)" else "-" end) | \(if .status == "analyzed" and .decision == null then .proposed else ((.decision // ["-"]) | join(" + ")) end) |")' "$RUN_DIR/state.json"
```

Explain the columns once in plain words (C/I/M/N: Critical, Important, Minor and Notable findings; the report holds the full findings) and the proposed actions ("post the review", "post a short no-findings note so later runs skip this PR").

### Allowed actions

Only an `analyzed` PR without a decision gets actions (FR-019):

| PR | Actions | Decision value |
|---|---|---|
| with findings | **Post review**: post all new findings, without per-finding questions | `["post"]` |
| with findings | **Review findings**: go through the findings one by one first (below), then post the accepted ones | nothing until the drill-down ends, then `["post"]` (or `["skip"]` when none is accepted) |
| with findings | **Skip**: post nothing; the next run selects the PR again | `["skip"]` |
| with at least one fixable finding (`fixable` > 0: a suggested fix, or Critical/Important), `authored_by_user`, no `local-unpushed` flag, run without `--no-fix` | **Apply fixes**: fix every fixable finding (any severity with a suggested fix, plus every Critical and Important finding) in the PR's worktree, commit and push to the PR branch | `["fix"]` |
| same as above | **Apply fixes, then post what remains** | `["fix","post"]` |
| without findings | **Post no-findings marker** | `["marker"]` |
| without findings | **Skip** | `["skip"]` |

"Apply proposed actions" gives `["post"]` or `["marker"]`; it never applies fixes.

**Review findings** (the one place where the coordinator reads findings, FR-018): for that PR, present `$PR_DIR/findings.json` in the single-PR Step 7.5g format of `review.md` (shortcut first; Critical and Important findings one at a time with accept, reject or edit; Minor and Notable findings in batches), as part of this decision step. Write the accepted findings, with any `edited_text`, as a JSON array to `$PR_DIR/accepted.json` with your file-write tool (never through a shell literal: findings quote PR code), record `["post"]`, and drop the findings from your context before the next PR. When the user accepts none, record `["skip"]`. Nothing is recorded while the drill-down is in progress: a decision step interrupted inside it leaves the PR undecided, and a resume offers it again.

### Apply

For each PR with a review decision, after the generic head check of [Apply](#apply) (`HEAD ok`) and with the status set to `applying`, run the decision's parts in this order. The worker inputs are those of Review Analysis, with `EXPECTED_HEAD` read again from the state (`pr-get ... .expected_head`), since a push moves it.

**Head check before every part.** Run the generic head check of [Apply](#apply) again immediately before the push of fix commits, immediately before dispatching the posting worker, and immediately before the marker, whatever happened before (a fix round that made no commit still gets its check before the post). Only `HEAD ok` continues; every other result is handled as described there.

**1. `fix`** (when the decision contains it). Skip this whole part when `.actions.pushed_sha` is already recorded: the fixes of this run are on the PR branch (a resumed run), and running the rounds again would apply them a second time on top of the pushed commit. Otherwise work in the PR's kept worktree; when `.worktree` is null or the directory is gone, set `failed` with `worktree missing; re-run needed` and go to the next PR:
1. Read the round limit: config `max_fix_rounds`, with the run's recorded `--max-rounds` applied on top, exactly as `review.md` Config Resolution does for a single PR:

```bash
export CC_REVIEW_CORE_DIR="{CORE_DIR}"; PROJECT_DIR="{PROJECT_DIR}"; RUN_ID="{RUN_ID}"
S="$CC_REVIEW_CORE_DIR/scripts"; RUN_DIR="$PROJECT_DIR/.cc-review/bulk/$RUN_ID"; cd "$PROJECT_DIR" || exit 1
# The recorded options hold "--flag" "value" pairs (or "--flag=value")
opt() { jq -r --arg f "$1" '.options as $o
  | ([$o | to_entries[] | select(.value == $f) | $o[.key + 1]] + [$o[] | select(startswith($f + "=")) | ltrimstr($f + "=")])
  | map(select(. != null)) | last // ""' "$RUN_DIR/state.json"; }
CONFIG_FLAG=$(opt --config); PROFILE_FLAG=$(opt --profile); MAX_ROUNDS_FLAG=$(opt --max-rounds)
source "$S/resolve-config.sh"
resolve_config_init --config "${CONFIG_FLAG:--}" --profile "${PROFILE_FLAG:--}" >/dev/null || exit 1
if [ -n "$MAX_ROUNDS_FLAG" ]; then resolve_config_apply_cli_overrides "max_fix_rounds=$MAX_ROUNDS_FLAG"; fi
resolve_config_validate_types || exit 1
echo "MAX_FIX_ROUNDS=$(resolve_config "max_fix_rounds" "3")"
```

2. Run the fix rounds of `review.md` "Worker Mode (bulk)" (f), up to `MAX_FIX_ROUNDS`, with `TEST_CMD` detected inside the worktree. Like the single-PR "Apply all suggested fixes" together with "Apply the important fixes", the rounds fix every fixable finding: any severity with a concrete suggested fix, plus every Critical and Important finding. The round loop stops when no fixable finding is left (the `FIXABLE` count of Review Analysis is 0), when a round made no commit, or at the round limit.
3. Head check, then push the fix commits:

```bash
export CC_REVIEW_CORE_DIR="{CORE_DIR}"; PROJECT_DIR="{PROJECT_DIR}"; RUN_ID="{RUN_ID}"
S="$CC_REVIEW_CORE_DIR/scripts"; RUN_DIR="$PROJECT_DIR/.cc-review/bulk/$RUN_ID"; cd "$PROJECT_DIR" || exit 1
N="{N}"
OUT=$("$S/bulk-apply.sh" review-push "$RUN_ID" "$N" 2>"$RUN_DIR/pr-$N/push.err"); RC=$?
echo "PUSH rc=$RC $OUT"
[ "$RC" -eq 0 ] || tail -n 1 "$RUN_DIR/pr-$N/push.err"
```

- `PUSHED <sha>`: the run recorded the push and the new expected head. Tell the user their local branch of this PR (if they have one) is now behind the remote.
- `UP-TO-DATE`: the rounds changed nothing; continue.
- `STALE` (the branch moved; the PR is now `stale`) or `DENIED` (no push permission, for example a fork; the PR is now `cannot-push`): nothing is posted; remove the worktree and go to the next PR.
- `rc=75`: pause the run as in Rate Limits.
- any other failure: set `failed` with the last error line, keep the worktree, go to the next PR.

With `["fix"]` alone, the PR is done after the push.

A PR that has recorded actions (a push, a review, replies) is never stored as `failed`: `bulk-state.sh pr-set` turns `failed` into `partially-applied` for it, so a resume applies the rest instead of analyzing the PR again and forgetting what was already pushed or posted.

**2. `post`** (when the decision contains it): skip this part when `.actions.review_id` is already recorded (a resumed run). Otherwise run the generic head check immediately before dispatching (always, whether or not the fix part pushed; after a push the expected head is the pushed commit), then dispatch the posting worker of `review.md` "Worker Mode (bulk)" (g) with `EXPECTED_HEAD`, `RUN_MARKER`, `PR_DIR`, `PROJECT_DIR`, `OWNER`, `REPO` and:
- `CAN_REQUEST_CHANGES`: `true` when the PR author is not the authenticated user (`authored_by_user` is false; GitHub does not let authors request changes on their own PR), otherwise `false`. The worker skips Step 5b, so it only knows this value from you; deferred mode then follows the 7.5k rule (a request for changes on someone else's PR with Critical or Important findings).
- `JUST_PUSHED`: `true` when this run pushed fix commits to the PR (`.actions.pushed_sha` is set), so the worker retries a "head moved" answer briefly while GitHub catches up with the push.
- in unattended mode `REVIEW_EVENT_OVERRIDE=COMMENT` (it wins over `CAN_REQUEST_CHANGES`, so an unattended run never blocks a PR).

With fixes applied, the worker posts only the findings the rounds did not fix. Map its status line:
- `STATUS ok review_id=<id> ...`: `"$S/bulk-state.sh" record "$RUN_ID" "$N" review_id <id>` (skip the record for `review_id=none`); show the review link to the user
- `STATUS failed reason=head-moved`: set `stale` with `stale, re-run needed: the PR head moved; review not posted`
- `STATUS failed reason=rate-limited`: pause as in Rate Limits
- anything else: set `failed` with the reason

**3. `marker`** (FR-021a), after the generic head check (`HEAD ok`) immediately before it:

```bash
export CC_REVIEW_CORE_DIR="{CORE_DIR}"; PROJECT_DIR="{PROJECT_DIR}"; RUN_ID="{RUN_ID}"
S="$CC_REVIEW_CORE_DIR/scripts"; RUN_DIR="$PROJECT_DIR/.cc-review/bulk/$RUN_ID"; cd "$PROJECT_DIR" || exit 1
N="{N}"
OUT=$("$S/bulk-apply.sh" marker "$RUN_ID" "$N" 2>"$RUN_DIR/pr-$N/marker.err"); RC=$?
echo "MARKER rc=$RC $OUT"
[ "$RC" -eq 0 ] || tail -n 1 "$RUN_DIR/pr-$N/marker.err"
```

`POSTED`, `FOUND` (this run's marker was already on the PR) and `RECORDED` are success. `STALE`: the PR is now `stale`. `rc=75`: pause. Any other failure: set `failed` with the error line.

**4. Done.** When every part of the decision succeeded, the PR is `actioned` and its worktree is removed:

```bash
export CC_REVIEW_CORE_DIR="{CORE_DIR}"; PROJECT_DIR="{PROJECT_DIR}"; RUN_ID="{RUN_ID}"
S="$CC_REVIEW_CORE_DIR/scripts"; RUN_DIR="$PROJECT_DIR/.cc-review/bulk/$RUN_ID"; cd "$PROJECT_DIR" || exit 1
N="{N}"
"$S/bulk-state.sh" pr-set "$RUN_ID" "$N" '.status="actioned"' >/dev/null
"$S/pr-worktree.sh" remove "$RUN_DIR/pr-$N/wt" && "$S/bulk-state.sh" pr-set "$RUN_ID" "$N" '.worktree=null' >/dev/null
```

## Triage Decision and Apply

### Decision table

Print one row per PR in the run:

```bash
export CC_REVIEW_CORE_DIR="{CORE_DIR}"; PROJECT_DIR="{PROJECT_DIR}"; RUN_ID="{RUN_ID}"
S="$CC_REVIEW_CORE_DIR/scripts"; RUN_DIR="$PROJECT_DIR/.cc-review/bulk/$RUN_ID"; cd "$PROJECT_DIR" || exit 1
jq -r --arg dir "$RUN_DIR" '
  def cell: tostring | gsub("\\|"; "\\|");
  "| PR | Title | Valid/Rejected/Deferred/Human | Status | Summary | Proposed |",
  "|---|---|---|---|---|---|",
  (.prs[] | "| #\(.number) | \(.title | cell) | \(if .counts then "\(.counts.bot_valid)/\(.counts.bot_rejected)/\(.counts.deferred)/\(.counts.human)" else "-" end) | \(.status)\(if .reason then " (\(.reason | cell))" else "" end)\(if (.flags | length) > 0 then " [\(.flags | join(", "))]" else "" end) | \(if .report then "\($dir)/\(.report)" else "-" end) | \(if .status == "analyzed" and .decision == null then .proposed else ((.decision // ["-"]) | join(" + ")) end) |")' "$RUN_DIR/state.json"
```

Explain the columns once in plain words (valid bot suggestions fixed in a prepared commit, rejected and deferred suggestions with drafted replies, human comments waiting for the user's answer; the summary file holds the details) and the flags (`local-unpushed`: fixes stay unpushed and only replies are posted; `cross-repo`: a fork, the push may be refused, and then only replies are posted).

### Allowed actions

Only an `analyzed` PR without a decision gets actions (FR-020):

| Action | Meaning | Decision value |
|---|---|---|
| **Apply** | push the prepared commit, post the replies, resolve the handled threads, and post the human replies the user approves below | `["apply"]` |
| **Skip** | nothing is pushed or posted; the threads stay open for the next run | `["skip"]` |

"Apply proposed actions" gives each PR its `proposed` action (`apply`, or `skip` for an empty plan).

**Human comments** (part of the same decision step, deferred mode only). After the per-PR choices, go through the human comments of every PR decided `apply`, one prompt per comment, as in single-PR Step 12. For each `.human[]` entry with `decision` null, show the PR, the file and line, the comment and the drafted reply (read these few fields with `jq`), then offer:
- **Approve**: post the drafted reply as it is
- **Edit**: ask for the reply text, then post that
- **Skip**: post nothing; the comment stays open

Record each answer in the plan right away. `DECISION` is `approve`, `edit` or `skip`. The reply text never passes through a shell literal (it quotes an untrusted comment and could contain `$(...)`): for **Approve** the block copies the drafted reply from the plan itself; for **Edit**, first write the user's text with your file-write tool to `$RUN_DIR/pr-<n>/reply-<comment id>.txt` and set `BODY_FILE` to that path; for **Skip** nothing is posted. A body without the `<!-- cc-review-triage -->` signature (an edited reply) gets it appended, so a resumed apply recognizes the posted reply and never posts it twice:

```bash
export CC_REVIEW_CORE_DIR="{CORE_DIR}"; PROJECT_DIR="{PROJECT_DIR}"; RUN_ID="{RUN_ID}"
S="$CC_REVIEW_CORE_DIR/scripts"; RUN_DIR="$PROJECT_DIR/.cc-review/bulk/$RUN_ID"; cd "$PROJECT_DIR" || exit 1
N="{N}"; CID="{COMMENT_ID}"
PLAN="$RUN_DIR/pr-$N/triage-plan.json"
case "$DECISION" in approve|edit|skip) ;; *) echo "Error: DECISION must be approve, edit or skip" >&2; exit 1 ;; esac
EDITED=""
if [ "$DECISION" = edit ]; then
  [ -n "${BODY_FILE:-}" ] && [ -s "$BODY_FILE" ] || { echo "Error: an edited reply needs BODY_FILE" >&2; exit 1; }
  EDITED="$BODY_FILE"
else
  EDITED="$(mktemp)"; : > "$EDITED"
fi
jq --argjson cid "$CID" --arg d "$DECISION" --rawfile edited "$EDITED" \
  '.human |= map(if .comment_id == $cid then .decision = $d
     | (if $d == "edit" then $edited
        elif $d == "approve" then (.draft // "")
        else "" end) as $b
     | .body = (if $b == "" then null
         elif ($b | contains("<!-- cc-review-triage")) then $b
         else $b + "\n\n<!-- cc-review-triage -->" end)
   else . end)' \
  "$PLAN" > "$PLAN.tmp" && mv "$PLAN.tmp" "$PLAN"
[ "$DECISION" = edit ] || rm -f "$EDITED"
```

A human comment left undecided (the step was stopped, or unattended mode) keeps `decision` null: apply does not answer it, and the summary lists it under "Needs attention".

### Apply

For each PR with `["apply"]`, run the generic head check of [Apply](#apply) immediately before this block (`HEAD ok` only; the script pushes and posts), with the status set to `applying`:

```bash
export CC_REVIEW_CORE_DIR="{CORE_DIR}"; PROJECT_DIR="{PROJECT_DIR}"; RUN_ID="{RUN_ID}"
S="$CC_REVIEW_CORE_DIR/scripts"; RUN_DIR="$PROJECT_DIR/.cc-review/bulk/$RUN_ID"; cd "$PROJECT_DIR" || exit 1
N="{N}"
export TRIAGE_STATE_FILE="$PROJECT_DIR/.cc-review/.triage-state.json"
OUT=$("$S/bulk-apply.sh" triage "$RUN_ID" "$N" 2>"$RUN_DIR/pr-$N/apply.err"); RC=$?
echo "APPLY rc=$RC $OUT"
[ "$RC" -eq 0 ] || tail -n 1 "$RUN_DIR/pr-$N/apply.err"
STATUS=$("$S/bulk-state.sh" pr-get "$RUN_ID" "$N" .status)
if [ "$RC" -ne 0 ] && [ "$RC" -ne 75 ] && [ "$STATUS" = applying ]; then
  REASON="apply failed: $(tail -n 1 "$RUN_DIR/pr-$N/apply.err")" \
    "$S/bulk-state.sh" pr-set "$RUN_ID" "$N" '.status="partially-applied"' '.reason=env.REASON' >/dev/null
  STATUS=partially-applied
fi
case "$STATUS" in
  actioned|stale|cannot-push)
    "$S/pr-worktree.sh" remove "$RUN_DIR/pr-$N/wt" && "$S/bulk-state.sh" pr-set "$RUN_ID" "$N" '.worktree=null' >/dev/null ;;
esac
echo "STATUS=$STATUS PUSHED=$("$S/bulk-state.sh" pr-get "$RUN_ID" "$N" '.actions.pushed_sha // "none"')"
```

The script itself records every sub-action (push, each reply, each resolution) and sets the final status:
- `ACTIONED ...`: done. When it pushed, tell the user that their local branch of this PR (if they have one) is now behind the remote, and that CI was not checked (the summary suggests `/triage --pr <n>` for CI repair).
- `PARTIAL ...` (some replies or resolutions failed), or a push or thread-read error: the PR is `partially-applied` and keeps its worktree; a resume retries only what is missing.
- `STALE` (the branch moved before the push, so nothing was pushed or posted; or it moved right after the push, so the fixes are pushed but no reply was posted) or `DENIED ...` (no push permission, for example a fork; the fixes are not pushed, the replies that do not depend on them are posted, and the PR is `cannot-push`): go to the next PR.
- `rc=75`: pause the run as in Rate Limits (the PR stays `applying`, so a resume applies it).

**Idea inbox.** When the run was started with `--idea-inbox <path>` and `BULK_MODE=deferred`, offer the single-PR Step 14 capture once, after all PRs are applied, over the deferred and rejected replies of the PRs that were applied (`jq '[.replies[] | select(.action == "deferred" or .action == "rejected")]'` on their plans). Unattended mode never offers it.

## Summary

```bash
export CC_REVIEW_CORE_DIR="{CORE_DIR}"; PROJECT_DIR="{PROJECT_DIR}"; RUN_ID="{RUN_ID}"
S="$CC_REVIEW_CORE_DIR/scripts"; RUN_DIR="$PROJECT_DIR/.cc-review/bulk/$RUN_ID"; cd "$PROJECT_DIR" || exit 1
# finished once it is not paused and every PR is finished for the run
echo "RUN_STATUS=$("$S/bulk-state.sh" finish "$RUN_ID")"
SUMMARY=$("$S/bulk-state.sh" summary "$RUN_ID") && cat "$SUMMARY"
```

Show the summary to the user (FR-034): every selected and excluded PR with its outcome and reason, kept worktrees, and links to posted reviews. Then, in plain words:
- the run is finished, or why it is not: PRs that failed (a resume retries them, up to 3 failed attempts per PR in all; a PR that failed 3 times stays failed and no longer keeps the run open, FR-028), a decision step that was stopped, or a pause for the rate limit, each with the command to continue (`--bulk --resume`; scheduled jobs: `--bulk --resume --unattended`). A paused run (status `paused`) always gets the line "GitHub rate limit reached; the run is paused. Continue later with `--bulk --resume` (scheduled jobs: `--bulk --resume --unattended`)."
- the state directory `.cc-review/bulk/<run-id>/` is kept (FR-032); cc-review never deletes it

## Resume

Reached from the [Unfinished-Run Check](#unfinished-run-check) with a run id: the given `RESUME_ID` (unknown ids already failed there with `Error: no unfinished <command> run '<id>'; unfinished runs: ...`), or the newest unfinished run of `BULK_COMMAND`, or the run the user chose to resume in deferred mode. With no unfinished run, that check already decided: unattended starts a new run with the flags given, deferred prints `No unfinished <command> run to resume.` and stops. Print `Resuming run <id>.` and keep it as `RUN_ID`.

A paused run (rate limit) and an interrupted run resume the same way.

**1. Validate the state and the flags (FR-029).** The run continues with its recorded selector, mode and options; only `--bulk`, the run id and an `--unattended` that matches the recorded mode may be given alongside `--resume`. Set `PER_PR_GIVEN` to the per-PR options the user passed (space-separated flag names, empty when none), `REQUESTED_MODE` to `BULK_MODE` as computed in Inputs, and `NON_INTERACTIVE=true` when this session cannot ask the user anything (a headless or scheduled run), otherwise `false`:

```bash
export CC_REVIEW_CORE_DIR="{CORE_DIR}"; PROJECT_DIR="{PROJECT_DIR}"; RUN_ID="{RUN_ID}"
S="$CC_REVIEW_CORE_DIR/scripts"; RUN_DIR="$PROJECT_DIR/.cc-review/bulk/$RUN_ID"; cd "$PROJECT_DIR" || exit 1
# An invalid state file stops the resume and is never rewritten
"$S/bulk-state.sh" validate "$RUN_ID" >/dev/null || exit 1
EXTRA=""
extra() { EXTRA="${EXTRA:+$EXTRA }$1"; }
if [ "${ALL_OPEN_FLAG:-}" = true ]; then extra --all-open; fi
if [ "${SEARCH_GIVEN:-}" = true ]; then extra --search; fi
if [ -n "${LIMIT_FLAG:-}" ]; then extra --limit; fi
if [ "${NO_FIX:-}" = true ]; then extra --no-fix; fi
if [ -n "${CONFIG_FLAG:-}" ]; then extra --config; fi
if [ -n "${PROFILE_FLAG:-}" ]; then extra --profile; fi
if [ -n "${IDEA_INBOX_FLAG:-}" ]; then extra --idea-inbox; fi
if [ -n "${PER_PR_GIVEN:-}" ]; then extra "$PER_PR_GIVEN"; fi
if [ -n "${PR_FLAG:-}" ]; then
  echo "Error: --bulk and --pr cannot be combined; --pr names a single PR" >&2; exit 1
fi
if [ -n "$EXTRA" ]; then
  echo "Error: --resume continues run $RUN_ID with its recorded options; remove $EXTRA" >&2; exit 1
fi
RECORDED_MODE=$(jq -r '.mode' "$RUN_DIR/state.json")
if [ "${REQUESTED_MODE:-deferred}" = unattended ] && [ "$RECORDED_MODE" = deferred ]; then
  echo "Error: run $RUN_ID was started in deferred mode" >&2; exit 1
fi
if [ "$RECORDED_MODE" = unattended ] && [ "${REQUESTED_MODE:-deferred}" != unattended ] && [ "${NON_INTERACTIVE:-false}" = true ]; then
  echo "Error: run $RUN_ID was started in unattended mode" >&2; exit 1
fi
echo "RESUME ok mode=$RECORDED_MODE options=$(jq -c '.options' "$RUN_DIR/state.json")"
```

Set `BULK_MODE` to the recorded mode (an unattended run resumes unattended, FR-025; when the user resumed it interactively without `--unattended`, say so in one line), and restore the per-PR options, `--no-fix`, `--config`, `--profile` and `--idea-inbox` from the recorded `options`.

**2. Re-read the heads and plan the resume.** Read the current head of every PR that is not finished, then let `resume-plan` apply the transition rules: an analysis is kept only at an unchanged head with its report, kept worktree and prepared commit still on disk; `analyzing` and `failed` PRs and moved heads are analyzed again (a PR that already failed 3 times is finished and stays `failed`, FR-028); `applying`, `partially-applied` and decided PRs are applied, with a remote at a recorded `pending_push` counted as pushed:

```bash
export CC_REVIEW_CORE_DIR="{CORE_DIR}"; PROJECT_DIR="{PROJECT_DIR}"; RUN_ID="{RUN_ID}"
S="$CC_REVIEW_CORE_DIR/scripts"; RUN_DIR="$PROJECT_DIR/.cc-review/bulk/$RUN_ID"; cd "$PROJECT_DIR" || exit 1
HEADS="{}"
for N in $("$S/bulk-state.sh" open-prs "$RUN_ID"); do
  H=$("$S/pr-worktree.sh" head "$N" 2>"$RUN_DIR/refresh.err"); RC=$?
  if [ "$RC" -eq 75 ]; then "$S/bulk-state.sh" set-status "$RUN_ID" paused >/dev/null; echo "RATE_LIMITED"; exit 0; fi
  # An unreadable head stays unknown; the head check before apply catches a move
  if [ "$RC" -eq 0 ]; then HEADS=$(printf '%s' "$HEADS" | jq -c --arg n "$N" --arg h "$H" '.[$n] = $h'); fi
done
PLAN=$("$S/bulk-state.sh" resume-plan "$RUN_ID" "$HEADS") || exit 1
printf 'PLAN %s\n' "$PLAN"
jq -r '"STATUS \(.status)", "UNDECIDED \([.prs[] | select(.status == "analyzed" and .decision == null) | .number] | join(","))"' "$RUN_DIR/state.json"
```

`RATE_LIMITED`: the run is set to `paused` with its PRs as they were; go to Summary, which tells the user to resume later.

**3. Continue.** Tell the user in one line how many PRs are analyzed again, wait for a decision, and are applied. Then run the normal flow from [Analysis Loop](#analysis-loop) on: the analysis loop handles the `reanalyze` PRs (they are `pending` now), the [Pre-Decision Refresh](#pre-decision-refresh) and [Decision Step](#decision-step) cover the undecided analyzed PRs (only undecided PRs are offered; actioned PRs are never decided again), and [Apply](#apply) takes the `apply` list together with the new decisions. Skip each part that has nothing to do.

**Nothing is done twice (FR-028).** Every completed sub-action has its id in the state and is skipped: `bulk-apply.sh` skips recorded pushes, replies and resolutions, and the posting step is skipped when `review_id` is recorded. Before posting a review that is not recorded, the posting worker looks for this run's marker on the PR and reports that review instead (`review.md` Worker Mode (g)); `bulk-apply.sh marker` does the same for the marker, and `bulk-apply.sh triage` records a reply this run already posted (a reply by the user with `<!-- cc-review-triage`, created since the run started) instead of posting it again. A fix push already recorded (`.actions.pushed_sha`) skips the fix rounds.
