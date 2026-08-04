# Research: Configuration System

## R-001: YAML Deep Merge with yq

**Decision**: Use `yq` with the `*` (merge) operator for recursive deep merge of config layers. Process layers from lowest to highest priority, merging each layer on top.

**Rationale**: `yq` natively supports YAML merge with `yq eval-all '. as $item ireduce ({}; . * $item)'` which performs recursive key-level merge. This avoids writing custom merge logic in Bash.

**Alternatives considered**:
- Custom Bash merge function: Complex, error-prone for nested structures.
- `jq` with YAML conversion: Extra step to convert YAML to JSON and back. Loses YAML comments.

**Key implementation detail**:
```bash
# Merge layers (lowest priority first, each overrides the previous)
yq eval-all '. as $item ireduce ({}; . * $item)' \
  defaults.yml user.yml project.yml profile.yml config.yml
```

CLI flag overrides are applied after the YAML merge as individual key sets.

## R-002: Tool Detection Patterns

**Decision**: Use `command -v` for binary detection and tool-specific auth check commands.

**Detection matrix**:

| Tool | Binary Check | Auth Check |
|------|-------------|------------|
| CodeRabbit | `command -v coderabbit` | `coderabbit auth status 2>&1` |
| Copilot | `command -v copilot` | (none, auth through GitHub CLI) |
| Codex | `command -v codex` | `codex --version 2>&1` |

**Test command detection** (priority order):
1. `grep -q '^test:' Makefile` -> `make test`
2. `jq -e '.scripts.test' package.json` -> `npm test`
3. `[ -f go.mod ]` -> `go test ./...`
4. `[ -f pyproject.toml ] || [ -f setup.py ]` -> `pytest`
5. `[ -f Cargo.toml ]` -> `cargo test`

**Platform detection**: Parse `git remote get-url origin` for github.com or gitlab.com.

## R-003: Profile File Format

**Decision**: Profile files are complete config files (not partial overrides). They specify all keys they intend to set, and unspecified keys fall through to lower-priority layers.

**Rationale**: Complete files are simpler to read and maintain. A user looking at `ci.yml` sees exactly what CI mode does without needing to mentally merge it with defaults.

## R-004: Init Merge Strategy

**Decision**: When `.cc-review/config.yml` already exists, init reads it, deep-merges newly detected values (only for keys the user hasn't customized), and writes the result.

**Rationale**: Users who have already customized their config should not lose their settings when re-running init (e.g., after installing a new external tool).

**Implementation**: Read existing config, read detected config, merge with existing as higher priority (preserves user values), then write. New keys from detection are added; existing keys are preserved.

## R-005: resolve_config Refactor

**Decision**: Refactor `resolve_config` to accept `--config` and `--profile` arguments, build the full layer stack, and merge them. The function signature changes from `resolve_config <key> <default>` to supporting an initialization step that builds the merged config once, then individual key lookups read from the merged result.

**Implementation approach**:
1. `resolve_config_init` builds merged config file (once per command invocation)
2. `resolve_config` reads from the merged file (unchanged signature for callers)
3. The merged file is written to a temp location and cleaned up on exit
