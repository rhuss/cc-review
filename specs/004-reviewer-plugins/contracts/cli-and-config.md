# Contract: CLI Flags and Configuration

## Review command flags

| Flag | Behavior |
|------|----------|
| `--no-<name>` | Disable discovered reviewer `<name>`. Unknown `<name>` is an error listing discovered names. For an invalid reviewer it prints a warning and the review continues. |
| `--only <a,b,...>` | Dispatch only the listed reviewers. Unknown or invalid name is an error. Overrides config `enabled: false`, never overrides `skipped` or `invalid`. |
| `--only ... --no-x` | `x` is removed from the `--only` set. Empty result is an error: "no reviewers remain after --only/--no- selection". |
| `--only <command reviewers> --no-external` | Error: "no reviewers remain: every --only reviewer is a command reviewer and --no-external disables them". |
| `--no-external` | Disable all `kind: command` reviewers. |
| `--external` | Enable all `kind: command` reviewers (they may still be `skipped` by detection). |
| `--sequential` | Unchanged. |
| `--parallel` | Accepted, no effect: parallel dispatch is the default. |
| `--no-coderabbit`, `--no-copilot`, `--no-codex` | Work because these are reviewer names; no special handling. |

Removed from documentation (still accepted as derived flags): nothing else changes. The `argument-hint` in all shims becomes:

```
[--pr <number>] [--spec <path>] [--hints <path>] [--output <path>] [--config <path>] [--profile <name>] [--no-fix] [--max-rounds <n>] [--no-external] [--external] [--no-<reviewer>] [--only <reviewer,...>] [--no-meta-review] [--sequential] [--parallel]
```

## Configuration keys

```yaml
reviewers:
  <name>: true | false      # default from the reviewer's `enabled` frontmatter
```

Resolution order unchanged: CLI flags > `--config` > `--profile` > project config > user config > template defaults > reviewer `enabled` frontmatter. The template sets no `reviewers.<name>` key (it carries a commented example), so without a config or profile key the frontmatter `enabled` of the effective reviewer applies, including a user or project override's own value. The profiles set an explicit key for every bundled reviewer.

`resolve_config_init --config <path> --profile <name>` treats a value of `-` as "not provided", so commands always pass both flags (`"${CONFIG_FLAG:--}"`). `resolve_config_reviewers_json` prints the merged `reviewers` map as JSON for `apply_config_enablement`. `resolve_config_migrate_legacy_keys <file>` requires its file argument; it migrates one layer (or a copy), never the merged config.

## Trust file

`~/.cc-review/trusted-reviewers` lists the project-layer command reviewers the user allows to run, one `<name> <sha256>` per line (`#` comments and blank lines ignored). The review command and init pass it to discovery with `--trust-file`; it is never read from the project. See `discovery-output.md` for the digest.

## Legacy key mapping (deprecated, at least one release)

| Legacy key | Maps to | Warning |
|------------|---------|---------|
| `agents.correctness` | `reviewers.correctness` | `Warning: config key agents.correctness is deprecated, use reviewers.correctness` |
| `agents.architecture` | `reviewers.architecture` | same pattern |
| `agents.security` | `reviewers.security` | |
| `agents.production` | `reviewers.production` | |
| `agents.test_quality` | `reviewers.test-quality` | |
| `agents.goal_alignment` | `reviewers.goal-alignment` | |
| `external_tools.coderabbit` | `reviewers.coderabbit` | |
| `external_tools.copilot` | `reviewers.copilot` | |
| `external_tools.codex` | `reviewers.codex` | |

Generic rule: any key under `agents.` or `external_tools.` maps to `reviewers.<key with _ replaced by ->`. The mapping applies only when the new key is absent in the merged config. One warning per legacy key, printed once per run to stderr.

## Hyphenated keys in resolve-config.sh

`resolve_config "reviewers.test-quality"` and `resolve_config_apply_cli_overrides "reviewers.test-quality=false"` must work. Internally, dotted keys are converted to `yq` bracket paths: `.["reviewers"]["test-quality"]`. The key validation regex becomes `^[a-zA-Z_][a-zA-Z0-9_.-]*$`.

## Type validation

`resolve_config_validate_types` validates every key under `reviewers.*` as boolean (invalid values fall back to the reviewer's frontmatter default with a warning), replacing the hard-coded `agents.*` / `external_tools.*` list.

## Init output

`/cc-review:init` prints, after tool detection:

```
Discovered reviewers:
| Name           | Layer   | Kind    | Enabled | Preconditions           |
|----------------|---------|---------|---------|-------------------------|
| correctness    | bundled | prompt  | true    | ok                      |
| goal-alignment | bundled | prompt  | true    | requires: pr (not now)  |
| coderabbit     | bundled | command | true    | not available           |
| gator          | bundled | prompt  | false   | ok                      |
| accessibility  | project | prompt  | true    | ok                      |
```

and generates a `reviewers:` section listing every discovered reviewer with its effective enabled value. Untrusted project command reviewers are listed with the trust line that would allow their current version; init never writes the trust file itself. A command reviewer whose check timed out is shown as `unknown (detection timed out)`, never as installed.
