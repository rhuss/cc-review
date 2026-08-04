# Brainstorm: Configuration System

**Date:** 2026-08-04
**Status:** active

## Problem Framing

The cc-review configuration is minimal: a flat YAML file (`config-template.yml`) with external tool toggles, test command, triage bot profiles, and basic PR posting settings. The `resolve_config` function reads from `.cc-review/config.yml` (project) or `~/.cc-review/config.yml` (user), with CLI flags overriding.

Users need more control: which review agents to run, PR posting defaults, severity thresholds, output format. CI/automation users need a way to point to a config file without copying it into the repo. And setting up the config should not require manually editing YAML; an interactive init skill should detect installed tools and generate sensible defaults.

Seeded from inbox item `platform-abstraction`: the extensibility points for external tools are scaffolded but not configurable end-to-end.

## Approaches Considered

### A: Flat Config Expansion + Shipped Profiles

Expand the existing `config-template.yml` with new sections. Ship preset profile files (`ci.yml`, `thorough.yml`, `quick.yml`) under `review/config/profiles/`. Add `--config <path>` and `--profile <name>` flags. Build an init skill that auto-detects tools and writes the config.

- Pros: Simple, backward-compatible, familiar YAML. `resolve_config` barely changes. CI-friendly with profiles. Low implementation complexity.
- Cons: Flat structure can get unwieldy as config grows. No validation beyond `yq` parsing.

### B: Structured Config with User-Defined Profiles

Add a `profiles` concept with named presets and user-defined profiles in the same config file. Profile inheritance and override rules.

- Pros: Great for CI, supports workflow presets. Users don't repeat settings.
- Cons: More complex config format. Profile inheritance adds mental overhead. More code.

### C: Schema-Validated Config with Migrations

Add JSON Schema for the config format. Init generates a validated config. Versioned config with migration tooling.

- Pros: Catches typos early. Self-documenting. Future-proof.
- Cons: Most complex. JSON Schema is another artifact to maintain. Overkill for a Bash/Markdown project.

## Decision

**Chosen: Approach A + profiles element from B (shipped presets only, no user-defined profiles)**

Keep the flat YAML structure. Add `--config` and `--profile` flags. Ship 3 preset profiles (ci, thorough, quick). Build an init skill with smart-defaults and interactive modes. Resolution chain: CLI flags > --config > --profile > project > user > defaults.

## Key Requirements

### Expanded Config Sections

- **agents**: Enable/disable individual review agents (correctness, architecture, security, production, test-quality, goal-alignment). Default: all enabled.
- **pr_posting**: Auto-detect PR from current branch (opt-in), default event type behavior, max inline comments, voice profile, recovery directory.
- **severity**: Minimum confidence to report (default 70, 50 for Critical), which severities trigger REQUEST_CHANGES (default: Critical + Important), auto-fix enabled per severity level.
- **output**: Report format (markdown), output directory, verbosity level (quiet/normal/verbose), findings filename.

### CLI Flags

- `--config <path>`: Point to a specific config file. Highest priority in the resolution chain (below CLI flags). Works with `claude -p` for CI invocation.
- `--profile <name>`: Load a shipped preset from `review/config/profiles/<name>.yml`. Sits between --config and project config in resolution priority.

### Resolution Chain (highest to lowest priority)

1. CLI flags (e.g., `--no-coderabbit`, `--no-fix`)
2. `--config <path>` file (explicit override)
3. `--profile <name>` preset file
4. Project config (`.cc-review/config.yml`)
5. User config (`~/.cc-review/config.yml`)
6. Built-in defaults (`review/config/config-template.yml`)

### Shipped Profiles

- **ci**: Disable interactive prompts, skip PR posting (local report only), all agents enabled, verbose output for logs.
- **thorough**: All agents enabled, all external tools enabled, max confidence thresholds, 5 fix rounds.
- **quick**: Only correctness + security agents, no external tools, 1 fix round, minimal output.

### Init Skill (`/cc-review:init`)

- **Smart-defaults mode** (default): Auto-detect installed tools (`coderabbit`, `codex`, `copilot` CLIs), detect test command (Makefile, package.json, go.mod, pyproject.toml), detect platform (GitHub/GitLab from git remote). Show the generated config and ask for confirmation. Write `.cc-review/config.yml`.
- **Interactive mode** (`--interactive`): Walk through each config section with questions. Explain each option. Support re-running to update existing config (merge, don't overwrite).
- Both modes: Detect preconditions for external tools (e.g., `coderabbit auth status`) and warn if not authenticated.

### CI/Automation Support

- `claude -p "cc-review:review --config /path/to/config.yml"` works for headless invocation.
- The `ci` profile disables all interactive prompts and outputs machine-parseable results.
- Config file can be stored in the CI pipeline repo and referenced via `--config`.

## Open Questions

- Should `--profile` and `--config` be mutually exclusive, or should `--config` override `--profile` values?
- Should the init skill support generating a GitHub Actions workflow file that uses cc-review?
- Should the config support environment variable interpolation (e.g., `$CC_REVIEW_TOKEN`) for CI secrets?
- How should config errors be reported: fail fast with all errors, or warn and use defaults for invalid keys?
