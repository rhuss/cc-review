# Configuration and finding schema

<!-- Sources:
cc-review:README.md:254-307
cc-review:review/config/config-template.yml:1-73
cc-review:review/core/scripts/resolve-config.sh:117-222
cc-review:review/core/schemas/finding.schema.json:40-127
cc-review:review/core/schemas/reviewer.schema.json:40-54
-->

This page lists the cc-review configuration keys, the order in which configuration layers resolve into one effective configuration, and the fields of a finding. For the command flags that can override these settings, see the [CLI reference](cli.md).

## Configuration file

cc-review reads YAML configuration from a project file at `.cc-review/config.yml` (which takes precedence) or a user file at `~/.cc-review/config.yml`. Each is copied from `review/config/config-template.yml`, and that same template is the built-in defaults layer of the merge.

```yaml
reviewers:                # one key per discovered reviewer; omit a key to use the reviewer's default
  correctness: true
  architecture: true
  security: true
  production: true
  test-quality: true
  goal-alignment: true
  coderabbit: true        # command reviewer (CodeRabbit CLI)
  copilot: false          # command reviewer (Copilot CLI)
  codex: true             # command reviewer (Codex CLI)
  greptile: false         # command reviewer (Greptile CLI, spends credits)
  gator: false            # opt-in principal-engineer reviewer

test:
  command: ""             # Auto-detected from Makefile/go.mod/package.json/pyproject.toml
  timeout_seconds: 300

triage:
  bot_profiles:
    - login: "coderabbitai[bot]"
      self_resolves: true
      auto_resolve: false
    - login: "copilot[bot]"
      self_resolves: false
      auto_resolve: true
    - login: "devin-ai-integration[bot]"
      self_resolves: false
      auto_resolve: true
    - login: "greptile-apps[bot]"
      self_resolves: false
      auto_resolve: true
  codecov:
    patch_threshold: 80
    auto_remediate: true

max_fix_rounds: 3
output:
  dir: "."
```

### Top-level keys

| Key | Shape | Purpose |
|-----|-------|---------|
| `reviewers` | map of booleans | One key per discovered reviewer. Omit a key to use that reviewer's own default. |
| `test` | map | The test command and timeout the fix loop runs. |
| `triage` | map | Bot handling and Codecov thresholds for triage. |
| `max_fix_rounds` | integer | Maximum fix loop rounds. |
| `output` | map | Where reports are written. |

### reviewers

Each key under `reviewers` enables (`true`) or disables (`false`) one discovered reviewer. The values below are those set in the config template.

| Reviewer key | Template value | Notes |
|--------------|----------------|-------|
| `correctness` | `true` | |
| `architecture` | `true` | |
| `security` | `true` | |
| `production` | `true` | |
| `test-quality` | `true` | |
| `goal-alignment` | `true` | |
| `coderabbit` | `true` | Command reviewer (CodeRabbit CLI) |
| `copilot` | `false` | Command reviewer (Copilot CLI) |
| `codex` | `true` | Command reviewer (Codex CLI) |
| `greptile` | `false` | Command reviewer (Greptile CLI, spends credits) |
| `gator` | `false` | Opt-in principal-engineer reviewer |

### test

| Key | Template value | Notes |
|-----|----------------|-------|
| `test.command` | `""` (empty) | Auto-detected from Makefile, go.mod, package.json, or pyproject.toml. |
| `test.timeout_seconds` | `300` | |

### triage

| Key | Template value | Notes |
|-----|----------------|-------|
| `triage.bot_profiles` | four entries | The template lists `coderabbitai[bot]` (`self_resolves: true`, `auto_resolve: false`), `copilot[bot]`, `devin-ai-integration[bot]`, and `greptile-apps[bot]` (each `self_resolves: false`, `auto_resolve: true`). |
| `triage.codecov.patch_threshold` | `80` | |
| `triage.codecov.auto_remediate` | `true` | |

### max_fix_rounds and output

| Key | Template value | Notes |
|-----|----------------|-------|
| `max_fix_rounds` | `3` | Maximum fix loop rounds. |
| `output.dir` | `"."` | Directory reports are written to. |

> [!NOTE]
> The legacy keys `agents.<name>` and `external_tools.<name>` are deprecated. They keep working for the migrated reviewers (`agents.test_quality` maps to `reviewers.test-quality`) and print a one-line warning that points to the new key.

## Resolution order

cc-review merges several configuration layers into one effective configuration. A higher layer overrides a lower one key by key. The order, from highest priority to lowest:

| Priority | Layer | Where it comes from |
|----------|-------|---------------------|
| 1 (highest) | CLI flags | Flags passed on the command line (see the [CLI reference](cli.md)). |
| 2 | `--config <path>` | An explicit configuration file. |
| 3 | `--profile <name>` | A bundled profile (`quick`, `thorough`, `ci`). |
| 4 | Project config | `.cc-review/config.yml` in the git root. |
| 5 | User config | `~/.cc-review/config.yml`. |
| 6 | Built-in defaults | `review/config/config-template.yml`. |
| 7 (lowest) | Reviewer default | The reviewer's own `enabled` value. |

> [!NOTE]
> The five file layers (built-in defaults, user config, project config, profile, and `--config` file) are assembled in `resolve-config.sh` and deep-merged from lowest to highest priority, so the explicit `--config` file wins among the files.

## Finding schema

Every reviewer reports findings in a common structure, validated against `finding.schema.json`. The gate and the meta-review act on a finding's `severity`, `confidence`, and `resolution`.

### Severity

A finding carries one severity, ordered `Critical > Important > Minor > Notable`.

| Severity | Rank |
|----------|------|
| `Critical` | highest |
| `Important` | |
| `Minor` | |
| `Notable` | lowest |

For how severity drives the pass or fix decision, see [Gate and fix](../how-it-works/gate-and-fix.md).

### Confidence

`confidence` is an integer from 0 to 100. The minimum to report a finding is 70, lowered to 50 for `Critical` findings.

### Resolution and round tracking

| Field | Values or type | Meaning |
|-------|----------------|---------|
| `resolution` | `pending`, `fixed`, `unresolved` | Current resolution status. |
| `round_found` | integer (minimum 1) | Fix loop round when the finding was discovered (1 is the initial review). |

### Meta-review fields

These fields are present only when the meta-review ran.

| Field | Values or type | Meaning |
|-------|----------------|---------|
| `verdict` | `confirmed`, `weak`, `false-positive` | The Skeptic's assessment of finding validity. |
| `verdict_reasoning` | string | The Skeptic's code-cited justification for non-confirmed verdicts. |
| `calibrated_severity` | `Critical`, `Important`, `Minor`, `Notable` | The Calibrator's adjusted severity (present only when changed). |
| `calibration_reasoning` | string | The Calibrator's justification for the severity adjustment. |

For how the two critics produce these, see [Meta-review](../how-it-works/meta-review.md).

## severity_map translation at merge

A reviewer plugin declares its metadata in frontmatter validated against `reviewer.schema.json`. When a command reviewer wraps an external tool whose severity vocabulary differs from cc-review's, the reviewer translates it with a `severity_map`.

`severity_map` is an object: each key is a native severity string, and each value is one of `Critical`, `Important`, `Minor`, or `Notable`. A native value not listed in the map passes through unchanged when it is already a cc-review severity; otherwise the finding is dropped with a warning.

> [!NOTE]
> These configuration keys and schema fields were verified against cc-review <!-- guide:attr cc-review-version -->1.4.0<!-- /guide:attr -->.
