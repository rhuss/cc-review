# Implementation Plan: Pluggable Reviewers

**Branch**: `004-reviewer-plugins` | **Date**: 2026-10-13 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/004-reviewer-plugins/spec.md`

## Summary

Replace the hard-coded reviewer lists in `review/core/commands/review.md` with a discovery-driven model. A reviewer is a markdown file with YAML frontmatter (metadata) and a body (prompt, or parsing notes for command reviewers), optionally in a directory form with supporting files. A new shell script discovers reviewers from three layers (project, user, bundled), validates frontmatter, resolves overrides, and emits a JSON list. The review command iterates that list to dispatch prompt reviewers as fresh-context subagents and command reviewers as bounded shell invocations, then merges findings through the existing dedup, meta-review, fix loop, and report stages. The six built-in agents and three external CLI tools migrate to the new format; config moves from `agents.*` / `external_tools.*` to `reviewers.<name>` with legacy aliases; CLI flags are derived from discovered names. A `gator` prompt reviewer ported from NVIDIA/OpenShell ships disabled by default as the first contributed plugin.

## Technical Context

**Language/Version**: Bash (POSIX-compatible with guarded bashisms, matching existing scripts), Markdown command definitions, `jq`, `yq` (v4, used for YAML and frontmatter extraction)

**Primary Dependencies**: Agent tool (harness-provided subagent dispatch), `jq`, `yq`. No new runtime dependencies.

**Storage**: Filesystem only. Reviewer files in three directories; merged config in a temp file (existing mechanism).

**Testing**: New `tests/run.sh` bash test runner (plain assertions, no framework) covering the discovery script and config legacy mapping, wired to a `make test` target. Prompt-dispatch behavior is validated manually via `quickstart.md` scenarios, as for prior features.

**Target Platform**: Claude Code, Codex, OpenCode (multi-harness plugin). macOS and Linux shells.

**Project Type**: Plugin (markdown command definitions + reviewer prompt files + JSON schemas + shell scripts)

**Performance Goals**: Discovery adds under one second to review startup for up to 30 reviewers (one `yq` call per file). Dispatch parallelism unchanged.

**Constraints**: Harness-agnostic plugin bodies (no tool names). Existing finding pipeline (dedup, meta-review, fix loop, report, PR posting) unchanged except where the spec generalizes by-name behavior. Backward compatible config for at least one release. Shims stay under 50 lines.

**Scale/Scope**: 1 new script, 1 new schema, 1 new test runner, 10 reviewer files (6 migrated prompt, 3 new command, 1 gator directory), modifications to `review.md`, `init.md`, `resolve-config.sh`, `detect-tools.sh`, `finding.schema.json`, config template and 3 profiles, 2 harness shims, README and docs.

## Constitution Check

No project constitution defined (template is unfilled). Proceeding with the conventions in `CLAUDE.md`: Bash + Markdown + `jq` + `yq`, shims resolve core and add no review logic, shims under 50 lines.

## Project Structure

### Documentation (this feature)

```text
specs/004-reviewer-plugins/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── reviewer-frontmatter.md   # Plugin metadata contract
│   ├── discovery-output.md       # JSON emitted by discover-reviewers.sh
│   └── cli-and-config.md         # Derived flags, config keys, legacy mapping
├── upstream/            # Verbatim OpenShell source files for the gator port (Apache-2.0)
│   ├── NOTICE.md
│   ├── principal-engineer-reviewer.md
│   └── review-findings-schema.md
└── tasks.md             # Phase 2 output (created by /speckit-tasks)
```

### Source Code (repository root)

```text
review/
├── core/
│   ├── reviewers/                      # NEW: bundled reviewer plugins (discovery layer "bundled")
│   │   ├── correctness.md              # MOVED from agents/, frontmatter added
│   │   ├── architecture.md             # MOVED from agents/, frontmatter added
│   │   ├── security.md                 # MOVED from agents/, frontmatter added
│   │   ├── production.md               # MOVED from agents/, frontmatter added
│   │   ├── test-quality.md             # MOVED from agents/, frontmatter added
│   │   ├── goal-alignment.md           # MOVED from agents/, frontmatter added (requires, context, dedup)
│   │   ├── coderabbit.md               # NEW: kind: command
│   │   ├── copilot.md                  # NEW: kind: command
│   │   ├── codex.md                    # NEW: kind: command
│   │   └── gator/
│   │       ├── reviewer.md             # NEW: ported prompt reviewer, enabled: false
│   │       └── references/
│   │           └── findings-contract.md  # NEW: evidence contract, listed in `references`
│   ├── agents/
│   │   ├── preamble.md                 # EXISTING (unchanged): prepended to every prompt reviewer
│   │   ├── meta-skeptic.md             # EXISTING (unchanged)
│   │   └── meta-calibrator.md          # EXISTING (unchanged)
│   ├── commands/
│   │   ├── review.md                   # MODIFIED: discovery-driven Prerequisites, Steps 2, 3, 4, 6, 7, 7.5j, 8
│   │   └── init.md                     # MODIFIED: list discovered reviewers, emit reviewers.* keys
│   ├── schemas/
│   │   ├── finding.schema.json         # MODIFIED: category becomes an open identifier
│   │   └── reviewer.schema.json        # NEW: frontmatter contract (documentation + jq-checked rules)
│   └── scripts/
│       ├── discover-reviewers.sh       # NEW: three-layer discovery, validation, override, JSON output
│       ├── resolve-config.sh           # MODIFIED: hyphenated keys, legacy alias mapping, reviewers.* validation
│       └── detect-tools.sh             # MODIFIED: detection driven by command reviewer metadata
├── config/
│   ├── config-template.yml             # MODIFIED: reviewers: section replaces agents/external_tools
│   └── profiles/{ci,quick,thorough}.yml  # MODIFIED: reviewers: keys
├── skills/review/SKILL.md              # MODIFIED: argument-hint (shim shared by Claude Code and Codex)
└── opencode/command/review.md          # MODIFIED: argument list

tests/
├── run.sh                              # NEW: bash tests for discovery and legacy config mapping
└── fixtures/reviewers/                 # NEW: fixture layers mirroring real flag semantics
    ├── bundled/reviewers/              #   passed as --core-dir tests/fixtures/reviewers/bundled
    ├── user/                           #   passed as --user-dir
    └── project/.cc-review/reviewers/   #   passed as --project-dir tests/fixtures/reviewers/project

docs/
└── reviewer-plugins.md                 # NEW: plugin authoring guide
README.md                               # MODIFIED: configuration and architecture sections
Makefile                                # MODIFIED: test target
```

**Structure Decision**: Reviewers move from `core/agents/` to a new `core/reviewers/` directory so the bundled discovery layer is a single, clearly named folder and `core/agents/` is left for the non-reviewer prompts (preamble, meta-review critics). All other changes are in-place modifications within the existing layout.

## Global Constraints

These apply to every task:

- **Shell**: Bash compatible with macOS default and Linux. Guard bashisms as existing scripts do. Use `yq` for YAML/frontmatter and `jq` for JSON; no other interpreters for new logic (the existing Python sanitizer is unrelated).
- **Harness neutrality**: Reviewer bodies never mention `ReportFindings`, `Agent`, or any harness tool. Only `review.md` knows how to dispatch.
- **No scope creep in the finding pipeline**: dedup, meta-review, fix loop, report, PR posting change only where the spec generalizes by-name behavior (dedup exemption, What Went Well, console table, status rows).
- **Backward compatibility**: legacy `agents.*` / `external_tools.*` keys and `--no-coderabbit`/`--no-copilot`/`--no-codex` flags keep working with a deprecation warning.
- **Shims**: resolve core, pass arguments, under 50 lines, no review logic.
- **Attribution**: gator plugin files carry upstream URL, commit, and Apache-2.0 notice.

## Complexity Tracking

No constitution violations to justify.
