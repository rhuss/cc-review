# Implementation Plan: Bulk Issue Assessment with Optional Draft-PR Fixes

**Branch**: `015-bulk-issue-assessment` | **Date**: 2026-11-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/014-bulk-issue-assessment/spec.md`

## Summary

Add `issue --bulk` to cc-review: select open issues by an optional search, skip already handled ones with deterministic rules and paging, assess each selected issue in a fresh worker context, walk the maintainer through one approval prompt per issue (post, edit or skip, plus fix or review choices), post approved comments immediately, then run chosen fixes one at a time in isolated worktrees and open draft pull requests. Everything except judgment and conversation lives in a new stdlib-only Python helper, `issue_bulk.py`, with a kind-agnostic run-state module, `run_state.py`, that the later bulk runner refactor (brainstorm #18) can adopt. The prompt side is a new `commands/issue-bulk.md`, reached from `commands/issue.md` when `--bulk` or `--resume` is present.

## Technical Context

**Language/Version**: Python 3.9+ (stdlib only, like `assess_issue.py`, `assessment.py`, `ci.py`); Markdown command prompts; Bash for the existing test runner.

**Primary Dependencies**: `gh` CLI (authenticated, GraphQL and REST), `git` (worktrees, push), `jq` for snapshot reads in prompts. Reuses `inbox.GitHub`, `inbox.run_collector` helpers, `assess_issue.collect`, `assessment.validate/repair/render/_safe`, and `ci.load_config` for label names.

**Storage**: JSON files. Run state under `<git toplevel>/.cc-review/issue-bulk/<run-id>/` (the state root gets its own `.gitignore` containing `*`), or `${XDG_STATE_HOME:-~/.local/state}/cc-review/issue-bulk/<owner>__<name>/<run-id>/` without a matching checkout.

**Testing**: `python3 -B tests/test_issue_bulk.py` (unittest, a fake `gh` on `PATH` as `tests/test_issue_assessment.py` does, real `git` against temporary repositories with a bare `origin`), wired into `tests/run.sh`; selection fixtures under `tests/fixtures/issue-bulk/`.

**Target Platform**: macOS and Linux shells used by Claude Code, Codex and OpenCode.

**Project Type**: CLI plugin (prompt commands plus helper scripts).

**Performance Goals**: Selection of 100 candidates in at most 5 GraphQL search requests (detail selected in the same request); a 10-issue batch needs no more GitHub calls than selection, one collection per issue, and one re-check plus post per approved issue.

**Constraints**: No project code, tests or hooks run locally for fixes. No model involvement in selection, state, posting, measuring or publishing (FR-030). Untrusted issue text never reaches a shell command. Fix workers have no network and no push authority (FR-022a). The maintainer's checkout stays unchanged (SC-006).

**Scale/Scope**: Batches of 1 to 100 issues (default 10), scan ceiling 1 to 1000 (default 100).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` is still the unfilled template, so there are no ratified gates. The project guidance in `CLAUDE.md` applies instead:

| Guidance | Status |
|---|---|
| Plugin structure: harness-agnostic logic in `review/core/`, shims only resolve core and forward arguments | Pass: logic in `core/commands/issue-bulk.md` and `core/scripts/`; shims only gain argument hints |
| SKILL.md shims under 50 lines, no review logic | Pass: `skills/issue/SKILL.md` changes only its argument hint, forwarded flags, core file check and closing sentence, staying under 50 lines |
| Bash/Python helpers, `jq`, `yq` | Pass: Python stdlib helpers, consistent with existing collectors |
| Existing single-issue behavior unchanged (FR-003) | Pass: bulk dispatch is a new early branch in `issue.md` |

Post-design re-check: unchanged, pass.

## Project Structure

### Documentation (this feature)

```text
specs/014-bulk-issue-assessment/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── issue-bulk-cli.md        # helper subcommands, inputs, outputs, exit codes
│   └── worker-files.md          # assessment and fix worker file contracts
└── tasks.md
```

### Source Code (repository root)

```text
review/core/scripts/
├── run_state.py          # NEW: kind-agnostic run state (init, find-unfinished, item get/set, record, status, abandon)
├── issue_bulk.py         # NEW: validate, select, start, collect, render-item, next, decide, post, fix-*, record-handoff, report
├── assess_issue.py       # reuse collect(); small refactor to expose a collect_issue(repository, number) function
└── assessment.py         # reuse validate/repair/render/_safe; render gains an optional run marker line

review/core/commands/
├── issue.md              # early dispatch: --bulk/--resume -> issue-bulk.md (before unattended dispatch)
└── issue-bulk.md         # NEW: orchestration prompt (workers, approval prompt, fix pass, handoff, report)

review/core/templates/
├── issue-fix-worker.md   # NEW: fix worker instructions (edit only inside worktree, write fix.json)
└── (existing need-and-fit.md, issue-assessment.md, maintainer-voice.md reused by assessment workers)

review/skills/issue/SKILL.md          # argument hint and forwarded flags
review/opencode/command/issue.md      # same for OpenCode
docs/ (guide pages are out of scope; README command table gains one row)

tests/
├── test_issue_bulk.py                # NEW: unit + CLI behavior tests with fake gh/git
├── fixtures/issue-bulk/              # NEW: search pages and candidate detail fixtures
└── run.sh                            # wire the new test file
```

**Structure Decision**: Follow the existing collector pattern (`assess_issue.py`, `ci.py`): one Python entry script with subcommands, stdlib only, fake `gh` in tests. Run state is a separate module so the PR bulk commands can adopt it later without depending on issue specifics.

## Design Overview

1. **Validate** (`issue_bulk.py validate`): full FR-002 table, before any service call; prints normalized options JSON.
2. **Unfinished-run check** (`run_state.py find-unfinished issue`): offer resume or start fresh (fresh abandons the old run).
3. **Select** (`issue_bulk.py select`): GraphQL search `repo:<r> is:issue is:open sort:created-desc <query>`, 20 per page, each page fetching per issue: author login and association, comments (author login, association, bot flag, body marker check), and timeline cross-references and connected events to pull requests (author association, state, merged, review and comment associations). Pure `classify(node, repository)` applies FR-005 to FR-009 and FR-011b; paging stops at limit, exhaustion or ceiling. Failure exits non-zero with no run (FR-011a). Output becomes the run's `selection.json`.
4. **Collect** (`issue_bulk.py collect <run> <n>`): `assess_issue.collect_issue` into `items/<n>/snapshot.json`; failure records `assessment_failed`.
5. **Assess** (prompt): one worker per issue reads its snapshot, project guidance (verified root), templates, and writes `items/<n>/assessment.json` (body, assessment, fix_estimate). `issue_bulk.py render-item` validates, renders, computes fix eligibility and stores `rendered.md`.
6. **Approve** (prompt + `decide`): one prompt per issue, full rendered text in the reply and in the option preview; edits rewrite `assessment.json` and re-render; `decide` records post/skip, fix/leave/review.
7. **Post** (`issue_bulk.py post <run> <n>`): re-check (fresh classify, open state), withhold or post comment with the run marker, then label; records comment and label separately; idempotent on resume by searching for the run marker.
8. **Fix pass**: `fix-prepare` creates worktree and branch from the fresh default branch tip and records a checkout snapshot; the fix worker (file tools only where the harness allows) edits only inside the worktree and writes `fix.json`; `fix-measure` verifies the snapshot, enforces the bound, and records the tree id; `fix-publish` commits without hooks, pushes, and opens the draft PR as separate recorded steps; `fix-cleanup` removes worktree and local branch. No project code runs locally (R-008).
9. **Handoff and report**: open non-maintainer PRs chosen for review are handed to `review --bulk --prs <list>`; `issue_bulk.py report` prints per-issue outcomes and coverage; the run is finished.

## Global Constraints

| Constraint | Value | Source |
|---|---|---|
| Python | 3.9+, stdlib only | plan |
| Batch limit | 1 to 100, default 10 | FR-002 |
| Scan ceiling | 1 to 1000, default 100, not below limit | FR-002 |
| Search page size | 20 | R-001 |
| Small bound | 3 non-test files, 100 non-test lines, 300 test lines | FR-013 |
| PR body summary | at most 1,500 characters, sanitized | R-009 |
| Branch name | `cc-review/fix-issue-<n>` | Assumptions |
| Local execution for fixes | none (no tests, builds, hooks) | FR-024, R-008 |

## Complexity Tracking

| Item | Why needed | Simpler alternative rejected because |
|---|---|---|
| New `run_state.py` instead of extending `bulk-state.sh` | FR-031 needs kind-agnostic state; `bulk-state.sh` is PR-shaped (heads, threads, pushes) | Extending it would entangle issue fields with PR resume logic and the 1,400-line `bulk.md` contract |
| Separate state root `.cc-review/issue-bulk/` | `bulk-state.sh find-unfinished` reads every run under `.cc-review/bulk/` and expects PR state | Sharing the root risks the PR resume path misreading issue runs |
