# Data Model: Pluggable Reviewers

**Feature**: 004-reviewer-plugins | **Date**: 2026-10-13

## Reviewer Plugin (on disk)

A reviewer is one of:

- **File form**: `<layer-dir>/<name>.md`
- **Directory form**: `<layer-dir>/<name>/reviewer.md` plus arbitrary sibling files

Both contain YAML frontmatter followed by a markdown body.

### Frontmatter fields

| Field | Type | Required | Default | Applies to | Rules |
|-------|------|----------|---------|------------|-------|
| `name` | string | yes | | both | `^[a-z0-9][a-z0-9-]*$`; must equal file basename or directory name; not in reserved set; must be a YAML string (quote `"007"`) |
| `kind` | enum | yes | | both | `prompt` or `command` |
| `display_name` | string | no | `name` | both | shown in console and report |
| `category` | string | no | `name` | both | `^[a-z0-9-]+$`; must be a YAML string; written to each finding |
| `enabled` | boolean | no | `true` | both | default when config has no `reviewers.<name>` key |
| `requires` | list of string | no | `[]` | both | tokens: `pr`, `spec`, `binary:<name>`; unknown token = unsatisfied |
| `severity_map` | map string to enum | no | identity | both | values must be `Critical`, `Important`, `Minor`, `Notable` |
| `dedup` | enum | no | `cross-category` | both | `cross-category` or `isolated` |
| `references` | list of string | no | `[]` | prompt | relative paths inside plugin dir; no `..`, not absolute; must exist |
| `context` | list of string | no | `[]` | prompt | only `goals` supported |
| `detect` | string (shell) | yes for command | | command | exit 0 means available |
| `auth_check` | string (shell) | no | | command | exit 0 means authenticated |
| `invoke` | string (template) | yes for command | | command | placeholders `{base_branch}`, `{files}`, `{pr_number}` only |
| `timeout_seconds` | integer | no | `120` | command | positive integer |
| `output.format` | enum | yes for command | | command | `json`, `delimited`, `parser` |
| `output.delimiter` | string | yes if delimited | | command | block separator |
| `output.fields` | map | yes if delimited | | command | finding field to label; must include `file`, `line`, `severity`, `description` |
| `output.parser` | string | yes if parser | | command | relative path inside plugin dir; executable |

Unknown fields are ignored with a verbose-level note.

### Body

- `kind: prompt`: the reviewer prompt. Must be non-empty. Must not reference harness tools (convention, not machine-checked).
- `kind: command`: parsing notes for the orchestrator. May be empty.

### Reserved names

`external`, `fix`, `meta-review`, `only`, `sequential`, `parallel`, `pr`, `spec`, `hints`, `output`, `config`, `profile`, `max-rounds`.

## Discovery Layer

| Layer | Path | Precedence |
|-------|------|-----------|
| project | `<git root>/.cc-review/reviewers/` | highest |
| user | `~/.cc-review/reviewers/` | middle |
| bundled | `<core>/reviewers/` | lowest |

Resolution: scan bundled, user, project in that order; valid entries overwrite by `name`; invalid entries are reported and never overwrite. A project entry whose files are in the review's changed-file list never overwrites either (the lower layer runs, or the entry is skipped), and a project `kind: command` entry without a matching trust entry is skipped before any of its commands run.

## Trust File

| Field | Description |
|-------|-------------|
| path | `~/.cc-review/trusted-reviewers` (user level only; a file inside the project is ignored) |
| line | `<name> <sha256>`; `#` comments and blank lines ignored |
| sha256 | SHA-256 of the hex SHA-256 digests of the reviewer file and the declared parser, one per line |

## Discovered Reviewer (runtime record)

Produced by `discover-reviewers.sh` for every reviewer file found, valid or not. See `contracts/discovery-output.md` for the JSON shape.

| Field | Description |
|-------|-------------|
| `name`, `kind`, `display_name`, `category`, `enabled`, `requires`, `severity_map`, `dedup` | from frontmatter with defaults applied |
| `layer` | `project`, `user`, `bundled` |
| `path` | absolute path to the reviewer markdown file |
| `dir` | absolute path to the plugin directory (file form: the layer dir; directory form: the reviewer's directory) |
| `body_file` | path to a file containing the body with frontmatter stripped, inside the caller's `--body-dir` (see the contract) |
| `references` | resolved absolute paths (prompt kind) |
| `context` | requested blocks (prompt kind) |
| `command` | object with `detect`, `auth_check`, `invoke`, `timeout_seconds`, `output` (command kind) |
| `overrides` | lower layer name this entry replaced, or null |
| `status` | `ready`, `disabled`, `skipped`, `invalid`, `failed` (defined once in `contracts/discovery-output.md`, "Status values") |
| `reason` | human-readable reason when status is not `ready` |

### Status lifecycle

```text
file found
  -> invalid    frontmatter missing/malformed, bad name, reserved name, missing body (prompt),
                missing invoke/output (command), bad reference path, bad severity_map value
  -> skipped    changed in the reviewed change | untrusted project command reviewer |
                precondition unsatisfied | {pr_number} used without PR (requires: pr)
  -> ready
       -> disabled   enabled=false after config (apply_config_enablement) and CLI
                     (apply_cli_selection) resolution
       -> skipped    detect failed (not available[: detail]) | auth_check failed
                     (not authenticated[: detail]) | probe timed out (apply_detection,
                     only for command reviewers still ready)
       -> failed     dispatch failed (subagent error, timeout, non-zero exit, parse error)
```

Config and CLI resolution (`reviewers.<name>`, `--no-<name>`, `--only`, `--external`, `--no-external`) is applied by the orchestrator after discovery and can move a reviewer between `ready` and `disabled`; it never changes `invalid` or `skipped`.

### Per-run outcome (orchestrator)

After dispatch each `ready` reviewer gets an outcome: `completed` (with found/fixed/remaining counts) or `failed` (reason: subagent error, timeout, non-zero exit, parse error). Console summary and report list every discovered reviewer with its status or outcome.

## Finding (existing, modified)

- `category`: was an enum; becomes a string matching `^[a-z0-9-]+$`. Existing values (`correctness`, `architecture`, `security`, `production-readiness`, `test-quality`, `goal-alignment`, `external`, `regression`) remain the documented conventions.
- `source_agent`: unchanged; populated from reviewer `name`.
- Severity translation: `severity_map[native]` if present; else pass through if native is already a cc-review severity; else drop with warning.

## Positive Observation (new, transient)

A bullet string citing a code location, collected from any prompt reviewer's final output under the heading `Positive observations:`. Aggregated into the PR review summary "What Went Well" section. Not persisted in findings.

## Configuration (modified)

```yaml
reviewers:
  test-quality: false     # any discovered reviewer name
  gator: true
```

The config template sets no `reviewers.<name>` key; the bundled defaults (all enabled except `copilot` and `gator`) live in each reviewer's `enabled` frontmatter, so an override's own `enabled` applies too. The profiles set an explicit key for every bundled reviewer.

Legacy keys `agents.<underscore_name>` and `external_tools.<name>` map to `reviewers.<hyphen-name>` with a deprecation warning when the new key is absent. Profiles use only `reviewers.*`; the template carries no legacy keys.
