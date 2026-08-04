# Tasks: Configuration System

**Input**: Design documents from `/specs/002-config-system/`

**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md

**Tests**: Not explicitly requested. No test tasks generated.

**Organization**: Tasks grouped by user story. US1+US5 combined (config options + resolution chain are inseparable). US2+US3 combined (--config and --profile flags are part of the same resolution chain). US4 is standalone (init skill).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to

---

## Phase 1: Setup

**Purpose**: Restructure config template and create profile directory

- [x] T001 Restructure review/config/config-template.yml from flat keys to nested sections per data-model.md (agents, severity, pr_posting, output, test, external_tools, triage, max_fix_rounds)
- [x] T002 [P] Create review/config/profiles/ directory and add ci.yml profile preset (all agents, all tools, verbose, no interactive)
- [x] T003 [P] Add thorough.yml profile preset in review/config/profiles/ (all agents, all tools, strict thresholds, 5 fix rounds)
- [x] T004 [P] Add quick.yml profile preset in review/config/profiles/ (correctness + security only, no external tools, 1 fix round, quiet)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Resolution chain infrastructure that all commands depend on

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T005 Refactor review/core/scripts/resolve-config.sh: add `resolve_config_init` function that accepts `--config <path>` and `--profile <name>` arguments, builds the full layer stack (defaults, user, project, profile, config), performs recursive deep merge via `yq`, and writes the merged result to a temp file. Existing `resolve_config <key> <default>` reads from the merged temp file. Add cleanup trap.
- [x] T006 Add `resolve_config_apply_cli_overrides` function to review/core/scripts/resolve-config.sh that applies individual CLI flag overrides (e.g., `--no-coderabbit` sets `external_tools.coderabbit: false`) on top of the merged config.
- [x] T007 Add validation logic inside `resolve_config_init` in resolve-config.sh: if `--config` points to nonexistent file, print "Error: config file not found: <path>" to stderr and exit 1. If `--profile` names a nonexistent profile, list available `.yml` files from review/config/profiles/ and exit 1. Run `yq '.' "$file" >/dev/null 2>&1` on each config source; on failure, print "Error: invalid YAML in <path>: <yq error>" and exit 1. This validation is centralized so all callers (review.md, triage.md) inherit it.

**Interfaces** (consumed by Phase 3+):

```bash
# Initialize the merged config from all layers. Call once at command startup.
# Writes merged result to a temp file; sets up EXIT trap for cleanup.
# Parameters:
#   --config <path>   Optional explicit config file (validated: must exist, must be valid YAML)
#   --profile <name>  Optional profile name (validated: must match a file in config/profiles/)
# Side effect: sets CC_REVIEW_MERGED_CONFIG to the temp file path
resolve_config_init [--config <path>] [--profile <name>]

# Read a single key from the merged config.
# Unchanged signature for backward compatibility.
# Parameters:
#   $1  Dotted key path (e.g., "agents.security", "severity.min_confidence")
#   $2  Default value if key is unset
# Returns: the resolved value on stdout
resolve_config <key> <default>

# Apply CLI flag overrides on top of the merged config.
# Called after resolve_config_init, before resolve_config reads.
# Parameters:
#   Associative list of dotted-key=value pairs (e.g., "external_tools.coderabbit=false")
resolve_config_apply_cli_overrides <key=value>...
```

**Checkpoint**: Resolution chain ready. All commands can now use the expanded config.

---

## Phase 3: User Stories 1+5 - Config Options and Resolution Chain (Priority: P1) MVP

**Goal**: Expanded config sections are read by the review command via the resolution chain. Config file at any level controls agent selection, severity, output, and PR posting behavior.

**Independent Test**: Create configs at project and user level with different agent settings. Run review. Verify correct agents run per resolution order.

### Implementation for User Stories 1+5

- [x] T008 [US1] Update review/core/commands/review.md Step 3 (agent dispatch) to read agent toggles from config via `resolve_config "agents.<name>" "true"` and skip disabled agents
- [x] T009 [US1] Update review/core/commands/review.md to read severity settings from config: `severity.min_confidence` for filtering, `severity.request_changes_severities` for event type, `severity.auto_fix` for fix loop control
- [x] T010 [US1] Update review/core/commands/review.md Step 7 (findings report) to read output settings from config: `output.dir`, `output.findings_filename`, `output.verbosity`
- [x] T011 [US5] Update review/core/commands/review.md argument parsing to accept `--config <path>` and `--profile <name>`, pass them to `resolve_config_init` at command startup
- [x] T012 [US5] Update review/core/commands/triage.md argument parsing to accept `--config <path>` and `--profile <name>`, pass them to `resolve_config_init` at command startup

**Checkpoint**: Config-driven review works. Agents, severity, and output are configurable.

---

## Phase 4: User Stories 2+3 - CLI Override and Profiles (Priority: P1/P2)

**Goal**: `--config` points to external config file for CI. `--profile` loads shipped presets. Both integrate into the resolution chain.

**Independent Test**: Run with `--config /tmp/test.yml` and verify settings apply. Run with `--profile ci` and verify CI behavior.

### Implementation for User Stories 2+3

- ~~T013~~ Removed: validation is centralized in T007 (`resolve_config_init`)
- ~~T014~~ Removed: validation is centralized in T007 (`resolve_config_init`)
- [x] T015 [P] [US2] Update review/skills/review/SKILL.md to pass `--config` and `--profile` flags through to core command
- [x] T016 [P] [US2] Update review/skills/triage/SKILL.md to pass `--config` and `--profile` flags through to core command

**Checkpoint**: CI users can point to external configs. Developers can switch profiles.

---

## Phase 5: User Story 4 - Init Skill (Priority: P2)

**Goal**: Interactive init skill detects tools, generates config, and writes .cc-review/config.yml.

**Independent Test**: Run init in a project with known tools. Verify generated config reflects detections.

### Implementation for User Story 4

- [x] T017 [US4] Create review/core/scripts/detect-tools.sh with functions: `detect_external_tools` (check coderabbit/copilot/codex CLIs via `command -v` and auth per R-002), `detect_test_command` (priority: Makefile test target > package.json > go.mod > pyproject.toml > Cargo.toml per R-002), `detect_platform` (parse `git remote get-url origin` for github.com/gitlab.com; if `git rev-parse` fails or no remote exists, print "Warning: not a git repository, skipping platform detection" to stderr and set platform to empty string)
- [x] T018 [US4] Create review/core/commands/init.md: smart-defaults mode that calls detect-tools.sh, generates YAML config from detections, shows preview, asks for confirmation, writes .cc-review/config.yml
- [x] T019 [US4] Add `--interactive` mode to init.md: walk through each config section (agents, external_tools, severity, output, pr_posting, test) with questions and options
- [x] T020 [US4] Implement config merge in init.md: when .cc-review/config.yml exists, read existing config, deep-merge with detections (existing values preserved), present diff, write merged result
- [x] T021 [US4] Create review/skills/init/SKILL.md: shim that resolves core directory and delegates to core/commands/init.md, passing --interactive flag if provided

**Checkpoint**: Users can set up config without editing YAML manually.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Edge cases, documentation, backward compatibility

- [x] T022 [P] Verify unknown-key tolerance in resolve-config.sh: since `resolve_config <key>` reads individual keys and `yq` merge passes through all keys, unknown keys are naturally ignored. Add a shell comment in `resolve_config_init` documenting this guarantee. If any future validation step rejects unknown keys, this is where to add the allowlist bypass.
- [x] T023 [P] Add `resolve_config_validate_types` function in resolve-config.sh called after merge. Validate: `agents.*` and `external_tools.*` values are boolean (`true`/`false`), `severity.min_confidence` is integer 0-100, `output.verbosity` is one of `quiet|normal|verbose`, `max_fix_rounds` is positive integer, `test.timeout_seconds` is positive integer. For each invalid value, print "Warning: invalid value for <key>: '<value>', using default" to stderr and overwrite the key in the merged config with the default from config-template.yml via `yq`.
- [x] T024 [P] Update review/core/commands/review.md to read `pr_posting.auto_detect_pr` from config and auto-detect PR number when true
- [x] T025 Run quickstart.md validation scenarios

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies, start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (needs restructured config template)
- **US1+US5 (Phase 3)**: Depends on Phase 2 (needs resolve_config_init)
- **US2+US3 (Phase 4)**: Depends on Phase 3 (needs --config/--profile wired into commands)
- **US4 (Phase 5)**: Depends on Phase 2 (needs resolve_config for merge logic)
- **Polish (Phase 6)**: Depends on Phase 3 minimum

### Parallel Opportunities

- T002, T003, T004 can run in parallel (Phase 1, different profile files)
- T015, T016 can run in parallel (Phase 4, different skill shims)
- T022, T023, T024 can run in parallel (Phase 6, different concerns)

---

## Implementation Strategy

### MVP First (Phase 1 + 2 + 3)

1. Restructure config template + create profiles
2. Refactor resolve-config.sh with full resolution chain
3. Wire agent selection + severity + output into review command
4. **STOP and VALIDATE**: Test config-driven agent selection

### Incremental Delivery

1. Setup + Foundational -> Config infrastructure ready
2. US1+US5 -> Config-driven review works (MVP)
3. US2+US3 -> --config and --profile flags work
4. US4 -> Init skill generates config interactively
5. Polish -> Edge cases and auto_detect_pr

---

## Notes

- The config template restructuring (T001) is a breaking change from the flat format
- resolve_config_init must be called once at command startup, not per-key
- Profile files are shipped read-only assets under review/config/profiles/
- The init skill shim follows the same contract as review and triage shims
