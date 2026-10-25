# Data Model: Bulk Review and Bulk Triage

All state lives under `.cc-review/bulk/` in the repository the command was invoked in.

```text
.cc-review/bulk/
├── .gitignore                    # "*" (FR-033)
└── <run-id>/                     # e.g. 20261025-101500-review
    ├── state.json                # source of truth (BulkRun)
    ├── state.md                  # rendered view, regenerated on every mutation
    ├── summary.md                # final summary (FR-034)
    └── pr-<n>/
        ├── wt/                   # isolated worktree (detached), removed when PR is done
        ├── changed-files         # one path per line, relative to wt
        ├── findings/<reviewer>.json   # review: raw findings per reviewer
        ├── reviewers.json        # review: per-reviewer status line (dispatched/skipped/failed, counts)
        ├── merged.json           # review: Step 4 output
        ├── meta/{skeptic,calibrator}.json  # review: Step 4b outputs (when gate passes)
        ├── findings.json         # review: final findings after meta-review
        ├── accepted.json         # review: drill-down result (optional)
        ├── review-findings.md    # review: per-PR report (FR-013)
        ├── triage-plan.json      # triage: prepared actions
        └── triage-summary.md     # triage: per-PR summary
```

## BulkRun (`state.json` root)

| Field | Type | Notes |
|---|---|---|
| `version` | int | `1` |
| `run_id` | string | `<YYYYMMDD-HHMMSS>-<command>` |
| `command` | `review` \| `triage` | |
| `mode` | `deferred` \| `unattended` | |
| `selector` | object | `{kind: "default"\|"all-open"\|"search", query: string\|null, limit: int}` |
| `options` | string[] | per-PR flags passed through (reviewer selection, `--no-meta-review`, ...) |
| `repo` | object | `{owner, name, root}` (root = absolute path of invoking repo) |
| `gh_user` | string | login of the authenticated user |
| `status` | enum | `selecting` → `analyzing` → `deciding` → `applying` → `finished`; `paused` (rate limit); `abandoned` |
| `created_at`, `updated_at` | ISO-8601 | |
| `prs` | PrEntry[] | ordered by processing order |
| `removed_worktrees` | string[] | optional; worktrees removed when the run was abandoned (listed in `summary.md`) |
| `excluded` | Exclusion[] | |

## PrEntry

| Field | Type | Notes |
|---|---|---|
| `number`, `title`, `author`, `head_ref` | | `head_ref` = branch name |
| `head_repo_url` | string | push target (fork-aware) |
| `analyzed_head` | sha \| null | head at analysis time |
| `base_ref` | string | PR base branch; diffs use `origin/<base_ref>` |
| `expected_head` | sha \| null | `analyzed_head`, then last sha this run pushed (FR-030) |
| `pending_push` | sha \| null | sha about to be pushed; a remote head equal to it counts as pushed on resume |
| `status` | enum | see transitions |
| `reason` | string \| null | failure/stale/cannot-push text |
| `dir` | string | `pr-<n>` relative to run dir |
| `worktree` | string \| null | absolute path while kept |
| `counts` | object | review: `{critical, important, minor, notable}`; triage: `{bot_valid, bot_rejected, deferred, human}` |
| `report` | string \| null | relative path to per-PR report |
| `fixable` | int | review: findings with a concrete suggested fix, plus every Critical and Important finding; "apply fixes" is offered only when above 0 |
| `authored_by_user` | bool | gates "apply fixes" (FR-019) |
| `flags` | string[] | `local-unpushed`, `cross-repo` |
| `proposed` | string \| null | FR-021 |
| `decision` | string[] \| null | e.g. `["post"]`, `["fix","post"]`, `["review-findings"]`, `["marker"]`, `["apply"]`, `["skip"]` |
| `actions` | object | completed sub-actions: `{pushed_sha, review_id, replies: {<comment_id>: <reply_id>}, resolved: [<thread_id>]}` |
| `failed_attempts` | int | times the PR was set to `failed`, counted across resumes; at 3 the PR is no longer retried (FR-028) |
| `reanalyses` | int | re-analyses after a head move between analysis and decision; a move after the first one makes the PR `stale` (FR-030) |

### PR status transitions

```text
pending ──► analyzing ──► analyzed ──► (decision) ──► applying ──► actioned
   ▲            │             │                         │   └──► partially-applied ──(resume)──► applying
   │            ▼             ├──► skipped              ├──► stale
   └──(resume)─ failed        └──► closed               └──► cannot-push
```

- `analyzing` on resume → treated as `pending` (re-analyze).
- `analyzed` on resume: kept if current head == `analyzed_head` and the worktree (when required) exists, otherwise reset to `pending`.
- `analyzed` whose head moved before the decision step (pre-decision refresh): `bulk-state.sh reanalyze` resets it to `pending` and counts it in `reanalyses`, so the run analyzes it again before the decision table; with `reanalyses` already at 1 it becomes `stale`.
- `failed` on resume → `pending`, unless `failed_attempts` reached 3: then it stays `failed` and is terminal. A PR with recorded actions is never set to `failed` (`bulk-state.sh pr-set` turns it into `partially-applied`), so a reset never forgets a push or post.
- A reset to `pending` clears `pending_push` and `actions.pushed_sha` (the next analysis prepares a new commit to push) and keeps the recorded replies and resolutions for dedup.
- `applying` and `partially-applied` on resume → apply list (completed sub-actions are skipped by their recorded ids).
- Analyzed PRs with a decision but no terminal status → apply list.
- `pending` on a deferred resume whose analysis was cut short by the user (`bulk-state.sh cut-short`, FR-028a) → `not-analyzed`, except the interrupted PR when the user chose to finish it first. Nothing is posted for a `not-analyzed` PR, so a later run selects it again.
- `actioned`, `skipped`, `stale`, `cannot-push`, `closed`, `not-analyzed`, and `failed` with 3 failed attempts are terminal for the run.
- Run `status` becomes `finished` when every PR is terminal.

## Exclusion

`{number, title, reason}` where reason ∈ `reviewed-at-head`, `no-open-threads`, `draft`, `over-limit`.

## TriagePlan (`pr-<n>/triage-plan.json`)

```json
{
  "pr": 20,
  "prepared_commit": "<sha or null>",
  "base_head": "<analyzed head>",
  "replies": [{"comment_id": 123, "thread_id": "PRRT_..", "author": "coderabbitai", "path": "a.sh", "line": 10, "body": "...", "action": "accepted|rejected|deferred|fix-failed", "resolve": true, "self_resolves": false}],
  "cc_review_threads": [{"comment_id": 456, "thread_id": "PRRT_..", "body": "...", "resolve": true}],
  "stale_resolutions": ["PRRT_.."],
  "human": [{"comment_id": 789, "path": "b.sh", "line": 3, "author": "alice", "text": "...", "draft": "...", "decision": null}]
}
```

Human entries also carry `thread_id` and `assessment` from the worker. `draft` is the drafted reply, with its signature. The decision step sets `decision` to `approve`, `edit` or `skip` and `body` to the text to post (`draft` for `approve`, the user's text for `edit`); `bulk-apply.sh triage` posts only `approve` and `edit` entries, and never resolves a human thread.

`self_resolves` marks bots whose profile resolves threads on their own (triage Step 9 skips those). CI is not checked in bulk mode; the summary adds the fixed "CI not checked" line for every pushed PR.

`thread_id` values are re-resolved by path+line after push (T Step 7c logic), because GitHub re-posts threads on outdated lines.

## Finding file (`findings/<reviewer>.json`, `merged.json`, `findings.json`)

Raw reviewer files (`findings/<reviewer>.json`) hold what the reviewer would have reported (the ReportFindings shape: `file, line, summary, severity, category, confidence, failure_scenario, ...`) and are normalized by the merge worker. `merged.json` and `findings.json` are JSON arrays of objects that conform to the existing finding schema (`review/core/schemas/finding.schema.json`: `severity`, `file`, `line_start`, `line_end`, category, source, meta-review fields, ...). File paths are **relative to the worktree** (as in single-PR reports). Reviewer status lines go to `reviewers.json` as `[{name, kind, status: "ok"|"skipped"|"failed", reason, count, positive_observations: []}]`. A command reviewer not run in a fork PR's checkout is `skipped` with the reason `untrusted checkout` (FR-011a).
