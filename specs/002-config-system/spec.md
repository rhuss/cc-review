# Feature Specification: Configuration System

**Feature Branch**: `002-config-system`

**Created**: 2026-08-04

**Status**: Draft

**Input**: User description: "Expand cc-review's configuration with agent selection, PR posting defaults, severity thresholds, output settings, --config/--profile flags, and an interactive init skill."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Expanded Configuration Options (Priority: P1)

A project maintainer wants to customize cc-review behavior without modifying command files. They create a `.cc-review/config.yml` file that disables the test-quality and goal-alignment agents, sets the minimum confidence threshold to 80, and configures verbose output. When they run cc-review, only the enabled agents execute, findings below 80 confidence are filtered, and the output is verbose.

**Why this priority**: Configuration is the foundation for all other user stories. Without expanded options, users must accept defaults or pass numerous CLI flags every run.

**Independent Test**: Create a config file with specific agent and severity settings, run cc-review, and verify only enabled agents produce findings above the configured threshold.

**Acceptance Scenarios**:

1. **Given** a config with `agents.test_quality: false`, **When** cc-review runs, **Then** the test-quality agent is not dispatched and does not appear in the report.
2. **Given** a config with `severity.min_confidence: 80`, **When** cc-review finds a 75-confidence issue, **Then** the finding is excluded from the report.
3. **Given** a config with `output.verbosity: verbose`, **When** cc-review runs, **Then** agent progress, timing, and intermediate results are shown.
4. **Given** no config file exists, **When** cc-review runs, **Then** all agents are enabled with default thresholds (existing behavior preserved).

---

### User Story 2 - CLI Config Override (Priority: P1)

A CI pipeline operator runs cc-review in a GitHub Action and points to a config file stored in the pipeline repository using `--config /path/to/ci-config.yml`. The config file disables interactive prompts, enables all agents, and sets output to a specific directory. CLI flags still override individual settings from the config file.

**Why this priority**: CI/automation is a primary use case. Without `--config`, users must either copy config files into every repo or rely solely on CLI flags.

**Independent Test**: Run cc-review with `--config` pointing to a file outside the project, verify its settings are applied while CLI flags still override.

**Acceptance Scenarios**:

1. **Given** a config file at `/tmp/ci-config.yml` with `output.dir: /tmp/results`, **When** cc-review runs with `--config /tmp/ci-config.yml`, **Then** the findings report is written to `/tmp/results/`.
2. **Given** the same config file enables CodeRabbit, **When** cc-review runs with `--config /tmp/ci-config.yml --no-coderabbit`, **Then** CodeRabbit is disabled (CLI flag wins).
3. **Given** `--config` points to a nonexistent file, **When** cc-review runs, **Then** it reports an error and stops (does not fall back to defaults silently).
4. **Given** `--config` is used alongside a project `.cc-review/config.yml`, **When** cc-review runs, **Then** the `--config` file's values override the project config, and the project config fills in unspecified keys.

---

### User Story 3 - Profile Presets (Priority: P2)

A developer wants a quick review during development (fewer agents, no external tools) and a thorough review before merging (all agents, all tools, strict thresholds). They run `cc-review --profile quick` for the first and `cc-review --profile thorough` for the second, without maintaining separate config files.

**Why this priority**: Profiles reduce friction for common workflows. Without them, switching between review modes requires remembering multiple CLI flags or maintaining custom config files.

**Independent Test**: Run cc-review with `--profile quick` and verify fewer agents run. Then run with `--profile thorough` and verify all agents and tools are active.

**Acceptance Scenarios**:

1. **Given** `--profile quick` is used, **When** cc-review runs, **Then** only correctness and security agents run, no external tools, one fix round, minimal output.
2. **Given** `--profile thorough` is used, **When** cc-review runs, **Then** all agents and external tools run, with higher confidence thresholds and up to 5 fix rounds.
3. **Given** `--profile ci` is used, **When** cc-review runs, **Then** interactive prompts are suppressed, all agents run, and output is verbose for log capture.
4. **Given** `--profile nonexistent` is used, **When** cc-review runs, **Then** it reports an error listing available profiles and stops.
5. **Given** `--profile quick --no-coderabbit` is used, **When** cc-review runs, **Then** the CLI flag overrides the profile setting (CodeRabbit disabled even if the profile enables it).

---

### User Story 4 - Interactive Init (Priority: P2)

A new cc-review user runs `/cc-review:init` to set up configuration. The init skill detects that CodeRabbit CLI is installed but not authenticated, detects `make test` as the test command, and identifies GitHub as the platform. It shows the generated config and asks the user to confirm before writing `.cc-review/config.yml`.

**Why this priority**: Manual YAML editing is error-prone and unfriendly. Init lowers the barrier to adoption by auto-detecting the environment and generating valid configuration.

**Independent Test**: Run init in a project with known tools installed, verify the generated config reflects detected tools and the written file is valid YAML.

**Acceptance Scenarios**:

1. **Given** CodeRabbit CLI is installed and authenticated, **When** init runs in smart-defaults mode, **Then** the generated config has `external_tools.coderabbit: true`.
2. **Given** CodeRabbit CLI is installed but not authenticated, **When** init runs, **Then** the generated config has `external_tools.coderabbit: true` but init warns about authentication.
3. **Given** no external tools are installed, **When** init runs, **Then** all external tools are set to `false` in the generated config.
4. **Given** a Makefile with a `test` target exists, **When** init runs, **Then** `test_command` is set to `make test`.
5. **Given** init runs with `--interactive`, **When** each config section is presented, **Then** the user can modify values before moving to the next section.
6. **Given** a `.cc-review/config.yml` already exists, **When** init runs, **Then** it merges new detections with existing values (does not overwrite user customizations).

---

### User Story 5 - Resolution Chain (Priority: P1)

A developer has a user-level config at `~/.cc-review/config.yml` (personal preferences), a project-level config at `.cc-review/config.yml` (team settings), and runs cc-review with `--profile ci` and `--no-coderabbit`. The resolution chain applies in order: the CLI flag disables CodeRabbit, the profile sets CI defaults, the project config fills remaining team settings, the user config fills personal preferences, and built-in defaults fill anything still unspecified.

**Why this priority**: Predictable configuration resolution is essential for trust. Users need to know which setting wins when multiple sources specify the same key.

**Independent Test**: Set up configs at all levels with different values for the same key, run cc-review with a profile and CLI flag, verify the correct resolution order.

**Acceptance Scenarios**:

1. **Given** user config sets `max_fix_rounds: 5` and project config sets `max_fix_rounds: 2`, **When** cc-review runs without CLI override, **Then** `max_fix_rounds` is 2 (project wins over user).
2. **Given** project config sets `agents.security: false` and `--profile thorough` sets all agents to true, **When** cc-review runs with `--profile thorough`, **Then** security agent is enabled (profile wins over project).
3. **Given** all sources are present, **When** cc-review runs with `--config /tmp/override.yml --profile ci --no-coderabbit`, **Then** the resolution order is: CLI flags > --config > --profile > project > user > defaults.

---

### Edge Cases

- What happens when a config file contains unknown keys? They are silently ignored (forward compatibility with future config options).
- What happens when a config value has an invalid type (e.g., `agents.security: "maybe"` instead of boolean)? The system uses the default value for that key and logs a warning.
- What happens when `--config` and `--profile` are both provided? Both are applied in the resolution chain (--config overrides --profile for overlapping keys).
- What happens when the init skill runs in a non-git directory? It warns that platform detection is unavailable and generates config without platform-specific settings.
- What happens when a profile file is corrupted or invalid YAML? The system reports the parse error with the profile path and stops.

## Clarifications

### Session 2026-08-04

- Q: What does `pr_posting.auto_detect_pr` mean exactly? → A: When true, the review command checks if an open PR exists for the current branch (via platform abstraction) and automatically uses it, as if `--pr <number>` were passed. When false (default), `--pr` must be explicit; if neither `auto_detect_pr` nor `--pr` is provided, the review runs without PR context (diff-only mode against the main branch).
- Q: What is the YAML structure for `severity.auto_fix`? → A: A global boolean. Per-severity auto-fix control is out of scope (can be added later without breaking the format).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The config file MUST support an `agents` section with boolean toggles for each review agent: correctness, architecture, security, production, test_quality, goal_alignment.
- **FR-002**: The config file MUST support a `severity` section with: `min_confidence` (integer 0-100), `request_changes_severities` (list of severity levels that trigger REQUEST_CHANGES), `auto_fix` (global boolean).
- **FR-003**: The config file MUST support an `output` section with: `dir` (output directory path), `verbosity` (quiet/normal/verbose), `findings_filename` (string).
- **FR-004**: The config file MUST support a `pr_posting` section with: `enabled` (boolean), `auto_detect_pr` (boolean), `max_inline_comments` (integer), `voice_profile` (string), `recovery_dir` (string).
- **FR-004a**: The config file MUST support a `test` section with: `command` (string, auto-detected if empty), `timeout_seconds` (integer, default 300).
- **FR-004b**: The config file structure MUST use nested sections (`output.dir`, `test.command`) rather than flat keys (`output_dir`, `test_command`). The existing `config-template.yml` MUST be updated to the nested format.
- **FR-005**: The `--config <path>` flag MUST be accepted by both the review and triage commands.
- **FR-006**: The `--config` file MUST be the highest priority source in the resolution chain (below CLI flags).
- **FR-007**: When `--config` points to a nonexistent file, the command MUST report an error and stop.
- **FR-008**: The `--profile <name>` flag MUST load a preset config from shipped profile files.
- **FR-009**: Three profiles MUST be shipped: `ci` (no interactive prompts, all agents, verbose), `thorough` (all agents, all tools, strict thresholds, 5 fix rounds), `quick` (correctness + security only, no external tools, 1 fix round).
- **FR-010**: When `--profile` references a nonexistent profile, the command MUST list available profiles and stop.
- **FR-011**: The resolution chain MUST be: CLI flags > --config > --profile > project config > user config > defaults.
- **FR-012**: The init skill MUST auto-detect: installed external tool CLIs, test command, platform (from git remote).
- **FR-013**: The init skill MUST warn when an external tool CLI is installed but not authenticated.
- **FR-014**: The init skill in smart-defaults mode MUST show the generated config and ask for confirmation before writing.
- **FR-015**: The init skill with `--interactive` MUST walk through each config section with questions.
- **FR-016**: The init skill MUST merge with existing config when `.cc-review/config.yml` already exists (preserve user customizations for keys not being updated).
- **FR-017**: Unknown config keys MUST be silently ignored.
- **FR-018**: Invalid config values MUST fall back to defaults with a warning.
- **FR-019**: The existing `resolve_config` function MUST be updated to support the full resolution chain.
- **FR-020**: Config format MUST remain YAML.
- **FR-021**: The config file MUST support an `external_tools` section with boolean toggles for each external tool (coderabbit, copilot, codex). New external tools can be added as new keys without modifying the resolution chain or init skill.
- **FR-022**: The resolution chain MUST perform per-key deep merge: each key is resolved independently from the highest-priority source that defines it. Nested sections are merged recursively (not replaced as whole blocks).

### Key Entities

- **Config File**: A YAML file containing review settings organized into sections (agents, severity, pr_posting, output, external_tools, triage, test). Located at `.cc-review/config.yml` (project), `~/.cc-review/config.yml` (user), or a custom path via `--config`.
- **Profile**: A shipped preset config file under `review/config/profiles/<name>.yml`. Provides a pre-configured set of options for common workflows (ci, thorough, quick).
- **Resolution Chain**: The ordered priority list determining which config source wins for each key. Higher-priority sources override lower-priority ones on a per-key basis.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can configure all review agents individually without CLI flags (via config file).
- **SC-002**: CI pipelines can run cc-review with a single `--config` or `--profile` flag, requiring no project-local config file.
- **SC-003**: The init skill generates a valid, working config file in under 30 seconds without manual YAML editing.
- **SC-004**: The resolution chain produces deterministic results: the same inputs always produce the same effective configuration.
- **SC-005**: Existing users with no config file experience zero behavior change (backward compatibility).
- **SC-006**: A new external tool can be added to the config without modifying the resolution chain or init skill (forward compatibility via the external_tools section).

## Out of Scope

- Environment variable interpolation in config values.
- Per-severity `auto_fix` control (the `auto_fix` setting is a global boolean only).
- Per-agent CLI flags (e.g., `--no-test-quality`). Agent selection is config-only; existing external tool flags (`--no-coderabbit`, etc.) remain unchanged.
- Config file format migration tooling. The restructuring from flat keys to nested sections (e.g., `output_dir` to `output.dir`) is a breaking change to the template; the old flat format is not supported.

## Assumptions

- The config file format is YAML, consistent with the existing `config-template.yml`.
- Profile files are read-only shipped assets, not user-editable (users who want custom presets create their own config files).
- The init skill runs within a Claude Code session (it uses interactive prompts via the harness).
- The `--config` flag accepts absolute or relative paths.
- Environment variable interpolation in config values is out of scope for this feature.
