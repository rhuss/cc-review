# Brainstorm: Bulk Runner Scripts

**Date:** 2026-11-23
**Status:** idea

## Problem Framing

`review/core/commands/bulk.md` is about 1,370 lines and still contains 49 inline shell blocks that the model must reproduce correctly on every run. A good part of the mechanics already lives in scripts (`bulk-select.sh`, `bulk-state.sh`, `bulk-apply.sh`, `pr-worktree.sh`, about 2,300 lines), but bookkeeping still runs through the prompt:

- flag parsing and validation (a shell `case` block in the prompt)
- the unfinished-run check and resume decisions
- the per-PR loop: next item, skip conditions, what to record
- `jq` queries over run state that build decision tables and counts

These are deterministic steps. Leaving them to the model costs context and creates room for drift between runs.

The idea is a bulk runner script that owns arguments, selection, state, loop control and report counts, and calls the model for one item at a time only where judgment is needed (analysis, drafting, fixing, questions to the user).

This came up while brainstorming [#17: Bulk Issue Assessment](17-bulk-issue-assessment.md). Issue bulk is built script-first, with shared pieces that do not assume PRs, so it can serve as the template for this runner.

## Approaches Considered

Not yet explored.

## Decision

Not yet decided. Recorded as a follow-up to #17; the review and triage migration is a refactor of working code with regression risk and should be its own brainstorm and spec once issue bulk has proven the shape.

## Key Requirements

- No behavior change for `review --bulk` and `triage --bulk` (selection, decisions, posting, resume).
- Item-kind agnostic runner: PR review, PR triage and issue assessment as kinds.
- Judgment stays with the model; bookkeeping moves to scripts.

## Open Questions

- Which inline blocks move first, and how is parity with current behavior tested?
- One runner with item kinds, or shared libraries used by per-kind scripts?
- How do existing run directories and resume ids migrate?
- How much of the prompt shrinks, and what remains as the contract between runner and model?
