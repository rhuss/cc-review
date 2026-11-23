# Contract: `issue_bulk.py` and `run_state.py`

All subcommands: stdlib Python 3.9+, run as `python3 -B <core>/scripts/issue_bulk.py <subcommand> ...`. Standard output is one JSON line unless stated; errors go to standard error as `Error: <actionable message>` with exit code 1 (usage errors exit 2). No subcommand passes untrusted issue text into a shell command, and no subcommand runs project code.

## `issue_bulk.py`

| Subcommand | Arguments | Effect | Output |
|---|---|---|---|
| `validate` | the raw user arguments | Applies the spec FR-002 table, no service call | `{"mode":"new"\|"resume","search","limit","scan","repo","resume_id"}` |
| `select` | `--repo R --limit N --scan S [--search Q] --out FILE` | Paged search and classification (R-001 to R-003) | writes `selection.json`; prints `{"scanned","selected","skipped","ceiling_reached","exhausted"}` |
| `start` | `--selection FILE` | Only when `selected` is non-empty. Resolves repository, user, matching checkout, push permission, default branch; creates the run with `run_state.init`; seeds items | `{"run_id","run_dir","selected","fixes_available","fixes_unavailable_reason"}` |
| `collect` | `<run> <n>` | Collects the issue into `items/<n>/snapshot.json`, merging `linked_prs`; on failure marks `assessment_failed` | `{"number","ok","warnings"}` |
| `render-item` | `<run> <n>` | Validates `assessment.json`, renders `rendered.md` with the run marker, computes label and `fix_eligible`, hashes the rendered text | `{"number","recommendation","label","fix_eligible","fix_ineligible_reason","linked_open_prs"}` |
| `next` | `<run> <phase> [--session S]` | First item in selection order needing the phase (table below); for `post` and `fix`, items with `attempt_session == S` are excluded | `{"number": n or null}`; for `assess` also `"stored"` (an `assessment.json` exists) |
| `fail` | `<run> <n> --reason R` | Marks the item `assessment_failed` with the reason | `{"number","phase"}` |
| `decide` | `<run> <n> --post post\|skip [--action fix\|leave\|review]` | Records the decision with the current `rendered_sha256`; rejects `fix` when not eligible and `review` without open linked PRs | `{"number","decision"}` |
| `post` | `<run> <n> [--session S]` | Refuses when `rendered.md` no longer matches the decided hash; re-check (open state, skip rules, run marker), then comment, then label existence check and add; each recorded | `{"number","comment","label","reason","comment_url"}` |
| `fix-prepare` | `<run> <n> [--session S]` | For a new fix, re-reads the issue and abandons when it was closed, no longer qualifies or a contributor PR references it; records ownership, fetches the default branch, branch conflict checks, `worktree add --no-track` (or reuse a recorded one), checkout and git-metadata snapshot | `{"number","worktree","branch","worker_needed"}` or `{"number","abandoned"}` |
| `fix-measure` | `<run> <n> [--session S]` | Checks git metadata without running git, reads `fix.json`, verifies the snapshot (the reason names changed paths), stages, abandons a binary change, measures, enforces the bound, records the tree id | `{"number","within_bound","size","reason"}` |
| `fix-publish` | `<run> <n> [--session S]` | Commit without hooks (adopting an unrecorded commit of the measured tree), refuse an `origin` push URL for another repository, push the recorded commit (`pending: "push"` when it fails or is unconfirmed), draft PR; each step recorded; resume-safe (R-009) | `{"number","pr_url","pending","abandoned"}` |
| `fix-cleanup` | `<run> <n> [--session S]` | Remove worktree and local branch (also for a pushed branch with a pending PR); set phase `done` once the fix is finished | `{"number","cleaned"}`, or `{"number","cleaned": false,"reason"}` when git files changed and cleanup is left to the maintainer |
| `abandon-run` | `<run>` | Removes the run's fix worktrees and local fix branches, then sets status `abandoned` | `{"run_id","status","cleaned","cleanup_failed","pushed_without_pr"}` |
| `item` | `<run> <n> [--session S]` | One item's decision fields (approval pass) | `{"number","title","url","phase","recommendation","label","fix_eligible","fix_ineligible_reason","linked_prs","decision","post","failure"}` |
| `guard-begin` | `<run> <n> [--session S]` | Digest of state.json (canonical) and all run files outside `items/<n>/`, before an assessment worker | `{"number","digest"}` |
| `guard-end` | `<run> <n> --digest D [--session S]` | Compares the digest; any change records `extra.halted` and exits 1 naming the item | `{"number","unchanged": true}` |
| `record-handoff` | `<run> [<pr,...>]` | Stores PR numbers handed to bulk review; without a list, all open non-maintainer linked PRs of review follow-ups | `{"handoff_prs","repository","command","closed"}` (PR state re-read; closed or merged PRs are left out) |
| `report` | `<run>` or `--selection FILE` | Prints the final Markdown report (not JSON); with a run, marks it finished unless a PR, post, fix, assessment or decision is still pending (then it stays running and the report prints the resume command); with only a selection, prints the "No issues matched" or "All candidates skipped" report without a run | Markdown |

Every subcommand that takes `<run>` holds an exclusive lock on the run for its duration. Every call with `--session S` records S in `<run>/lock`; another session is refused while that lock is younger than 30 minutes. A run halted by `guard-end` refuses everything except `item`, `report` and `abandon-run`. Fix steps that fail record the fix as abandoned (or its PR as pending) instead of leaving it open.

### `next` phases

| Phase | Item qualifies when |
|---|---|
| `collect` | `phase == "selected"` |
| `assess` | `phase == "collected"`, or `phase == "assessed"` with no `rendered.md` |
| `decide` | `phase == "assessed"` and `decision` is null |
| `post` | `phase == "decided"` and `post.comment` in `pending`, `failed`, or `post.label` in `pending`, `failed` |
| `fix` | `decision.action == "fix"` and either the fix is open (`fix` absent, or `fix.pr_url` and `fix.abandoned` null), or it is finished but its worktree or branch was never cleaned up (not when git metadata was tampered with) |

## `run_state.py`

| Subcommand | Arguments | Effect |
|---|---|---|
| `root` | `--kind K --repo R` | Prints the state root (always the per-user `${XDG_STATE_HOME:-~/.local/state}/cc-review/<kind>-bulk/<owner>__<name>/`) |
| `find-unfinished` | `--kind K --repo R [<run-id> \| --latest]` | Lists unfinished run ids, newest first (same-second runs by numeric suffix), plus `unreadable` run directories; with an id, prints it or fails with `no unfinished <kind> run '<id>'; unfinished runs: <ids or none>` |
| `abandon` | `<run-dir>` | Sets status `abandoned` |
| `show` | `<run-dir>` | Prints `state.json` |

Python API (imported by `issue_bulk.py`): `root(kind, repository)`, `init(root, kind, repository, user, options, extra) -> run_dir`, `load(run_dir)`, `update(run_dir, fn)`, `set_item(run_dir, id, **fields)`, `set_status(run_dir, status)`, `find_unfinished(root, kind, unreadable=None)`, `atomic_write(path, text)`, `write_json(path, value)`, `locked(run_dir)`, `claim_session(run_dir, session)`.

## Prompt interface

`issue --bulk [--search Q] [--limit N] [--scan S] [--repo owner/name]` and `issue --resume [<run-id>]`. `commands/issue.md` dispatches to `commands/issue-bulk.md` when `--bulk` or `--resume` is present, before its single-item unattended dispatch.
