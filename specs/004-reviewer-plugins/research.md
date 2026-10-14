# Research: Pluggable Reviewers

**Feature**: 004-reviewer-plugins | **Date**: 2026-10-13

## R-001: Frontmatter extraction in shell

**Decision**: Use `yq --front-matter=extract '.' <file>` to read frontmatter as YAML and `yq --front-matter=process` is not needed; the body is obtained by stripping the first `---`…`---` block with `awk`. Validation rules are applied with `jq` on the YAML converted to JSON (`yq -o=json`).

**Rationale**: `yq` v4 is already a required dependency and supports front matter natively. `awk` is available everywhere. No new dependency.

**Alternatives considered**: Parsing frontmatter with `sed`/`grep` only (fragile for nested maps like `severity_map`); a Python parser (adds an interpreter dependency for core logic; the existing Python file is an isolated helper).

## R-002: Discovery output shape and ownership

**Decision**: A new script `review/core/scripts/discover-reviewers.sh` performs discovery and emits one JSON array to stdout (see `contracts/discovery-output.md`). Warnings go to stderr. The review command sources nothing from it; it calls it once and stores the JSON in a variable (`REVIEWERS_JSON`) used by all later steps including fix-loop re-dispatch (FR-024).

**Rationale**: Keeps deterministic logic (file scanning, validation, override resolution, precondition evaluation) in a testable script. The markdown command stays an orchestration narrative that iterates the JSON. Mirrors the existing split between `resolve-config.sh` and `review.md`.

**Alternatives considered**: Doing discovery inline in `review.md` as prose instructions (untestable, easy for the orchestrating model to get wrong); a Python discovery tool (dependency).

## R-003: Layer resolution and override rules

**Decision**: Scan bundled, then user, then project. Build a map by `name`. A later (higher-precedence) valid entry replaces an earlier one entirely and records `overrides: "<lower layer>"`. An invalid entry never enters the map; if it would have overridden a valid lower entry, the warning says "falling back to <layer> version" (FR-009). Within one layer, when both `<name>.md` and `<name>/reviewer.md` exist, the file form wins with a warning.

**Rationale**: Directly implements FR-008 through FR-010 and the edge cases. Scanning lowest precedence first makes "replace" a simple map overwrite.

**Alternatives considered**: Field-level merging across layers (rejected by the spec: replace entirely).

## R-004: Reviewer name versus config key syntax

**Decision**: Reviewer names use hyphens (`test-quality`). Config keys are `reviewers.<name>`. `resolve_config` and `resolve_config_apply_cli_overrides` are extended to accept hyphens by converting dotted keys into bracket paths for `yq` (`.reviewers["test-quality"]`). Legacy keys `agents.<x>` and `external_tools.<x>` are mapped after merge by a new `resolve_config_migrate_legacy_keys` function: for each legacy key present, if `reviewers.<mapped-name>` is not already set, copy the value and print one deprecation warning naming the replacement key. Underscores in legacy names map to hyphens.

**Rationale**: Names appear in `source_agent`, console rows, and CLI flags, where hyphens are the existing convention (`test-quality`, `goal-alignment`). The current `yq` path syntax in `resolve_config` would break on hyphens, so the bracket conversion is required anyway.

**Alternatives considered**: Underscore names everywhere (breaks existing `source_agent` values and category names); keeping two parallel key families (defeats unification).

## R-005: Command reviewer output parsing

**Decision**: Three `output.format` values:
- `json`: tool prints a JSON array of objects already in the finding shape (`file`, `line` or `line_start`, `severity`, `description`, `rationale`, optional `fix`, `confidence`).
- `delimited`: tool prints blocks separated by `output.delimiter`; inside a block, lines of the form `<Label>: <value>` are mapped to finding fields by `output.fields` (a map from finding field to label). Multi-line values continue until the next known label.
- `parser`: `output.parser` names a script inside the plugin directory; it receives raw output on stdin and prints `json` format on stdout.

The command reviewer body holds parsing notes for the orchestrating model (for example, how CodeRabbit labels its blocks). Parsing of `delimited` and `json` output is performed by the orchestrator following those notes plus the format declaration; `parser` scripts are run via Bash.

**Rationale**: Covers the three migrated tools without inventing a regex language. CodeRabbit's `=============` blocks and Copilot's `### FINDING` markers both fit `delimited`. Codex CLI output is not stable enough to pin a format, so its plugin uses `delimited` with parsing notes and the orchestrator's judgment, as today.

**Alternatives considered**: Regex-based field extraction in frontmatter (hard to author, hard to validate); JSON-only (would force wrapper scripts for every tool).

## R-006: Timeouts for command reviewers

**Decision**: A helper `run_with_timeout <seconds> <command...>` in `discover-reviewers.sh` (sourced by review.md for invocation) uses `timeout` or `gtimeout` when available, otherwise runs unbounded and prints a verbose-level note. Non-zero exit or timeout marks the reviewer `failed` with reason.

**Rationale**: macOS lacks `timeout` by default; `coreutils` provides `gtimeout`. Graceful degradation keeps the review running (FR-022).

**Alternatives considered**: Background process plus `kill` after sleep (works but complicates output capture); requiring coreutils (new dependency).

## R-007: Prompt assembly for prompt reviewers

**Decision**: The orchestrator builds each subagent prompt as: `preamble.md` contents, then the reviewer body, then (if `references` non-empty) each referenced file under `## Reference: <relative path>`, then the review target (changed files), then spec and hints if present, then requested `context` blocks (`## Declared Goals` for `goals`, only when PR context exists), then the output contract. The output contract keeps today's ReportFindings-based instruction plus: "If you observed concrete positive patterns, end your final text output with a section headed `Positive observations:` containing 2-5 bullets, each citing a file and function or line." The orchestrator collects those sections from all reviewers into What Went Well (FR-006b).

**Rationale**: Matches FR-006 ordering. Keeps harness-specific tool naming in the orchestrator. Using the final text output for positive observations avoids changing the `ReportFindings` tool schema, which the plugin does not control.

**Alternatives considered**: A `positive_observations` field inside ReportFindings (tool schema is harness-owned); only goal-alignment producing What Went Well (rejected by clarification).

## R-008: Preconditions

**Decision**: `requires` tokens evaluated in `discover-reviewers.sh` given environment flags passed as arguments (`--pr <n|->`, `--spec <path|->`). Supported: `pr`, `spec`, `binary:<name>`. Unknown tokens mark the reviewer `skipped` with reason `unknown precondition: <token>`. For command reviewers, `detect` and `auth_check` run during discovery and set `skipped (not available)` / `skipped (not authenticated)`. An `invoke` template containing `{pr_number}` with no PR sets `skipped (requires: pr)` (FR-004a).

**Rationale**: One place computes dispatch eligibility; the orchestrator only reads `status`. Makes `init` trivial (same script, same output).

**Alternatives considered**: Evaluating preconditions in `review.md` prose (duplicated in `init.md`, untested).

## R-009: Dedup generalization and category enum

**Decision**: `finding.schema.json` `category` loses its enum and becomes a string matching `^[a-z0-9-]+$`; existing values remain documented in the description. Step 4 rule 5 becomes: findings whose reviewer has `dedup: isolated` are never merged with findings of a different category. `REVIEWERS_JSON` carries `dedup` so the orchestrator can look it up by `source_agent`.

**Rationale**: Contributed reviewers need arbitrary categories (FR-003 default `category = name`). Isolated dedup is the generalization of the goal-alignment exception (FR-025).

**Alternatives considered**: Keeping the enum and forcing contributed reviewers into `external` (loses signal in reports).

## R-010: Gator port

**Decision**: Port `.claude/agents/principal-engineer-reviewer.md` (OpenShell commit 5e414ea) into `review/core/reviewers/gator/reviewer.md`. Keep: three-priority persona (pragmatism, user empathy, security with CWE / OWASP ASVS / OWASP LLM Top 10 / CAPEC framing), review approach steps, severity definitions (Critical / Warning / Suggestion), the full "Pragmatic review calibration" block, blocker evidence rule ("state reachability, impact, and why the PR owns the problem"). Remove: OpenShell project context paragraph and `architecture` directory pointer, `sync-agent-infra` maintenance map item, Windows `test:windows` label routing, review-feedback-ledger item, the plan/architecture-review and requirements-to-plan sections (cc-review reviews code diffs only), "If something is good, say so briefly" (conflicts with preamble), and private security disclosure routing to OpenShell channels. The evidence contract from `references/review-findings-schema.md` is adapted into `references/findings-contract.md`: drop the JSON envelope and `GATOR-` IDs; keep the evidence field list and state that each finding's `rationale` must cover invariant, prerequisite, entry point, sink, base vs head behavior, observable impact, PR ownership, and that `failure_scenario` must be the reproducer. Frontmatter: `enabled: false`, `category: gator`, `severity_map: {Critical: Critical, Warning: Important, Suggestion: Minor}`, `references: [references/findings-contract.md]`. Attribution block at the end of `reviewer.md` with the upstream URL, commit, and Apache-2.0 notice. Verbatim upstream copies are stored under `specs/004-reviewer-plugins/upstream/` for the implementer.

**Rationale**: Implements FR-030 through FR-033 and the clarification on preamble conflicts. OpenShell is Apache-2.0 (verified in the repository LICENSE), so redistribution with attribution is permitted.

**Alternatives considered**: Wrapping gator's sandbox pipeline (out of scope, Codex-only, hard-coded repository).

## R-011: Testing approach

**Decision**: Add `tests/run.sh` with plain bash assertions and fixtures under `tests/fixtures/reviewers/` (valid file form, valid directory form, invalid frontmatter, duplicate name across layers, missing reference, reserved name, command kind with and without `detect` success). Tests exercise `discover-reviewers.sh` (status, overrides, warnings) and `resolve-config.sh` (legacy mapping, hyphenated keys, `--only`/`--no-` set arithmetic helper). `make test` runs it. Prompt dispatch and gator behavior are validated manually via `quickstart.md`.

**Rationale**: The deterministic parts of this feature are large enough to warrant automated tests, and the ship pipeline's per-task test checkpoints need a `make test` target to detect.

**Alternatives considered**: bats-core (new dependency); no tests (prior features did this, but discovery rules are too numerous to verify by hand).

## R-012: CLI flag derivation

**Decision**: The review command parses arguments generically: any `--no-<x>` where `<x>` is a discovered reviewer name disables it; `--no-external` / `--external` toggle all `kind: command` reviewers; `--only a,b` restricts to that set (error on unknown names); `--no-<x>` subtracts from the `--only` set; empty result is an error. Reserved words that may never be reviewer names: `external`, `fix`, `meta-review`, `only`, plus any existing flag suffix (`sequential`, `parallel`). Discovery rejects such names. Legacy `--no-coderabbit` etc. need no special handling because those are reviewer names.

**Rationale**: FR-015 through FR-017a. Reserved list computed from the existing flag table in `review.md`.

**Alternatives considered**: Explicit flag list in frontmatter of the shims (would require maintaining the list the spec forbids).
