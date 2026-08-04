# Implementation Plan: PR Review Comments

**Branch**: `001-pr-review-comments` | **Date**: 2026-08-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-pr-review-comments/spec.md`

## Summary

Close the feedback loop by posting cc-review findings as inline PR review comments via the GitHub Review Submission API. When `--pr` is provided, findings go through an interactive local review (accept/reject/edit), then are posted as a single GitHub review with inline comments, a summary body (including "What Went Well"), source attribution, and a run-id marker for lifecycle management. Extends triage to recognize and manage cc-review's own threads.

## Technical Context

**Language/Version**: Bash (POSIX-compatible), Markdown, `jq`, `yq`

**Primary Dependencies**: `gh` CLI (GitHub API), `jq` (JSON processing), `yq` (YAML processing)

**Storage**: Local JSON state files (`.cc-review/.triage-state.json`), Markdown reports

**Testing**: Manual integration testing via `gh` API against real PRs

**Target Platform**: Any system with Bash, `gh`, `jq` installed

**Project Type**: CLI plugin (prompt-based, no compiled code)

**Performance Goals**: Single API call for review submission, paginated queries for re-run scanning

**Constraints**: GitHub API rate limits, review comments must reference lines within diff hunks

**Scale/Scope**: Typically 5-50 findings per review, 1-3 re-runs per PR

## Global Constraints

These constraints apply to every task and are inherited implicitly:

- All scripts MUST be POSIX-compatible Bash
- `gh` CLI is required and assumed authenticated with review permissions
- `jq` is required for all JSON processing
- `yq` is required for all YAML processing
- Finding schema (`finding.schema.json`) MUST NOT be modified on disk; transient fields are in-memory only
- Platform functions in `platform.sh` follow the existing `_github_*` naming convention for GitHub-specific functions

## Constitution Check

No constitution defined for this project (template only). No gate violations.

## Project Structure

### Documentation (this feature)

```text
specs/001-pr-review-comments/
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
│   │   ├── preamble.md          # Shared agent instructions (existing)
│   │   ├── correctness.md       # (existing)
│   │   ├── architecture.md      # (existing)
│   │   ├── security.md          # (existing)
│   │   ├── production.md        # (existing)
│   │   ├── test-quality.md      # (existing)
│   │   └── goal-alignment.md    # (existing, extended for "What Went Well")
│   ├── commands/
│   │   ├── review.md            # Main review command (MODIFIED: add Step 7.5)
│   │   └── triage.md            # Triage command (MODIFIED: recognize cc-review threads)
│   ├── schemas/
│   │   └── finding.schema.json  # Finding schema (unchanged, transient fields in-memory only)
│   ├── scripts/
│   │   ├── platform.sh          # Platform abstraction (MODIFIED: add _github_post_review)
│   │   ├── triage-state.sh      # Triage state management (existing)
│   │   ├── resolve-config.sh    # Config resolution (existing)
│   │   └── sanitize-gh-json.py  # JSON sanitizer (existing)
│   └── templates/
│       └── reviewer-voice.md    # NEW: Reviewer voice profile for prose plugin
├── config/
│   └── config-template.yml      # Config template (MODIFIED: add pr_posting section)
```

**Structure Decision**: No new directories needed. The feature integrates into existing command files (`review.md`, `triage.md`) and scripts (`platform.sh`). One new file: `review/core/templates/reviewer-voice.md` for the prose voice profile.
