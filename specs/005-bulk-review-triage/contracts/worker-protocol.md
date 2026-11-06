# Contract: File-Backed Worker Protocol

This contract describes how the bulk coordinator (`core/commands/bulk.md`) keeps its own context bounded (FR-010).

Every subagent gets absolute paths, writes its result to a file in `PR_DIR=<run dir>/pr-<n>`, and **returns exactly one status line**. No subagent dispatches further subagents. Every fan-out (reviewers, meta critics, fix-round re-reviews) is driven by the coordinator.

The coordinator never reads findings files into its own context; it reads counts with `jq`. There is one exception: the interactive "review findings" drill-down (apply phase) presents one PR's findings to the user.

Status line format: `STATUS <ok|failed> <key>=<value> ...`, for example `STATUS ok findings=7`. A worker that hits a hosting-service rate limit returns `STATUS failed reason=rate-limited`. The coordinator maps that to run status `paused` and stops the loop. Any other failure, an unparseable status, or a missing output file marks the reviewer, or the PR when the worker is PR-level, as failed.

## Variables shared by all review workers

`CORE_DIR`, `RUNTIME` (`$CORE_DIR/scripts/reviewer-runtime.sh`), `PROJECT_DIR` (invoking repo), `REVIEW_ROOT` (worktree), `PR_NUMBER`, `PR_DIR`, `EXPECTED_HEAD`, `BASE_REF` (`origin/<baseRefName>`), `MIN_CONFIDENCE`, `RUN_MARKER` (`<run-id>/pr-<n>`), `UNTRUSTED_CHECKOUT` (`true` for a fork PR: command reviewers are skipped as `untrusted checkout` unless `allow_untrusted_checkout.<name>` is true, FR-011a).

## Review, per PR (analysis phase)

Before the reviewer workers run, a **prep worker** subagent, fresh for this PR, executes review.md Steps 1 to 3 in worker mode, so no judgment about one PR happens in a context that has seen another:
- discovery, selection, preconditions, goals, scope, prior review history and prior finding verification, in the prep worker
- `$PR_DIR/reviewers.json` is written from `REVIEWERS_JSON` together with each reviewer's planned status (`dispatched`, `skipped` with reason, `disabled`)
- command reviewers run in the prep worker's shell with `( cd "$REVIEW_ROOT" && ... )`, and their raw output stays in `$PR_DIR/commands/<name>.{out,err,rc}`; only the exit code is recorded in `reviewers.json`
- one prompt file per prompt reviewer, `$PR_DIR/prompts/<name>.md`, and the dispatch list `$PR_DIR/dispatch.json`; returns `STATUS ok dispatch=<n> commands=<n> mode=<scope mode or none>`

The coordinator never reads PR content: it dispatches each prompt reviewer with only the path of its prompt file.

Every early stop in Steps 1 to 3 (no reviewers left, selection error, diff failure) makes the prep worker return `STATUS failed reason=<step>: <error>`, a per-PR failure with a reason (FR-015), never an `exit` of the coordinator.

| # | Worker | Input | Output | Return |
|---|---|---|---|---|
| 1 | Prompt reviewer (one per dispatched prompt reviewer, parallel as configured) | Same prompt as single-PR Step 3. The Review Target lists **absolute** paths under `REVIEW_ROOT`, and `file` is reported relative to it. The Output section is replaced by: "write your findings as a JSON array (same fields you would report) to `<PR_DIR>/findings/<name>.json` and positive observations to `<PR_DIR>/findings/<name>.positive.json`" | findings file | `STATUS ok findings=<n>` |
| 2 | Merge worker | `reviewers.json`, `findings/*.json`, `commands/*.out`, `RUNTIME`, `CORE_DIR`, `MIN_CONFIDENCE`, and the text of review.md Step 3 "Severity Filtering", the command-reviewer parsing rules, and Step 4 | `merged.json` | `STATUS ok merged=<n> critical=.. important=.. minor=.. notable=..` |
| 3 | Meta-review Skeptic and Calibrator (only when the Step 4b gate passes on the merged count) | `merged.json`, the changed-files path, the same agent prompt files, plus an override: "write your result JSON to `<PR_DIR>/meta/<skeptic|calibrator>.json` instead of reporting it, and return a STATUS line" | meta files | `STATUS ok verdicts=<n>` |
| 4 | Report worker | `merged.json`, meta files, `reviewers.json`, the positive files, and the Step 4b apply rules plus the Step 7 report format | `findings.json`, `review-findings.md` | `STATUS ok critical=.. important=.. minor=.. notable=.. report=<path>` |

What the merge worker does:
1. Parses each command reviewer's output according to that reviewer's parsing notes.
2. Normalizes every entry to the finding schema (`$RUNTIME helper map_severity`, `source_agent`, `line_start`/`line_end`).
3. Applies the `MIN_CONFIDENCE` filter.
4. Applies the Step 4 dedup rules, including `dedup: isolated`.
5. Updates the per-reviewer counts in `reviewers.json`.

The coordinator then sets the PR to `analyzed` with counts and `report`. It removes the worktree unless "apply fixes" may be offered (`authored_by_user`, not `local-unpushed`, no `--no-fix`).

## Review, per PR (apply phase)

| Decision | Driver | Behavior |
|---|---|---|
| `fix` | Coordinator loop, up to `max_fix_rounds` | Per round: (a) a **fix worker** subagent applies every suggested fix of the current `findings.json` (any severity, as the single-PR "Apply all suggested fixes") in `REVIEW_ROOT` (absolute paths), runs the detected test command, commits in the worktree, writes the list of changed files to `$PR_DIR/round-<k>/changed-files`, and returns `STATUS ok fixed=<n> commit=<sha>`; (b) the coordinator re-runs analysis workers 1 to 4 on that round's changed files, with outputs under `$PR_DIR/round-<k>/`, and `findings.json` is replaced by the round's result. The loop stops when no finding with a concrete fix remains unfixed, when a round made no commit, or when the round limit (`max_fix_rounds` with the run's `--max-rounds`) is reached. Then `bulk-apply.sh review-push`. |
| `review-findings` | Coordinator (interactive, the documented exception) | Presents `findings.json` in the Step 7.5g format, writes `accepted.json`, then continues as `post` |
| `post` | Drafting worker (subagent), then the coordinator | Superseded by `specs/011-review-draft-approval/contracts/worker-protocol.md`: in the Prepare pass the drafting worker runs the Draft half of Step 7.5 non-interactively (findings from `accepted.json` or `findings.json`, `commit_id` = `EXPECTED_HEAD`, review type `COMMENT` in unattended mode via `REVIEW_EVENT_OVERRIDE`, otherwise the single-PR rule with `CAN_REQUEST_CHANGES`, marker `cc-review:run-id:<RUN_MARKER>`, inline prose rewrite of slot text, 7.5c file existence via `git ls-tree -r --name-only "$EXPECTED_HEAD"` in `PROJECT_DIR`) and writes nothing to GitHub; it returns `STATUS ok draft=<dir> fingerprint=<sha> lint=<n>`. The coordinator then shows every draft in the Approve pass and posts the approved ones in the Post pass with `post-review.sh` (fingerprint, commit, head, marker, history and conversation checks) |
| `marker` | Script | `bulk-apply.sh marker` |
| `skip` | none | Status `skipped`, worktree removed |

Before the decision table is rendered, and again before every push or post, the coordinator re-reads each non-terminal PR's state and head:
- a closed or merged PR → `closed`
- a head different from `expected_head` (or from a recorded `pending_push` sha, see scripts.md) → `stale`

## Triage, per PR

| Phase | Driver | Behavior |
|---|---|---|
| Analysis | Triage worker (subagent) | Executes triage.md with `TRIAGE_MODE=prepare`, `TRIAGE_ROOT=<wt>`, `TRIAGE_STATE_FILE=$PROJECT_DIR/.cc-review/.triage-state.json`, `TRIAGE_PLAN=$PR_DIR/triage-plan.json`, `--pr <n>`. Writes the plan and `triage-summary.md`, and commits fixes in the worktree. Returns `STATUS ok valid=.. rejected=.. deferred=.. human=.. commit=<sha or none>` |
| Decision | Coordinator | Per PR: `apply` or `skip`. Per human comment: the triage Step 12 options. The choice is written into `triage-plan.json` `.human[].decision` |
| Apply | Script | `bulk-apply.sh triage <run> <n>` |

Triage worktree keep rule: keep the worktree while `prepared_commit` is set and the PR is undecided or partially applied. Otherwise remove it after analysis or apply.
