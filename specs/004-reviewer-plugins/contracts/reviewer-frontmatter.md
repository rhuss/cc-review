# Contract: Reviewer Frontmatter

The machine-readable version of this contract is `review/core/schemas/reviewer.schema.json`. Discovery enforces it with a jq validator whose lists (kinds, dedup modes, context blocks, output formats, delimited fields, placeholders, reserved names, patterns) are defined once in `discover-reviewers.sh`; `tests/run.sh` checks that the schema agrees with them. This document is the human-readable reference for plugin authors and the test fixtures.

## Prompt reviewer (file form)

```markdown
---
name: accessibility
display_name: "Accessibility"
kind: prompt
category: accessibility
enabled: true
requires: []
dedup: cross-category
---
You are the ACCESSIBILITY REVIEW AGENT.

YOUR ROLE: ...
```

## Prompt reviewer (directory form with references and context)

`reviewers/gator/reviewer.md`:

```markdown
---
name: gator
display_name: "Gator (Principal Engineer)"
kind: prompt
category: gator
enabled: false
severity_map:
  Critical: Critical
  Warning: Important
  Suggestion: Minor
references:
  - references/findings-contract.md
---
You are a principal engineer reviewing code ...
```

`reviewers/goal-alignment.md` (bundled):

```markdown
---
name: goal-alignment
display_name: "Goal Alignment"
kind: prompt
category: goal-alignment
requires: [pr]
context: [goals]
dedup: isolated
---
You are the GOAL ALIGNMENT REVIEW AGENT. ...
```

## Command reviewer

```markdown
---
name: coderabbit
display_name: "CodeRabbit"
kind: command
category: external
enabled: true
detect: "command -v coderabbit"
auth_check: "coderabbit auth status"
invoke: "coderabbit review --agent --base {base_branch} --committed"
timeout_seconds: 540
severity_map:
  critical: Critical
  major: Important
  minor: Minor
  info: Notable
  trivial: Notable
  none: Notable
output:
  format: parser
  parser: parse.sh
---
Parsing notes: `coderabbit review --agent` prints JSON lines. `parse.sh` keeps
the `finding` objects and converts them to cc-review's json finding shape.
Default confidence 75.
```

This reviewer ships in directory form (`coderabbit/reviewer.md` plus `coderabbit/parse.sh`). A `delimited` example looks like this:

```yaml
output:
  format: delimited
  delimiter: "### FINDING"
  fields:
    file: "File"
    line: "Line"
    severity: "Severity"
    description: "Description"
    rationale: "Rationale"
```

## Validation rules (enforced by discovery)

| Rule | Status on failure |
|------|-------------------|
| Frontmatter present and parseable as YAML | invalid: "frontmatter missing or malformed" |
| `name` is a YAML string (not a number or boolean such as `007`, `1e3`, `0x1f`) | invalid: "name must be a quoted string" |
| `name` present, matches `^[a-z0-9][a-z0-9-]*$` | invalid: "invalid name" |
| `name` equals basename or directory name | invalid: "name does not match file or directory name" |
| `name` not reserved | invalid: "reserved name" |
| `kind` is `prompt` or `command` | invalid: "unknown kind" |
| `display_name` is a string | invalid: "invalid display_name" |
| `category` is a YAML string | invalid: "category must be a quoted string" |
| `category` matches `^[a-z0-9-]+$` | invalid: "invalid category" |
| `enabled` is a boolean | invalid: "invalid enabled value" |
| `requires` is a list of strings | invalid: "invalid requires list" |
| `severity_map` is a map | invalid: "invalid severity_map" |
| `severity_map` values in the cc-review set | invalid: "invalid severity_map value: <v>" |
| `dedup` in `cross-category`, `isolated` | invalid: "unknown dedup mode" |
| prompt: body non-empty after frontmatter | invalid: "empty prompt body" |
| prompt: `references` is a list of strings | invalid: "invalid references list" |
| prompt: `context` is a list of strings | invalid: "invalid context list" |
| prompt: each `context` entry is `goals` | invalid: "unknown context block: <x>" |
| command: `detect`, `invoke`, `output.format` present | invalid: "command reviewer missing <field>" |
| command: `auth_check` is a string | invalid: "invalid auth_check" |
| command: `invoke` placeholders subset of allowed | invalid: "unknown placeholder {x}" |
| command: `output.format` in `json`, `delimited`, `parser`; required sub-fields present | invalid: "incomplete output declaration" |
| command: `timeout_seconds` positive integer | invalid: "invalid timeout_seconds" |
| prompt: each `references` entry relative, no `..`, not absolute, exists inside the plugin dir | invalid: "reference not found or outside plugin directory: <path>" |
| command: `output.parser` relative, inside plugin dir, executable | invalid: "parser not found or not executable" |
| unknown fields | accepted; verbose note |

Rules are checked in this order; the first failing rule gives the reason.

## Precondition evaluation (after validation)

| Condition | Status |
|-----------|--------|
| project layer: a file of the reviewer is in `--changed-files` | ignored; lower layer used, else skipped: "changed in the reviewed change" |
| project layer, command: no matching trust entry | skipped: "untrusted project command reviewer (trust with: <name> <sha256>)" |
| `requires` contains `pr` and no PR context | skipped: "requires: pr" |
| `requires` contains `spec` and no `--spec` | skipped: "requires: spec" |
| `requires` contains `binary:<x>` and `<x>` not on PATH | skipped: "requires: binary:<x>" |
| `requires` contains unknown token | skipped: "unknown precondition: <token>" |
| command: `invoke` contains `{pr_number}` and no PR | skipped: "requires: pr" |
| command: `detect` exits non-zero | skipped: "not available" or "not available: <last stderr line>" |
| command: `detect` exceeds the 15 second bound | skipped: "detection timed out" |
| command: `auth_check` present and exits non-zero | skipped: "not authenticated" or "not authenticated: <last stderr line>" |
| command: `auth_check` exceeds the 15 second bound | skipped: "authentication check timed out" |

`detect` and `auth_check` run in discovery only without `--skip-detection` (init). The review command passes `--skip-detection` and runs them with `apply_detection` after config enablement and CLI selection, so only enabled command reviewers are probed.
