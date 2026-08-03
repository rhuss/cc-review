---
name: speckit.cc-review.triage
description: PR comment triage via cc-review with spec-aware assessment
---

# cc-review: Triage (spec-kit integration)

## Ship Pipeline Guard

Read `.specify/.spex-state`. If `mode` is not `ship`, skip this command:
"Triage runs during ship pipeline only. Current mode: {mode}"

## Spec Resolution

Run `scripts/check-prerequisites.sh` to resolve the active spec path.
If no spec is found, warn but continue without `--spec`.

## Constitution Context

If `.specify/memory/constitution.md` exists, read it and pass its
architectural principles as review context via `--hints`.

## Core Resolution

Find cc-review core by checking in order:
1. `.cc-review/core` (project-local)
2. `~/.cc-review/core` (user-global)

If not found: "cc-review core not found. Install with: cc-review install"

## Execution

Read and execute `core/commands/triage.md` from resolved core, passing:
- `--spec <resolved-spec-path>` (if found)
- `--idea-inbox brainstorm/idea-inbox.md`
- All user-provided arguments
