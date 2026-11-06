# Implementation Plan: Streamlined Inbox Report with Guided Tour and Fan-Out

**Branch**: `012-inbox-tour-orchestration` | **Date**: 2026-11-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/012-inbox-tour-orchestration/spec.md`

## Summary

Rework the `inbox` command so its report is scannable (a table for the "Needs your attention" group, a detailed assessment section below it, brief lists for the other two groups) and add two opt-in layers behind an end-of-report prompt: a guided tour that walks up to five attention items one at a time, and a fan-out that delegates acting on an item to the existing `review`, `triage`, and `issue` commands, batching several pull requests into `bulk`. The report and tour stay read-only; `inbox` orchestrates by invoking the real commands and never reimplements their logic.

The work is almost entirely prompt-and-shell changes in the harness-agnostic core: `review/core/commands/inbox.md` (report format, end-of-report prompt, tour loop, fan-out delegation, snapshot lifecycle) plus one genuinely new capability in the bulk selection path so `bulk` can run on an explicit pull-request list.

## Technical Context

**Language/Version**: Bash (POSIX-compatible), Markdown prompt files, `jq`, `yq`, Python 3.9+ (the existing read-only collector `inbox.py` only; no new Python required).

**Primary Dependencies**: `gh` CLI (GitHub), the existing cc-review core commands (`review.md`, `triage.md`, `issue.md`, `bulk.md`) and scripts (`inbox.py`, `bulk-select.sh`, `pr_actions.py`).

**Storage**: The existing one-shot read-only snapshot (`$INBOX_TMP/snapshot.json`) in a private temp dir outside the project. No new persistent storage.

**Testing**: Shell-level tests following the existing pattern in `tests/` (e.g., `tests/test_inbox.py` drives the collector and output expectations). Prompt-flow behavior is validated through the quickstart scenarios.

**Target Platform**: The three harnesses cc-review already supports via its manifests: Claude Code, Codex, OpenCode.

**Project Type**: CLI / agent-command plugin (prompt-driven commands plus shell utilities).

**Performance Goals**: No new network cost in the default path (one collection, as today). Fan-out cost is whatever the delegated command costs, incurred only on explicit user choice.

**Constraints**: Default run stays read-only (no post/push/resolve/agent-launch/working-tree change). The tour reads only the already-collected snapshot (no re-collection, FR-011). Fan-out requires a local checkout (FR-016).

**Scale/Scope**: Per-type item limit stays as today (default 10, max 100). Tour batches are capped at five items (FR-008).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The project constitution (`.specify/memory/constitution.md`) is an unfilled template with no ratified principles, so there are no constitutional gates to evaluate. The feature nonetheless respects the repository's stated development guidelines (CLAUDE.md): harness-agnostic core with thin shims, `jq`/`yq` for structured data, and the SKILL.md contract (shims stay under 50 lines and add no logic). No violations. No complexity-tracking entries required.

## Project Structure

### Documentation (this feature)

```text
specs/012-inbox-tour-orchestration/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── inbox-report.md      # Report structure (table + detail + brief lists)
│   ├── tour-and-fanout.md   # End-of-report prompt, tour loop, per-item fan-out
│   └── bulk-explicit-list.md# New --prs selector threaded review/triage -> bulk -> bulk-select.sh
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
review/core/
├── commands/
│   ├── inbox.md         # CHANGED: Section 4 (report format), new end-of-report prompt,
│   │                    #          tour section, fan-out section, Section 5 cleanup moved
│   │                    #          past the tour.
│   ├── review.md        # CHANGED: accept and forward an explicit PR list into bulk handoff.
│   ├── triage.md        # CHANGED: same explicit-list forwarding into bulk handoff.
│   └── bulk.md          # CHANGED: accept the explicit PR list as a selector kind.
├── scripts/
│   ├── inbox.py         # UNCHANGED (collector stays read-only; snapshot shape reused).
│   └── bulk-select.sh   # CHANGED: new explicit-list mode feeding the existing assessor.
review/skills/inbox/SKILL.md   # Possibly CHANGED: argument-hint only; no new logic (stays a shim).
tests/
└── test_inbox*          # NEW/CHANGED: report-structure and explicit-list selection tests.
```

## Approach by component

### 1. Streamlined report (US1, FR-001..006)

Rewrite `inbox.md` Section 4 ("Present the Overview"). "Needs your attention" becomes a Markdown table with the five columns in FR-001 (item+link, what, why you, certainty, next step), ordered as today (explicit before uncertain, then recency). Below it, a detailed section with one short block per attention item: situation, a labeled "my take" recommendation (may be "no response needed"), and evidence link. "Waiting on others" and "No current action" become two-column lists. The scope line and coverage account are kept but compressed. The read-only boundary language in Section 5 and Boundaries is unchanged for the report itself.

### 2. End-of-report prompt + guided tour (US2, FR-007..011)

Add a new section after report rendering. When attention items exist and the harness is interactive, present an end-of-report prompt offering the tour; declining ends the command with the read-only report intact. On accept, offer the default top-five (or let the user type specific item numbers, max five). Walk the selection one item at a time. On harnesses that support subagents, each item is presented by a per-item subagent that reads only that item's slice of `snapshot.json` (clean context); otherwise present inline in sequence (FR-019 degradation). After a batch, offer the next five unvisited attention items (FR-010) or a re-run.

### 3. Fan-out delegation (US3, FR-012..018)

Within the tour, each item offers "work on it now." The inbox flow invokes the matching command and, when it returns, continues the tour loop (the call/return model, see research). Single PR -> `review --pr N` or `triage --pr N`; issue -> `issue` for that issue; Discussion -> textual suggestion only. Several PRs -> offer a batch: invoke `review --bulk --prs <list>` and/or `triage --bulk --prs <list>`. Fan-out is offered only inside a local checkout of the target repo (FR-016); otherwise the report states acting is unavailable. Where a harness cannot chain command invocations in one session, inbox prints the exact command(s) as a text handoff (FR-019).

### 4. Bulk explicit pull-request list (FR-017, FR-018)

`bulk-select.sh` gains an explicit-list mode (a `--prs <n,...>` selector) that resolves those exact PRs through the existing shared assessor (`pr_actions.py select`), returning the same `{selected, excluded}` shape with bulk's own eligibility and exclusions. `review.md`/`triage.md` accept the list in their bulk handoff and pass it to `bulk.md`, which records it as the run's selector kind `explicit`. `inbox` passes the list unfiltered; `bulk` surfaces any PR it excludes (FR-018). `--prs` remains incompatible with `--all-open`/`--search`/`--pr`, mirroring the existing selector validation.

## Planning-input resolutions

- **Call/return and tour resume (central risk).** `inbox` does not hold a delegated command's context: it invokes the command and resumes its own tour loop afterward. `review` and `bulk` run with their own fresh context, worktrees, and subagents, exactly as when invoked directly; nothing about them needs to change for resume to work. The only harness-dependent part is in-session chaining of command invocations; where that is unavailable, the text-handoff fallback (FR-019) preserves the value. This keeps the orchestration thin and within each harness's existing capabilities.
- **Snapshot lifecycle.** Move the `$INBOX_TMP` cleanup from Section 5 (immediately after the report) to the true end of the command: after the user declines the tour, or after the tour/fan-out completes. The snapshot stays readable for the tour and per-item subagents; a delegated command's own data collection is separate and does not touch the snapshot. Cleanup still removes only the private temp dir and leaves the project untouched.

## Phase 0: Outline & Research

See [research.md](research.md). All unknowns from the spec's "Planning inputs" and the review findings are resolved there: the delegation/call-return model, the bulk explicit-list entry point, snapshot lifecycle, cross-harness degradation, report structure, and the recommendation-labeling boundary. No `NEEDS CLARIFICATION` remain.

## Phase 1: Design & Contracts

See [data-model.md](data-model.md) for the entities (attention item, tour selection, fan-out action, and the reused snapshot shape), [contracts/](contracts/) for the report, tour/fan-out, and bulk `--prs` contracts, and [quickstart.md](quickstart.md) for the end-to-end validation scenarios mapped to the success criteria.

Post-design constitution re-check: still no constitutional gates; design stays within the harness-agnostic-core and thin-shim guidelines. No violations.
