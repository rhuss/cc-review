# Vendored SDD helper scripts

These three scripts are copied verbatim (plus a one-line provenance header) from
superpowers `skills/subagent-driven-development/scripts/`:

| Script | Role |
|---|---|
| `sdd-workspace` | Resolve and ensure the per-plan workspace directory; prints its absolute path |
| `task-brief` | Extract one task's text from a plan into a file (`task-brief PLAN_FILE N [OUTFILE]`) |
| `review-package` | Build a review diff package (`review-package PLAN_FILE BASE HEAD [OUTFILE]`) |

cc-guide vendors them so `create` and `evolve` never read or execute files inside
another plugin's install directory (FR-006): capability detection no longer resolves
a superpowers install path. The scaffold copies this directory into each guide
project as `tools/guide/sdd/`, so the scripts travel with the project for CI too.

## Refreshing

They are plain bash doing git and file plumbing, with no harness-specific logic.
When superpowers changes them, re-copy from the superpowers version recorded in the
provenance header of each script and bump that header. Keep the executable bit.
`guide/compat.yaml` records the superpowers version cc-guide was validated against.
