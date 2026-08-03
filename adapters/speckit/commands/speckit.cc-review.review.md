---
name: speckit.cc-review.review
description: Enhanced multi-agent code review via cc-review
---

# cc-review: Review (spec-kit integration)

## Ship Pipeline Guard

Read `.specify/.spex-state`. If `mode` is not `ship`, skip this command:
"Review runs during ship pipeline only. Current mode: {mode}"

## Spec Resolution

Run `scripts/check-prerequisites.sh` to resolve the active spec path.
If no spec is found, warn but continue without `--spec`.

## Flow State

Update `.specify/.spex-state` flow tracking:
- Set `current_step: review`
- Set `review_status: in_progress`

## Core Resolution

Find cc-review core by checking in order:
1. `.cc-review/core` (project-local)
2. `~/.cc-review/core` (user-global)

If not found: "cc-review core not found. Install with: cc-review install"

## Execution

Read and execute `core/commands/review.md` from resolved core, passing:
- `--spec <resolved-spec-path>` (if found)
- `--hints .specify/memory/constitution.md` (if exists)
- `--output .specify/reports/review-report.md`
- All user-provided arguments

After completion, update `.specify/.spex-state`:
- Set `review_status: completed`
