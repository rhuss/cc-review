# Brainstorm Overview

Last updated: 2026-08-14

## Sessions

| # | Date | Topic | Status | Spec | Issue |
|---|------|-------|--------|------|-------|
| 01 | 2026-08-03 | pr-review-comments | spec-created | 001 | - |
| 02 | 2026-08-04 | config-system | active | - | - |
| 03 | 2026-08-04 | reviewer-abstraction | active | - | - |
| 04 | 2026-08-14 | meta-reviewer | active | - | - |

## Open Threads
- Should --profile and --config be mutually exclusive? (from #02)
- Should init generate a GitHub Actions workflow file? (from #02)
- Should config support environment variable interpolation for CI secrets? (from #02)
- How should config errors be reported? (from #02)
- Should reviewer descriptors support multiple output formats? (from #03)
- Should there be a "test" subcommand for reviewer detection + auth? (from #03)
- How to handle tools that post directly to PR vs stdout? (from #03)
- Should the abstraction unify internal + external agent dispatch? (from #03)
- Should meta-review critics see which agent produced each finding, or anonymize? (from #04)
- What is the exact schema for meta-review verdict output? (from #04)
- Should quality scores influence future reviews (confidence multiplier)? (from #04)

## Parked Ideas
(none)
