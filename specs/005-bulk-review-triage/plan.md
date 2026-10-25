# Implementation Plan: Bulk Review and Bulk Triage

**Branch**: `005-bulk-review-triage` | **Date**: 2026-10-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/005-bulk-review-triage/spec.md`

## Summary

Add `--bulk` (with `--all-open`, `--search`, `--limit`, `--unattended`, `--resume`) to the `review` and `triage` commands. A new orchestrator, `core/commands/bulk.md`, does the following:
- selects PRs through a new `bulk-select.sh`
- records a resumable run in `.cc-review/bulk/<run-id>/` through `bulk-state.sh`
- checks each PR out in a detached git worktree (`pr-worktree.sh`)
- runs the existing per-PR pipeline in a file-backed worker mode, so every subagent writes results to the PR's run directory and returns one status line (research R-001)

After analysis, the coordinator presents one decision table (deferred mode), or applies the fixed policy (unattended mode). It then applies actions with a head check before every push or post. Triage apply and the no-findings marker are deterministic scripts (`bulk-apply.sh`).

`review.md` gains a `REVIEW_ROOT` concept (research R-002). That fixes reviewing a PR that is not checked out, in single-PR mode too. Posted reviews now carry `commit_id`, so "reviewed at head" is exact (R-004). `triage.md` gains a prepare mode that records post, resolve and push actions instead of performing them (R-007).

## Technical Context

**Language/Version**: Bash (scripts run under bash, `set -euo pipefail` for the new executed CLIs, matching `triage-state.sh`), Markdown command definitions, `jq`, `yq` v4, `git` ≥ 2.30 (worktree `--detach`), `gh` CLI

**Primary Dependencies**: harness subagent dispatch (existing), `gh`, `git`, `jq`. No new dependencies.

**Storage**: Files under `.cc-review/bulk/` in the invoking repository ([data-model.md](data-model.md))

**Testing**: `tests/run.sh` (plain bash, `run_test`, explicit list in `main()`), run with `make test`. Script behavior is tested with temp git repos and a fake `gh` on `PATH`. The command Markdown is covered by contract greps and block extraction (existing pattern). LLM-driven flows are validated manually via [quickstart.md](quickstart.md).

**Target Platform**: Claude Code, Codex, OpenCode on macOS and Linux

**Project Type**: Multi-harness plugin (Markdown commands + shell scripts)

**Performance Goals**: Selection plus state setup completes in under 10 s for 50 open PRs (two `gh pr list` calls or one GraphQL search). Coordinator context per PR stays at roughly 10 status lines.

**Constraints**:
- Shims stay under 50 lines and add no logic.
- Single-PR behavior is unchanged except for `REVIEW_ROOT` when `--pr` is not the current branch, plus `commit_id` on posted reviews (FR-035, FR-036).
- No force-push, ever.
- No harness-specific tool names in reviewer bodies.

**Scale/Scope**:
- 4 new scripts and 1 new command file.
- Modifications to `review.md`, `triage.md`, `platform.sh`, `discover-reviewers.sh`, `reviewer.schema.json`, 4 shims, docs, README.
- About 30 new tests.

## Constitution Check

No project constitution is defined (the template is unfilled). Checked against `CLAUDE.md` conventions instead:

| Convention | Status |
|---|---|
| Bash (POSIX-compatible), Markdown, `jq`, `yq` | ✅ only these |
| Shims resolve core, pass all args, < 50 lines, no review logic | ✅ shims only add flag lines |
| Core stays harness-agnostic | ✅ worker protocol uses generic "dispatch a subagent" wording |

Post-design re-check: ✅ no violations, so the Complexity Tracking table is empty.

## Project Structure

### Documentation (this feature)

```text
specs/005-bulk-review-triage/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── cli-flags.md          # flags, validation errors, reserved names
│   ├── scripts.md            # bulk-state / bulk-select / pr-worktree / bulk-apply CLIs
│   └── worker-protocol.md    # file-backed subagent protocol, per-phase workers
└── tasks.md                  # created by /speckit-tasks
```

### Source Code (repository root)

```text
review/
├── core/
│   ├── commands/
│   │   ├── bulk.md                 # NEW: orchestrator (selection, unfinished-run check, analysis loop,
│   │   │                           #      decision table, apply, summary, resume)
│   │   ├── review.md               # MODIFIED: bulk entry + arg validation; REVIEW_ROOT (Steps 1-3, 6);
│   │   │                           #      worker-mode sections (Step 3 output-to-file, 4/4b/7 workers);
│   │   │                           #      commit_id in 7.5k; FR-035 isolated checkout
│   │   └── triage.md               # MODIFIED: bulk entry; TRIAGE_MODE=prepare overlay; TRIAGE_ROOT;
│   │                               #      TRIAGE_STATE_FILE; mandatory-step exceptions
│   ├── scripts/
│   │   ├── bulk-state.sh           # NEW
│   │   ├── bulk-select.sh          # NEW
│   │   ├── pr-worktree.sh          # NEW
│   │   ├── bulk-apply.sh           # NEW
│   │   ├── platform.sh             # MODIFIED: fetch_reviews returns commit.oid, author.login
│   │   └── discover-reviewers.sh   # MODIFIED: reserved names
│   └── schemas/
│       └── reviewer.schema.json    # MODIFIED: reserved names
├── skills/review/SKILL.md          # MODIFIED: new flags
├── skills/triage/SKILL.md          # MODIFIED: new flags
└── opencode/command/{review,triage}.md  # MODIFIED: new flags
docs/standalone-guide.md            # MODIFIED: bulk section
README.md                           # MODIFIED: bulk usage
tests/
├── run.sh                          # MODIFIED: new tests
└── fixtures/bulk/                  # NEW: gh fixture JSON + fake gh script
```

**Structure Decision**: The single plugin layout stays. The orchestrator is a separate command file (`bulk.md`) that `review.md` and `triage.md` hand off to when `--bulk` or `--resume` is present. This keeps the bulk loop out of the two already-long command files, which only gain worker-mode overlays.

## Design Overview

### Flow (bulk.md)

1. **Validate flags** ([cli-flags.md](contracts/cli-flags.md)). Resolve config once in the invoking repo (FR-011). `interactive: false` maps to unattended.
2. **Unfinished-run check** (`bulk-state.sh find-unfinished`). With `--resume`, load the run, `validate` it, and compute `resume-plan` against current heads. Without `--resume`: if an unfinished run exists, deferred mode asks resume/abandon/cancel and unattended mode errors (FR-031).
3. **Select** (`bulk-select.sh`). If nothing is selected, report it and stop with no state dir. Otherwise `init` + `set-prs`.
4. **Analyze**, sequentially (FR-016). For each pending PR:
   - `pr-worktree.sh add`, then mark the PR `analyzing`.
   - Run the review worker pipeline or the triage worker ([worker-protocol.md](contracts/worker-protocol.md)).
   - Mark it `analyzed`/`failed` with counts and the closed-PR check.
   - Remove or keep the worktree (FR-012).
   - On rate limit, mark the run `paused` and stop.
5. **Decide**:
   - Deferred: print the table and run the decision step (research R-009).
   - Unattended: policy (FR-023, FR-024). Record decisions.
6. **Apply**, sequentially:
   - Check that the head equals `expected_head`.
   - Run the decision's workers and scripts, recording sub-action ids.
   - Set the terminal status and remove the worktree when done.
7. **Summarize**: `bulk-state.sh summary`, print it, set the run to `finished` when all PRs are terminal.

### review.md changes

- **Prerequisites**: if `--bulk` or `--resume` is set, validate the review-specific bulk flags and execute `commands/bulk.md` instead of the single-PR steps.
- **Step 1**: set `REVIEW_ROOT`.
  - When `--pr` is given and `pr-worktree.sh is-pr-branch` fails, create a worktree under `.cc-review/pr-worktrees/pr-<n>` (detached, at the PR head) and set `REVIEW_ROOT` to it. Remove it at command end.
  - Otherwise `REVIEW_ROOT=$(git rev-parse --show-toplevel)`.
  - Changed files come from `git -C "$REVIEW_ROOT"` or `gh pr diff` as today.
- **Step 2**: test detection and command reviewers use `REVIEW_ROOT`. Discovery keeps `--project-dir "$PROJECT_DIR"` (the invoking repo).
- **Step 3**: Review Target lists absolute paths under `REVIEW_ROOT`. New subsection "Worker Mode Output" (used by bulk.md), see the worker protocol.
- **Steps 4, 4b, 7**: new subsection "Worker Mode" describing the merge, meta and report workers (by reference to the existing step text).
- **Step 6**: in isolated mode, the fix menu is shown only when the user authors the PR. Fixes are committed and pushed with `pr-worktree.sh push`.
- **Step 7.5k**: add `"commit_id": "<reviewed head sha>"` to the payload. Use the marker variant `cc-review:run-id:<RUN_ID>` (bulk passes `<run-id>/pr-<n>`).

### triage.md changes

- **Prerequisites**: hand off to `bulk.md` for `--bulk`/`--resume`. Validate triage-specific bulk flags.
- New section "Prepare Mode (`TRIAGE_MODE=prepare`)":
  - lists the steps skipped or turned into plan entries (research R-007)
  - all file paths are absolute under `TRIAGE_ROOT`
  - `TRIAGE_STATE_FILE` is exported for every `triage-state.sh` call
- The "MUST execute" notes on Steps 3d, 12b, 12c and 13 gain "(in prepare mode, see Prepare Mode)".

## Risks

| Risk | Mitigation |
|---|---|
| Subagent ignores "write to file" and returns findings inline | Worker prompt ends with an explicit return contract; the coordinator verifies the file exists and parses with `jq`. Otherwise it marks the reviewer failed for that PR. |
| `gh pr list --json reviews` truncates long review lists | Fall back to `fetch_reviews` (paginated) for PRs whose `reviews` length hits the page size |
| Detached worktree leaks on crash | `resume-plan` re-validates worktrees; summary lists kept ones; `pr-worktree.sh remove` is idempotent |
| GitHub rejects `commit_id` for an outdated head | Only possible after the head moved, which the head check catches first. On a 422, mark the PR stale. |

## Complexity Tracking

No violations.
