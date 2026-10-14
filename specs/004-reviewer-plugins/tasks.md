# Tasks: Pluggable Reviewers

**Input**: Design documents from `specs/004-reviewer-plugins/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included. research.md R-011 decides on a bash test runner (`tests/run.sh`, `make test`) for the deterministic parts (discovery script, config resolution, CLI selection). Prompt-dispatch behavior is validated manually via quickstart.md.

**Organization**: Tasks are grouped by user story. Foundational work (discovery script, config resolution, migrated built-in files) must land before any story because the review command becomes discovery-driven in US1.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1 to US6)
- All paths are relative to the repository root

## Path Conventions

Plugin layout per plan.md: `review/core/{reviewers,agents,commands,schemas,scripts}/`, `review/config/`, harness shims under `review/skills/` (shared by Claude Code and Codex) and `review/opencode/command/`. Tests under `tests/`. Upstream gator sources under `specs/004-reviewer-plugins/upstream/`.

---

## Phase 1: Setup

**Purpose**: Directories, test runner skeleton, build target

- [x] T001 Create `review/core/reviewers/` and the fixture layer directories `tests/fixtures/reviewers/bundled/reviewers/`, `tests/fixtures/reviewers/user/`, `tests/fixtures/reviewers/project/.cc-review/reviewers/` (empty `.gitkeep` where needed) per plan.md Project Structure. The fixture layout mirrors the real flag semantics from contracts/discovery-output.md: `--core-dir tests/fixtures/reviewers/bundled` (script appends `reviewers/`), `--user-dir tests/fixtures/reviewers/user` (used as-is), `--project-dir tests/fixtures/reviewers/project` (script appends `.cc-review/reviewers/`)
- [x] T002 Create `tests/run.sh` test runner skeleton: bash strict mode, `assert_eq`, `assert_contains`, `assert_json` helpers using `jq`, a per-test temp dir, summary line `N passed, M failed`, non-zero exit on failure
- [x] T003 [P] Add `test` target to `Makefile` that runs `bash tests/run.sh`, and add it to the `help` target listing

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Discovery script, frontmatter contract, config resolution changes, migrated reviewer files. US1 cannot work until these exist.

- [x] T004 Create `review/core/schemas/reviewer.schema.json` encoding the frontmatter contract from `contracts/reviewer-frontmatter.md` and data-model.md (required `name`, `kind`; enums; `severity_map` value enum; command-only and prompt-only fields; `additionalProperties: true` with a description noting unknown fields are ignored)
- [x] T005 Implement `review/core/scripts/discover-reviewers.sh` argument parsing and layer scanning (`--core-dir`, `--project-dir`, `--user-dir`, `--pr`, `--spec`, `--skip-detection`, `--verbose`): resolve layer directories as `<core-dir>/reviewers/`, `<user-dir>` as given (default `$HOME/.cc-review/reviewers`), `<project-dir>/.cc-review/reviewers/`; enumerate `<name>.md` and `<name>/reviewer.md` in bundled, user, project order; same-layer duplicate rule (file form wins, warning); a directory without `reviewer.md` is ignored silently; per contracts/discovery-output.md
- [x] T006 Implement frontmatter extraction and validation in `review/core/scripts/discover-reviewers.sh`: `yq --front-matter=extract` to JSON, body stripped to a temp file under `${TMPDIR:-/tmp}/cc-review-reviewers.<pid>/`, all validation rules from contracts/reviewer-frontmatter.md producing `status: invalid` with the listed reason strings, defaults applied (`display_name`, `category`, `enabled`, `requires`, `severity_map`, `dedup`, `timeout_seconds`), reserved-name list from data-model.md
- [x] T007 Implement override resolution and precondition evaluation in `review/core/scripts/discover-reviewers.sh`: map by name with higher layer replacing lower (`overrides` field), invalid never shadows valid (fallback warning), `requires` tokens (`pr`, `spec`, `binary:<x>`, unknown), `{pr_number}` without PR, command `detect` / `auth_check` execution unless `--skip-detection`, output ordering per contract, single JSON array on stdout. Discovery never emits `status: disabled`: a valid reviewer whose preconditions pass is `ready` regardless of its `enabled` frontmatter (the `enabled` field is passed through for the caller, which applies enablement; quickstart.md scenario 2 expects gator `ready` with `enabled: false`)
- [x] T008 Implement sourced-mode helpers in `review/core/scripts/discover-reviewers.sh`: `run_with_timeout` (timeout/gtimeout fallback), `substitute_invoke`, `apply_cli_selection` (FR-015 to FR-017a including unknown-name error and empty-set error), `map_severity` (map, pass-through for valid cc-review severities, empty for drop); guard with `[[ "${BASH_SOURCE[0]}" == "$0" ]]` so execution runs main and sourcing only defines functions
- [x] T009 Extend `review/core/scripts/resolve-config.sh`: convert dotted keys to `yq` bracket paths so hyphenated keys work in `resolve_config` and `resolve_config_apply_cli_overrides`; widen the key regex to `^[a-zA-Z_][a-zA-Z0-9_.-]*$`
- [x] T010 Add `resolve_config_migrate_legacy_keys` to `review/core/scripts/resolve-config.sh` per contracts/cli-and-config.md (map `agents.*` and `external_tools.*` to `reviewers.<hyphenated>` when the new key is absent, one deprecation warning per legacy key to stderr) and call it from `resolve_config_init` after the merge
- [x] T011 Replace the hard-coded `agents.*` / `external_tools.*` boolean list in `resolve_config_validate_types` in `review/core/scripts/resolve-config.sh` with generic validation of every `reviewers.*` key (invalid value: warning and delete the key so the frontmatter default applies)
- [x] T012 [P] Relax `category` in `review/core/schemas/finding.schema.json` from enum to `"type": "string", "pattern": "^[a-z0-9-]+$"` with the existing values listed in the description
- [x] T013 [P] Move `review/core/agents/correctness.md` to `review/core/reviewers/correctness.md` (`git mv`) and prepend frontmatter: `name: correctness`, `display_name: "Correctness"`, `kind: prompt`, `category: correctness`
- [x] T014 [P] Move `review/core/agents/architecture.md` to `review/core/reviewers/architecture.md` with frontmatter `name: architecture`, `display_name: "Architecture & Idioms"`, `kind: prompt`, `category: architecture`
- [x] T015 [P] Move `review/core/agents/security.md` to `review/core/reviewers/security.md` with frontmatter `name: security`, `display_name: "Security"`, `kind: prompt`, `category: security`
- [x] T016 [P] Move `review/core/agents/production.md` to `review/core/reviewers/production.md` with frontmatter `name: production`, `display_name: "Production Readiness"`, `kind: prompt`, `category: production-readiness`
- [x] T017 [P] Move `review/core/agents/test-quality.md` to `review/core/reviewers/test-quality.md` with frontmatter `name: test-quality`, `display_name: "Test Quality"`, `kind: prompt`, `category: test-quality`
- [x] T018 [P] Move `review/core/agents/goal-alignment.md` to `review/core/reviewers/goal-alignment.md` with frontmatter `name: goal-alignment`, `display_name: "Goal Alignment"`, `kind: prompt`, `category: goal-alignment`, `requires: [pr]`, `context: [goals]`, `dedup: isolated`; rewrite PASS 3 so it ends the final output with a `Positive observations:` section instead of "What Went Well:" (keep the content rules: 2-5 bullets, concrete locations, no generic praise)
- [x] T019 Write discovery tests in `tests/run.sh` with fixtures under `tests/fixtures/reviewers/` (layer directories from T001: `bundled/reviewers/`, `user/`, `project/.cc-review/reviewers/`): valid file form, valid directory form with `references`, directory without `reviewer.md` ignored silently (no entry, no warning), missing frontmatter, name mismatch, reserved name, unknown kind, empty prompt body, missing reference, `..` reference, bad `severity_map` value, same-layer duplicate (file wins), cross-layer override (`overrides` set), invalid project reviewer falling back to valid bundled one, `requires: [pr]` skipped without `--pr` and ready with `--pr 1`, `binary:nonexistent` skipped, unknown precondition skipped, command reviewer missing `invoke`, `{pr_number}` without PR skipped, command `detect: false` skipped (not available), `auth_check: false` skipped (not authenticated), `--skip-detection` leaves command reviewer ready
- [x] T020 Write config and helper tests in `tests/run.sh`: hyphenated `resolve_config "reviewers.test-quality"`, CLI override with hyphenated key, legacy `agents.test_quality: false` maps to `reviewers.test-quality=false` with one warning, legacy key not applied when new key present, invalid `reviewers.x: maybe` warns and is removed, `apply_cli_selection` cases (`--only a,c`; `--no-b`; `--only a --no-a` error; `--only unknown` error; `external off` disables command kinds; `--only` re-enables config-disabled but not skipped), `map_severity` cases (mapped, pass-through, drop), `substitute_invoke` placeholder substitution
- [x] T021 Run `make test` and fix failures until all Phase 2 tests pass

**Checkpoint**: Discovery and config resolution work and are tested. The review command still references the old `core/agents/` paths; that is fixed in US1.

---

## Phase 3: User Story 1 - Drop-In Prompt Reviewer (Priority: P1) MVP

**Goal**: A reviewer file dropped into `.cc-review/reviewers/` is discovered, dispatched as a fresh-context subagent with preamble and output contract, and appears in findings and the console table.

**Independent Test**: quickstart.md scenario 3 (marker reviewer) produces a `Source: marker` finding and a "Marker" console row.

- [x] T022 [US1] Rewrite `review/core/commands/review.md` Step 2 "Detect External Tools" into "Discover Reviewers": call `discover-reviewers.sh` once with `--core-dir`, `--project-dir`, `--pr`/`--spec` when present, store `REVIEWERS_JSON`, print warnings, stop with an error when zero valid reviewers exist (FR-012); keep the test-command auto-detection and PR metadata subsections
- [x] T023 [US1] Rewrite `review/core/commands/review.md` Step 3 "Agent Selection", "Dispatch", and "Prompt Construction" to iterate `REVIEWERS_JSON` entries with `status: ready` and `kind: prompt`: prompt = `core/agents/preamble.md` + body file + each `references` file under `## Reference: <path>` + review target + spec/hints + `## Declared Goals` when `context` contains `goals` and goals exist + output contract (existing ReportFindings instruction plus the `Positive observations:` final-text instruction from research.md R-007); one Agent tool call per reviewer in a single response; `--sequential` unchanged; a subagent that errors or returns no parseable findings is recorded as `failed (subagent error)` in `REVIEWERS_JSON` and the review continues (FR-022); replace the hard-coded "Hard rule" list with "dispatch exactly the ready prompt reviewers from discovery"
- [x] T024 [US1] Update `review/core/commands/review.md` Step 3 progress reporting and Step 8 console summary to generate rows from `REVIEWERS_JSON` (display name, counts, status one of completed / disabled / skipped (reason) / failed (reason); note "(project override)" or "(user override)" when `overrides` is set); keep the Test Suite (regression) row and MVP line
- [x] T025 [US1] Update `review/core/commands/review.md` Step 4 to set `source_agent` = reviewer `name`, `category` = reviewer `category`, severity via `map_severity` (drop with warning on empty), and replace rule 5 with "findings from reviewers with `dedup: isolated` never merge with findings of other categories"
- [x] T026 [US1] Update `review/core/commands/review.md` Step 7 report header "Agents completed: N/6 (+ N external tools)" to "Reviewers completed: N/M (+ list of skipped/failed)" and Step 7.5j to aggregate `Positive observations:` sections from all prompt reviewers into "What Went Well" (FR-006b)
- [x] T027 [US1] Update `review/core/commands/review.md` Step 6 fix loop item 6 to re-dispatch the same `REVIEWERS_JSON` ready set on modified files (FR-024) and add temp body directory cleanup at the end of Step 8
- [x] T028 [US1] Add `tests/fixtures/reviewers/project/.cc-review/reviewers/marker.md` (the quickstart scenario 3 reviewer) and a discovery test asserting it is `ready` with `layer: project`, `category: marker`

**Checkpoint**: `make test` passes; a manual `/review --no-fix` with the marker reviewer in `.cc-review/reviewers/` shows the Marker row (quickstart 3).

---

## Phase 4: User Story 2 - Built-In Reviewers Become Plugins (Priority: P1)

**Goal**: The six built-ins run from `core/reviewers/` with identical behavior; legacy config keys keep working with a deprecation warning; the review command holds no reviewer-specific knowledge.

**Independent Test**: quickstart.md scenario 4 (legacy `agents.test_quality: false` disables Test Quality with a warning) and scenario 10 (`rg` finds no reviewer paths or invocations in review.md).

- [x] T029 [P] [US2] Rewrite `review/config/config-template.yml`: replace `agents:` and `external_tools:` with a `reviewers:` section listing the ten bundled reviewers with defaults from data-model.md (copilot and gator false), update the header comment
- [x] T030 [P] [US2] Rewrite `review/config/profiles/quick.yml`, `review/config/profiles/thorough.yml`, `review/config/profiles/ci.yml` to use `reviewers:` keys (quick: only correctness and security true, all command reviewers false; thorough and ci: all true except gator false)
- [x] T031 [US2] Update `review/core/commands/review.md` Prerequisites: remove `CODERABBIT`/`COPILOT`/`CODEX` variables and the `--no-coderabbit`-style override lines; after `resolve_config_init`, apply enablement onto `REVIEWERS_JSON`: for every entry with `status: ready`, effective enabled = `resolve_config "reviewers.<name>"` when the key is present, else the entry's `enabled` field; set `status: disabled` with `reason: "disabled"` when effective enabled is false (entries with `skipped` or `invalid` status are left untouched). Legacy mapping and deprecation warnings surface through `resolve-config.sh`
- [x] T032 [US2] Verify FR-028 by running `rg -n "core/agents/(correctness|architecture|security|production|test-quality|goal-alignment)|coderabbit review|copilot -s|codex review|Agent 6|CODERABBIT_AVAILABLE|COPILOT_AVAILABLE|CODEX_AVAILABLE" review/core/commands/review.md` and removing every remaining occurrence (the preamble path `core/agents/preamble.md` and meta-review agent paths stay)
- [x] T033 [US2] Add a config test in `tests/run.sh` that merges `review/config/config-template.yml` with each profile and asserts no `agents` or `external_tools` keys exist and every `reviewers.*` value is boolean (FR-018)

**Checkpoint**: Default run dispatches the six prompt reviewers; legacy config warns; `review.md` is reviewer-agnostic.

---

## Phase 5: User Story 3 - External CLI Tools as Command Reviewers (Priority: P2)

**Goal**: CodeRabbit, Copilot CLI, and Codex CLI are `kind: command` plugins; any command reviewer is detected, invoked with a timeout, parsed per its declared output format, and marked failed on error without blocking the review.

**Independent Test**: quickstart.md scenario 5 (fake-tool with `output.format: json`) yields one Important finding; `detect: false` yields `skipped (not available)`.

- [x] T034 [P] [US3] Create `review/core/reviewers/coderabbit.md` (`kind: command`, `category: external`, `enabled: true`, `detect: "command -v coderabbit"`, `auth_check: "coderabbit auth status"`, `invoke: "coderabbit review --agent --base {base_branch} --committed"`, `severity_map` critical/major/minor/info, `output: delimited` with `=============` and File/Line/Severity/Description/Rationale labels; body: parsing notes from the current review.md CodeRabbit paragraph, default confidence 75)
- [x] T035 [P] [US3] Create `review/core/reviewers/copilot.md` (`kind: command`, `category: external`, `enabled: false`, `detect: "command -v copilot"`, `auth_check: "gh auth status"`, `invoke` carrying the current `copilot -s -p "..."` prompt extended to request `### FINDING` blocks with `File:`, `Line:`, `Severity:`, `Description:`, `Rationale:` lines, `output: delimited` with delimiter `### FINDING`; body: discard findings under `specs/`, default confidence 75)
- [x] T036 [P] [US3] Create `review/core/reviewers/codex.md` (`kind: command`, `category: external`, `enabled: true`, `detect: "command -v codex"`, `auth_check: "codex --version"`, `invoke: "codex review --base {base_branch}"`, `output: delimited` with a blank-line delimiter and best-effort labels; body: parsing notes stating that Codex output varies and the orchestrator should extract file, line, severity, description, rationale per finding, default confidence 75)
- [x] T037 [US3] Add "Command Reviewer Invocation" to `review/core/commands/review.md` Step 3 replacing "External Tool Invocations": for each ready `kind: command` entry, `substitute_invoke`, run via `run_with_timeout` with `timeout_seconds`, on exit 124 or non-zero mark `failed (timeout)` / `failed (exit N)` and continue; parse stdout per `output.format` (`json`: validate array and map fields; `delimited`: split on delimiter, map labels via `output.fields`, follow body parsing notes; `parser`: pipe raw output into the script and treat its stdout as `json`); on unparseable output mark `failed (parse error)` and log the first 20 lines at verbose level; set `source_agent`, `category`, mapped severity, confidence 75 when absent
- [x] T038 [US3] Replace `detect_external_tools` in `review/core/scripts/detect-tools.sh` with `detect_command_reviewers <reviewers_json>` that prints `name:available:auth_status` lines derived from discovery status (`ready` → `true:`, `skipped not available` → `false:`, `skipped not authenticated` → `true:not_authenticated`), keeping `detect_test_command` and `detect_platform` unchanged; update the single call site `TOOL_RESULTS=$(detect_external_tools)` in `review/core/commands/init.md` Step 1 to run `discover-reviewers.sh --core-dir "$(dirname "$0")/.." --project-dir "$(git rev-parse --show-toplevel)"` and pass the result to `detect_command_reviewers`, so init keeps working until T043 rewrites that step
- [x] T039 [US3] Add tests in `tests/run.sh`: a command fixture with `output.format: json` whose `invoke` is a fixture script printing a JSON finding array, asserting discovery marks it ready and `substitute_invoke` produces the expected command line; a fixture with `output.format: parser` whose parser script is present and executable (ready) and one where it is missing (invalid); `run_with_timeout 1 sleep 3` returns 124 when a timeout binary exists

**Checkpoint**: Command reviewers are discovered, invoked, and parsed through the generic path; `--no-external` works through `apply_cli_selection`.

---

## Phase 6: User Story 4 - Gator Reviewer Bundled (Priority: P2)

**Goal**: A ported, attributed, preamble-compatible gator prompt reviewer in directory form, disabled by default, with the evidence contract inlined via `references` and severities mapped.

**Independent Test**: quickstart.md scenario 6 (gator finds a reachable bug with an evidence-structured rationale) and the `rg` check for OpenShell-specific strings.

- [x] T040 [P] [US4] Create `review/core/reviewers/gator/references/findings-contract.md` adapted from `specs/004-reviewer-plugins/upstream/review-findings-schema.md` per research.md R-010: drop the JSON envelope and `GATOR-` IDs; keep the evidence field list; state that `rationale` must cover invariant, prerequisite, supported entry point, sink, base vs head behavior, observable impact, PR ownership, requested change, and that `failure_scenario` must be a minimal deterministic reproducer; state that a Critical or Warning lacking any evidence field must be reported as Suggestion instead; group sibling sites under one finding
- [x] T041 [US4] Create `review/core/reviewers/gator/reviewer.md` ported from `specs/004-reviewer-plugins/upstream/principal-engineer-reviewer.md` per research.md R-010: frontmatter (`name: gator`, `display_name: "Gator (Principal Engineer)"`, `kind: prompt`, `category: gator`, `enabled: false`, `severity_map` Critical/Warning/Suggestion to Critical/Important/Minor, `references: [references/findings-contract.md]`); keep persona, review approach, severity definitions, pragmatic calibration, blocker evidence rule; remove OpenShell project context, architecture directory pointer, sync-agent-infra item, Windows label routing, ledger item, plan/architecture/requirements review sections, "if something is good, say so" line, OpenShell security-channel routing; end with an attribution section citing the upstream URL, commit 5e414ea, and the Apache-2.0 license
- [x] T042 [US4] Add bundled gator checks to `tests/run.sh`: discovery of the real bundled directory (`--core-dir review/core --skip-detection`) returns ten entries (requires T034 to T036 to exist), gator has `kind: prompt`, `status: ready`, `enabled: false`, one resolved reference path that exists, and `rg -n "OpenShell|Fern|Windows|ledger|sync-agent-infra" review/core/reviewers/gator/reviewer.md` reports only lines whose number is greater than the line of the `## Attribution` heading (obtain it with `rg -n "^## Attribution"`)

**Checkpoint**: `reviewers.gator: true` dispatches gator with the contract inlined; default runs show gator as disabled.

---

## Phase 7: User Story 5 - Layered Discovery and Overrides (Priority: P3)

**Goal**: User and project layers override bundled reviewers by name with a console note; `/cc-review:init` lists discovered reviewers and generates `reviewers.*` keys.

**Independent Test**: quickstart.md scenario 7 (project `security.md` replaces bundled) and scenario 9 (init table and generated config).

- [x] T043 [US5] Rewrite `review/core/commands/init.md` Step 1 and Step 2: call `discover-reviewers.sh` (`--core-dir`, `--project-dir`), print the "Discovered reviewers" table from contracts/cli-and-config.md (name, layer, kind, enabled, preconditions), use `detect_command_reviewers` for the auth warnings, and generate a `reviewers:` section listing every discovered reviewer with its effective enabled value instead of `agents:` / `external_tools:`
- [x] T044 [US5] Update `review/core/commands/init.md` Interactive Mode Sections 1 and 2 into one "Reviewers" section that iterates discovered reviewers (display name, kind, layer, precondition status) and asks enable/disable for each; update Step 4 detection results line to list command reviewers by name
- [x] T045 [US5] Confirm override behavior end to end by adding a `tests/run.sh` case that places `security.md` in `tests/fixtures/reviewers/project/.cc-review/reviewers/` (a copy of the bundled file with `display_name: "Security (project)"`, discovered with `--core-dir review/core --skip-detection`) and asserts the result has one `security` entry with `layer: project`, `overrides: bundled`, and the project `display_name`

**Checkpoint**: Overrides visible in console and init; init emits only `reviewers.*` keys.

---

## Phase 8: User Story 6 - Derived CLI Flags (Priority: P3)

**Goal**: `--no-<name>`, `--only`, `--external`, `--no-external` work for any discovered reviewer with no flag list maintained in the core; shims advertise the generic flags.

**Independent Test**: quickstart.md scenario 8 (four flag combinations behave as specified).

- [x] T046 [US6] Update `review/core/commands/review.md` Prerequisites argument handling: collect every `--no-<x>` into `NO_LIST`, `--only <csv>` into `ONLY_LIST`, `--external` / `--no-external` into `EXTERNAL_FLAG`, then call `apply_cli_selection "$REVIEWERS_JSON" "$ONLY_LIST" "$NO_LIST" "$EXTERNAL_FLAG"` after config application; stop with the helper's error on unknown names or an empty set; after selection, if no reviewer has `status: ready`, stop with a message listing every discovered reviewer and its status reason (disabled, skipped (reason)) per the spec edge case; keep `--no-fix`, `--no-meta-review`, `--sequential`, `--max-rounds` handling unchanged
- [x] T047 [P] [US6] Update `review/core/commands/review.md` frontmatter `argument-hint` to the generic list in contracts/cli-and-config.md
- [x] T048 [P] [US6] Update `review/skills/review/SKILL.md` (the shim shared by Claude Code and Codex) argument-hint and "Pass through all arguments" list to the generic flags (`--no-<reviewer>`, `--only <reviewer,...>`, `--external`, `--no-external`), keeping the file under 50 lines
- [x] T049 [P] [US6] Update `review/opencode/command/review.md` pass-through list the same way, under 50 lines
- [x] T050 [US6] Extend `tests/run.sh` `apply_cli_selection` coverage with the quickstart scenario 8 combinations against the real bundled discovery output (`--only correctness,security`; `--only correctness --no-correctness` error; `--only nope` error; `external off` disables coderabbit, copilot, codex only)

**Checkpoint**: All six user stories complete.

---

## Phase 9: Polish & Cross-Cutting Concerns

- [x] T051 [P] Write `docs/reviewer-plugins.md`: plugin authoring guide covering file and directory forms, every frontmatter field with defaults, prompt body conventions (no harness tool names, preamble always applied), `references` and `context`, command kind with the three output formats and placeholders, discovery layers and overrides, config and CLI, a worked prompt example and a worked command example, and the gator plugin as a reference
- [x] T052 [P] Update `README.md`: Features bullet for pluggable reviewers, Configuration section (`reviewers:` keys, legacy keys deprecated, `--no-<reviewer>` and `--only` flags), Architecture section (`core/reviewers/` directory, discovery layers), Review Agents section listing gator as opt-in, link to `docs/reviewer-plugins.md`
- [x] T053 [P] Update `docs/standalone-guide.md` config example from `external_tools:` to `reviewers:` keys
- [x] T054 [P] Bump `review/VERSION`, `VERSION`, `review/.claude-plugin/plugin.json`, and `review/.codex-plugin/plugin.json` to 1.2.0 and add a changelog note in `README.md` if a changelog section exists
- [x] T055 Run `make test` and `make validate`; fix any failures
- [x] T056 Run quickstart.md scenarios 2 and 10 (discovery listing and harness-neutrality `rg` checks), time `discover-reviewers.sh --core-dir review/core --project-dir tests/fixtures/reviewers/project --skip-detection` against the bundled set plus at least 20 fixture reviewers (plan.md Performance Goal: under one second), and record results in `specs/004-reviewer-plugins/quickstart.md` under a "Validation log" heading with the date
- [x] T057 Run `bash -n` on `review/core/scripts/discover-reviewers.sh`, `review/core/scripts/resolve-config.sh`, `review/core/scripts/detect-tools.sh`, `tests/run.sh` and `shellcheck` if available; fix reported issues

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies
- **Foundational (Phase 2)**: depends on Phase 1; blocks all user stories
- **US1 (Phase 3)**: depends on Phase 2; delivers the MVP (discovery-driven dispatch with the six migrated reviewers plus drop-ins)
- **US2 (Phase 4)**: depends on US1 (config application happens in the rewritten review.md prerequisites)
- **US3 (Phase 5)**: depends on US1 (generic dispatch loop); independent of US2
- **US4 (Phase 6)**: T040 and T041 depend on Phase 2 only; T042 depends on US3 (its ten-entry count includes the three command reviewers); manual validation needs US1
- **US5 (Phase 7)**: depends on US3 (init uses `detect_command_reviewers`); override logic itself is in Phase 2
- **US6 (Phase 8)**: depends on US1 and US2 (argument handling in the same prerequisites block)
- **Polish (Phase 9)**: depends on all stories

### User Story Dependencies

```text
Phase 2 ──> US1 ──> US2 ──> US6
        │     └──> US3 ──> US5
        │            └──> US4 (T042 only)
        └──> US4 (T040, T041)
```

### Within Each Phase

- Files marked [P] can be edited concurrently; tasks touching `review.md` (T022 to T027, T031, T032, T037, T046, T047) must run sequentially because they edit the same file
- Tests (T019, T020, T028, T033, T039, T042, T045, T050) are written after the code they exercise within the same phase and must pass before the phase checkpoint

## Parallel Execution Examples

**Phase 2**: T012 to T018 (schema relax and six file moves with frontmatter) in parallel while T005 to T008 (discovery script) proceed sequentially; T009 to T011 (resolve-config) in parallel with the discovery script.

**Phase 5**: T034, T035, T036 (three command reviewer files) in parallel, then T037, T038.

**Phase 8**: T047 to T049 (three argument-hint updates) in parallel after T046.

**Phase 9**: T051 to T054 in parallel, then T055 to T057.

## Implementation Strategy

**MVP (Phases 1 to 3)**: Discovery script with tests, migrated built-in reviewer files, and a discovery-driven review command. At this point any drop-in prompt reviewer works and the six built-ins still run. Command reviewers temporarily absent until Phase 5 (acceptable in the MVP branch, not for merge).

**Increment 2 (Phases 4 to 5)**: Config migration with legacy aliases, and command reviewers restored as plugins. Feature parity with the current release is reached here.

**Increment 3 (Phases 6 to 8)**: Gator, layered overrides in init, derived CLI flags and shim updates.

**Increment 4 (Phase 9)**: Documentation, version bump, validation log.

## Notes

- Total tasks: 57. Per story: Setup 3, Foundational 18, US1 7, US2 5, US3 6, US4 3, US5 3, US6 5, Polish 7.
- `review.md` is edited by many tasks; keep each edit scoped to the named step to avoid conflicts.
- Never reference `ReportFindings` or the Agent tool inside any file under `review/core/reviewers/`.
- Commit after each phase checkpoint.
