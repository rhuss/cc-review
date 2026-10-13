# Brainstorm Overview

Last updated: 2026-10-13

## Sessions

| # | Date | Topic | Status | Spec | Issue |
|---|------|-------|--------|------|-------|
| 01 | 2026-08-03 | pr-review-comments | spec-created | 001 | - |
| 02 | 2026-08-04 | config-system | active | - | - |
| 03 | 2026-08-04 | reviewer-abstraction | superseded (by #05) | - | - |
| 04 | 2026-08-14 | meta-reviewer | active | - | - |
| 05 | 2026-10-13 | reviewer-plugins | active | - | - |

## Open Threads
- Should --profile and --config be mutually exclusive? (from #02)
- Should init generate a GitHub Actions workflow file? (from #02)
- Should config support environment variable interpolation for CI secrets? (from #02)
- How should config errors be reported? (from #02)
- Should meta-review critics see which agent produced each finding, or anonymize? (from #04)
- What is the exact schema for meta-review verdict output? (from #04)
- Should quality scores influence future reviews (confidence multiplier)? (from #04)
- Exact frontmatter schema and validation for reviewer plugins? (from #05)
- How does `kind: command` express output parsing without a script? (from #05)
- Do the meta-review agents also become plugins, or stay core? (from #05)
- Config migration: deprecated aliases for `agents.*` / `external_tools.*` or clean break? (from #05)
- Should a plugin be able to opt its findings out of the fix loop? (from #05)
- Should triage auto-discover bot profiles from `kind: command` reviewer metadata? (from #05)

## Parked Ideas
- Remote reviewer plugin sources (git URLs in config, community catalog) (#05)
  Reason: out of scope for the first plugin mechanism; revisit once the local three-layer discovery exists
