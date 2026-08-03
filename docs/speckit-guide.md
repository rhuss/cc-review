# spec-kit Integration Guide

How cc-review integrates with [cc-spex](https://github.com/rhuss/cc-spex) and the spec-kit workflow.

## Overview

cc-spex includes a built-in `review-code` gate in the `spex-gates` extension. When cc-review is installed as a spec-kit extension, it replaces the built-in review with a more thorough multi-agent review that includes external tool integration, autonomous fix loops, and PR comment triage.

The delegation is transparent: cc-spex detects cc-review at runtime and delegates to it. If cc-review is not installed, cc-spex falls back to its built-in review behavior.

## Installation

### As a spec-kit extension

```bash
specify extension add /path/to/cc-review/adapters/speckit
```

Or symlink into the extensions directory:

```bash
ln -s /path/to/cc-review/adapters/speckit ~/.specify/extensions/cc-review
```

The extension registers two commands:
- `speckit.cc-review.review` (replaces the built-in `review-code` gate)
- `speckit.cc-review.triage` (adds PR comment triage to the ship pipeline)

### Core access

The spec-kit adapter resolves cc-review core by checking:
1. `.cc-review/core` in the project root
2. `~/.cc-review/core` in the home directory

Ensure the core is accessible at one of these paths. The simplest approach:

```bash
ln -s /path/to/cc-review/core ~/.cc-review/core
```

## How cc-spex Delegates to cc-review

### Review

During the ship pipeline, cc-spex runs the `review-code` gate. When cc-review is installed, this gate delegates to `speckit.cc-review.review`, which:

1. Checks that the pipeline is in `ship` mode (skips otherwise)
2. Resolves the active spec path via `scripts/check-prerequisites.sh`
3. Updates flow state to `current_step: review`, `review_status: in_progress`
4. Reads and executes `core/commands/review.md` with these arguments:
   - `--spec <resolved-spec-path>` (automatic, from the active spec)
   - `--hints .specify/memory/constitution.md` (if the constitution exists)
   - `--output .specify/reports/review-report.md`
   - Any user-provided flags
5. Updates flow state to `review_status: completed`

### Triage

After pushing a PR and receiving review comments, run:

```
/speckit.cc-review.triage
```

The triage command:

1. Checks ship mode
2. Resolves the active spec path
3. Passes the constitution as review hints (for assessing whether suggestions align with architectural principles)
4. Captures out-of-scope ideas to `brainstorm/idea-inbox.md`
5. Delegates to `core/commands/triage.md`

## Spec-Aware Review

When cc-review receives a `--spec` path, all 6 review agents gain spec awareness:

- **Correctness**: verifies implementation matches spec boundaries exactly (e.g., "retry on 502/503/504" means exactly those codes, not all 5xx)
- **Architecture**: checks for YAGNI violations against spec scope
- **Security**: validates that security-related requirements are implemented
- **Production Readiness**: confirms observability and metrics the spec requires are exposed
- **Test Quality**: cross-references tests against spec requirements (FR-NNN items) to identify gaps
- **Goal Alignment**: builds a goal delivery table from spec requirements, PR description, and linked issues; verifies each FR is DELIVERED, PARTIAL, or NOT DELIVERED

After the fix loop completes, if code was removed, a post-fix spec compliance check verifies that all functional requirements are still implemented. Dropped requirements generate Critical findings.

## Constitution as Review Hints

The spec-kit constitution (`.specify/memory/constitution.md`) contains project-level architectural principles and design decisions. When passed as `--hints`, these principles inform all review agents through the preamble's project review hints mechanism.

This means review agents can flag code that violates constitutional principles, not just generic best practices.

## Triage with Constitution Principles

When triage receives the constitution as hints, it uses the architectural principles to assess whether bot suggestions align with the project's design decisions. A bot suggestion that contradicts a constitutional principle is deprioritized; a suggestion that reinforces one gets higher confidence.

## Simplified Fallback

When cc-review is not installed, cc-spex's built-in `review-code` gate runs instead. The built-in review:

- Reads the spec and changed files
- Performs a single-pass review (no specialized agents)
- Does not integrate external tools
- Does not run an autonomous fix loop
- Produces a simpler pass/fail gate result

The built-in review is functional but less thorough. It exists so the ship pipeline works without cc-review as a dependency.

## Migration from Built-in Deep Review

If your project uses the `spex-deep-review` extension (the older multi-agent review built into cc-spex), migrating to cc-review:

1. Install cc-review as described above
2. The `speckit.cc-review.review` command takes precedence over `spex-deep-review` when both are installed
3. cc-review uses the same 6 agent roles but with updated prompts, external tool integration, and triage support
4. Review hints replace the older review context mechanism; move any project-specific patterns from your deep-review config to `.cc-review/review-hints.md`
5. The output format is compatible: both produce a findings report with severity levels and a gate outcome

Key differences from `spex-deep-review`:

| Capability | spex-deep-review | cc-review |
|------------|-----------------|-----------|
| Agent count | 5 | 6 (adds Goal Alignment) |
| External tools | None | CodeRabbit, Copilot, Codex |
| PR comment triage | Separate `triage` command in spex-collab | Integrated `/triage` command |
| Fix loop | Built-in | Built-in with post-fix spec compliance check |
| Harness support | cc-spex only | Claude Code, spec-kit, Codex, OpenCode |
| Configuration | In-memory | `.cc-review/config.yml` with project/user levels |
| Review hints | None | `.cc-review/review-hints.md` |
| Triage state | None | Persistent `.cc-review/.triage-state.json` |
