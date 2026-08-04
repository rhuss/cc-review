# Data Model: Configuration System

## Entities

### Config File (YAML structure)

```yaml
agents:
  correctness: true
  architecture: true
  security: true
  production: true
  test_quality: true
  goal_alignment: true

external_tools:
  coderabbit: true
  copilot: false
  codex: true

severity:
  min_confidence: 70          # 0-100, minimum to report (50 for Critical)
  request_changes_severities:  # severities that trigger REQUEST_CHANGES
    - Critical
    - Important
  auto_fix: true              # global boolean

pr_posting:
  enabled: true
  auto_detect_pr: false
  max_inline_comments: 50
  voice_profile: "reviewer"
  recovery_dir: ".cc-review"

output:
  dir: "."
  verbosity: "normal"         # quiet | normal | verbose
  findings_filename: "review-findings.md"

test:
  command: ""                 # auto-detect if empty
  timeout_seconds: 300

triage:
  bot_profiles:
    - login: "coderabbitai[bot]"
      self_resolves: true
      auto_resolve: false
    - login: "copilot[bot]"
      self_resolves: false
      auto_resolve: true
  codecov:
    patch_threshold: 80
    auto_remediate: true

max_fix_rounds: 3
```

### Resolution Chain

```
CLI Flags          (highest priority)
  ↓
--config <path>    (explicit override file)
  ↓
--profile <name>   (shipped preset)
  ↓
Project config     (.cc-review/config.yml)
  ↓
User config        (~/.cc-review/config.yml)
  ↓
Built-in defaults  (review/config/config-template.yml)
```

Merge semantics: per-key deep merge. Each key resolves from the highest-priority source that defines it. Nested sections are merged recursively.

### Profile Presets

| Profile | Agents | External Tools | Fix Rounds | Verbosity | Notes |
|---------|--------|---------------|------------|-----------|-------|
| ci | all enabled | all enabled | 3 | verbose | No interactive prompts |
| thorough | all enabled | all enabled | 5 | normal | Strict thresholds |
| quick | correctness, security | none | 1 | quiet | Minimal review |

## Relationships

```
Init Skill
  ├── runs detect-tools.sh
  │     ├── detects external tool CLIs + auth
  │     ├── detects test command
  │     └── detects platform
  ├── generates Config File (YAML)
  └── merges with existing Config File (if present)

Review/Triage Commands
  ├── parse --config and --profile flags
  ├── call resolve_config_init (builds merged config)
  │     ├── loads defaults (config-template.yml)
  │     ├── loads user config (~/.cc-review/config.yml)
  │     ├── loads project config (.cc-review/config.yml)
  │     ├── loads profile (profiles/<name>.yml)
  │     ├── loads --config file
  │     └── deep merges all layers
  └── call resolve_config <key> for each setting
```
