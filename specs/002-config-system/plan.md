# Implementation Plan: Configuration System

**Branch**: `002-config-system` | **Date**: 2026-08-04 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-config-system/spec.md`

## Summary

Expand cc-review's configuration system with new sections (agents, severity, output, test), a multi-layer resolution chain (CLI > --config > --profile > project > user > defaults), shipped profile presets, and an interactive init skill. Restructure the config template from flat keys to nested sections.

## Technical Context

**Language/Version**: Bash (POSIX-compatible), Markdown, `jq`, `yq`

**Primary Dependencies**: `yq` (YAML processing), `jq` (JSON processing), `gh` CLI

**Storage**: YAML config files (`.cc-review/config.yml`), shipped profile YAMLs

**Testing**: Manual integration testing

**Target Platform**: Any system with Bash, yq, jq

**Project Type**: CLI plugin (prompt-based)

**Constraints**: Backward compatibility with existing resolve_config callers

## Global Constraints

- All scripts MUST be POSIX-compatible Bash
- `yq` is required for all YAML merging and reading
- Config template restructuring from flat to nested is a breaking change (documented in Out of Scope)
- Resolution chain must be deterministic: same inputs always produce same output
- `resolve_config` function signature must remain backward compatible for existing callers

## Project Structure

### Source Code (repository root)

```text
review/
├── core/
│   ├── commands/
│   │   ├── review.md            # MODIFIED: add --config, --profile flag parsing
│   │   ├── triage.md            # MODIFIED: add --config, --profile flag parsing
│   │   └── init.md              # NEW: init skill command definition
│   ├── scripts/
│   │   ├── resolve-config.sh    # MODIFIED: full resolution chain with deep merge
│   │   └── detect-tools.sh      # NEW: tool detection for init skill
│   └── templates/
│       └── reviewer-voice.md    # (existing, unchanged)
├── config/
│   ├── config-template.yml      # MODIFIED: restructured to nested sections
│   └── profiles/
│       ├── ci.yml               # NEW: CI profile preset
│       ├── thorough.yml         # NEW: thorough review preset
│       └── quick.yml            # NEW: quick review preset
├── skills/
│   ├── review/SKILL.md          # MODIFIED: pass --config, --profile
│   ├── triage/SKILL.md          # MODIFIED: pass --config, --profile
│   └── init/SKILL.md            # NEW: init skill shim
```

**Structure Decision**: New files are `init.md` (command), `detect-tools.sh` (script), 3 profile YAMLs, and `init/SKILL.md` (shim). The rest are modifications to existing files.
