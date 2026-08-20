# Implementation Plan: Meta-Review Quality Gate

**Branch**: `003-meta-review` | **Date**: 2026-08-14 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-meta-review/spec.md`

## Summary

Add a meta-review quality gate (Step 4b) to the cc-review pipeline between merge/dedup and gate check. Two critic subagents (Skeptic and Calibrator) evaluate findings in parallel with fresh contexts, filtering false positives, calibrating severity, detecting contradictions, and scoring agent performance. Config-gated with `meta_review.enabled` and `meta_review.min_findings` threshold.

## Technical Context

**Language/Version**: Bash (POSIX-compatible), Markdown, `jq`, `yq`

**Primary Dependencies**: Agent tool (harness-provided), `jq` for JSON processing

**Storage**: N/A (findings are in-memory during the review pipeline)

**Testing**: Manual validation via review runs; no automated test framework for markdown command definitions

**Target Platform**: Claude Code, OpenCode, Codex (multi-harness plugin)

**Project Type**: Plugin (markdown-based command definitions + agent prompts + JSON schemas + shell scripts)

**Performance Goals**: Meta-review step completes within the time of the slowest review agent (parallel execution)

**Constraints**: No new runtime dependencies; must work within existing config resolution chain

**Scale/Scope**: 2 new agent prompt files, 1 modified command file, 1 extended schema, 1 modified config template

## Constitution Check

No project constitution defined. Proceeding with standard project conventions from CLAUDE.md.

## Project Structure

### Documentation (this feature)

```text
specs/003-meta-review/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output (created by /speckit-tasks)
```

### Source Code (repository root)

```text
review/
├── core/
│   ├── agents/
│   │   ├── meta-skeptic.md      # NEW: Skeptic agent prompt
│   │   ├── meta-calibrator.md   # NEW: Calibrator agent prompt
│   │   ├── preamble.md          # EXISTING (unchanged)
│   │   ├── correctness.md       # EXISTING (unchanged)
│   │   └── ...                  # Other existing agents
│   ├── commands/
│   │   └── review.md            # MODIFIED: Add Step 4b, update Steps 7/8
│   └── schemas/
│       └── finding.schema.json  # MODIFIED: Add verdict/calibration fields
├── config/
│   └── config-template.yml      # MODIFIED: Add meta_review section
```

**Structure Decision**: All changes are within the existing `review/core/` directory structure. Two new agent prompt files, three modified existing files. No new directories needed.

## Global Constraints

These project-wide requirements from the spec apply to every task:

- **Shell**: POSIX-compatible Bash (no bashisms unless guarded)
- **Harnesses**: Must work in Claude Code, OpenCode, and Codex (Agent tool availability assumed)
- **Dependencies**: No new runtime dependencies; `jq` and `yq` are the only required CLI tools
- **Schema**: `additionalProperties: false` in finding schema; all new fields must be optional
- **Config**: New keys must integrate with the existing resolution chain (CLI > project > user > defaults)
