# Contract: discover-reviewers.sh and reviewer-runtime.sh

## Invocation

```bash
review/core/scripts/discover-reviewers.sh \
  --core-dir <path-to-core> \
  [--project-dir <git-root>] \
  [--user-dir <path>]          # default: $HOME/.cc-review/reviewers
  [--pr <number>]              # "-" or omitted: no PR context
  [--spec <path>]              # "-" or omitted: no spec
  [--changed-files <file>]     # one repo-relative path per line; "-" or omitted: none
  [--trust-file <file>]        # default: $HOME/.cc-review/trusted-reviewers
  [--body-dir <dir>]           # existing empty directory for the body files
  [--skip-detection]           # do not run detect/auth_check (the review command, tests)
  [--verbose]
```

- stdout: one JSON array (see below). Always valid JSON, possibly `[]`.
- stderr: one line per warning, prefixed `Warning:`. Verbose notes prefixed `Note:` only with `--verbose` (or `CC_REVIEW_DISCOVER_VERBOSE=true`).
- exit code: 0 on success (even with invalid reviewers); 1 on usage error, a missing or wrong `jq`/`yq`/`awk`, a missing `--core-dir`, a missing `--changed-files` file, or a `--body-dir` that is not an existing empty directory.
- `-` means "not provided" for `--pr`, `--spec` and `--changed-files`, so callers always pass the flag and never need `${x:+--flag "$x"}` (which zsh keeps as one word).

The script does not read config. Enablement from config and CLI, and detection for the review command, are applied by the caller with the runtime helpers below.

## Project-layer guards

Project reviewers come from the checkout under review, so discovery treats them as untrusted input:

- **Changed in the reviewed change.** With `--changed-files`, a project reviewer is ignored for the run when its reviewer file, any file below its directory-form plugin directory, one of its references, or its parser appears in the list (paths relative to `--project-dir`). The next lower layer's valid reviewer of the same name is used and a warning names the ignored file; when there is none, the entry is listed with `status: skipped`, `reason: "changed in the reviewed change"`.
- **Untrusted command reviewers.** A project `kind: command` reviewer is `skipped` with `reason: "untrusted project command reviewer (trust with: <name> <sha256>)"` unless the trust file has a line `<name> <sha256>` for it. None of its `detect`, `auth_check`, `invoke` or parser commands run (and `--only` cannot change a `skipped` status). For a single-file reviewer the digest is the SHA-256 of the hex SHA-256 digest of the reviewer file. For a directory-form reviewer it is the SHA-256 over `<hex digest> <relative path>` lines for every regular file in the plugin directory, sorted by path, so a parser and any helper it sources are pinned together; editing, adding or removing any file changes it. A plugin directory that contains a symlink or a file name with a newline cannot be pinned and stays `skipped` with a reason saying so. Files outside the plugin directory that a command calls (for example a project script named in `invoke`) are not covered. Trust-file lines starting with `#` and blank lines are ignored. A trust file inside `--project-dir` is ignored with a warning. Bundled and user layers are trusted; project prompt reviewers need no trust.

The changed-file check runs before the trust check, so a changed project command reviewer is reported as changed.

## Output element

```json
{
  "name": "goal-alignment",
  "kind": "prompt",
  "display_name": "Goal Alignment",
  "category": "goal-alignment",
  "enabled": true,
  "requires": ["pr"],
  "severity_map": {},
  "dedup": "isolated",
  "layer": "bundled",
  "path": "/abs/review/core/reviewers/goal-alignment.md",
  "dir": "/abs/review/core/reviewers",
  "body_file": "/tmp/cc-review-run.XXXX/bodies/bundled-goal-alignment.md",
  "references": [],
  "context": ["goals"],
  "command": null,
  "overrides": null,
  "status": "skipped",
  "reason": "requires: pr"
}
```

Command reviewer element differences:

```json
{
  "kind": "command",
  "body_file": "/tmp/cc-review-run.XXXX/bodies/bundled-coderabbit.md",
  "references": [],
  "context": [],
  "command": {
    "detect": "command -v coderabbit",
    "auth_check": "coderabbit auth status",
    "invoke": "coderabbit review --agent --base {base_branch} --committed",
    "timeout_seconds": 540,
    "output": {"format": "parser", "parser": "parse.sh", "parser_path": "/abs/review/core/reviewers/coderabbit/parse.sh"}
  },
  "status": "ready",
  "reason": null
}
```

Invalid element (never dispatched, still listed so the console can show it):

```json
{
  "name": "broken",
  "kind": null,
  "layer": "project",
  "path": "/abs/.cc-review/reviewers/broken.md",
  "status": "invalid",
  "reason": "frontmatter missing or malformed"
}
```

## Status values

This is the one place the reviewer status set is defined. Every entry carries one `status`; `reason` is `null` only for `ready`.

| Status | Set by | Meaning | Typical reasons |
|--------|--------|---------|-----------------|
| `ready` | discovery | Dispatchable as far as the step that set it knows | (none) |
| `invalid` | discovery | Frontmatter or files violate the contract; never dispatched, never changed later | the validation reasons in `reviewer-frontmatter.md` |
| `skipped` | discovery, `apply_detection` | Valid but cannot run now; never re-enabled by config or CLI | `requires: <token>`, `unknown precondition: <token>`, `changed in the reviewed change`, `untrusted project command reviewer (trust with: <name> <sha256>)`, `not available[: <stderr line>]`, `not authenticated[: <stderr line>]`, `detection timed out`, `authentication check timed out` |
| `disabled` | `apply_config_enablement`, `apply_cli_selection` | Turned off by config or CLI; `--only` and `--external` can turn it back to `ready` | `disabled`, `not in --only`, `--no-external`, `--no-<name>` |
| `failed` | review command (dispatch) | Ran and failed; logged, never blocks the review | `subagent error`, `timeout`, `exit N: <last line>`, `parse error`, `unsafe invoke value` |

The review command applies them in this order: discovery (`--skip-detection`), `apply_config_enablement`, `apply_cli_selection`, `apply_detection`, dispatch. The console's `completed` is the outcome of a `ready` entry that ran without failing; it is not a status in the JSON.

## Ordering

Elements are sorted: `ready` (and later `disabled`) first in the order bundled prompt, bundled command, user, project (so the console table matches today's order for built-ins), then `skipped`, then `invalid`.

## Body files

`body_file` points to a file with the frontmatter stripped. With `--body-dir`, all body files are written to that directory, which must exist and be empty; discovery never removes it (on failure it only removes what it wrote), and the caller removes it at the end of the run. The review command passes `<run dir>/bodies` and init passes a `mktemp -d` directory, so neither derives the directory from `body_file`. Without `--body-dir`, the script creates a private directory with `mktemp -d "${TMPDIR:-/tmp}/cc-review-reviewers.XXXXXX"` and removes it on failure and when no body file remains. Callers must not tie removal to a shell `EXIT` trap, since the harness may run each command block in a new shell.

## Runtime helpers (reviewer-runtime.sh)

`reviewer-runtime.sh helper <function> [args...]` runs one helper under bash, whatever shell the caller uses (the review command uses this form). Sourcing the script (`source reviewer-runtime.sh`, bash only) defines the same functions; `discover-reviewers.sh` sources it.

- `run_with_timeout <seconds> <cmd...>`: uses `timeout`/`gtimeout` with `-k 5` (SIGKILL five seconds after SIGTERM; a build without `-k` falls back to the plain form) when available, then a `perl` fallback that signals the command's process group; with none of them it runs unbounded and prints a `Warning:`. Exit code 124 on timeout (busybox `timeout`'s 143 and the 137 of a SIGKILL escalation are normalised).
- `substitute_invoke <template> <base_branch> <files> <pr_number>`: replaces placeholders. `<files>` holds one path per line; `{files}` becomes the space-separated list with each path shell-quoted (a path starting with `-` is passed as `./-...`). Rejects an empty, dash-prefixed or non `[A-Za-z0-9._/@+-]` base branch and a non-numeric PR number. The placeholder set itself is defined once, in the discovery validator (`CC_REVIEW_PLACEHOLDERS`).
- `map_severity <reviewer_json_element> <native_severity>`: prints the mapped cc-review severity, or empty string when the finding must be dropped.
- `apply_config_enablement <reviewers_json> <reviewers_config_json>`: `<reviewers_config_json>` is the merged config's `reviewers` map (`resolve_config_reviewers_json`). A `ready` entry becomes `disabled` (reason `disabled`) when its key is `false`, or when there is no key and its `enabled` is `false` (FR-013). Other statuses are untouched.
- `apply_cli_selection <reviewers_json> <only_csv> <no_csv> <external_flag>`: returns the JSON with `status` moved between `ready` and `disabled` per FR-015 to FR-017a. Prints an error and returns 1 on an unknown name, an invalid `--only` name, an empty `--only`/`--no-` result, or an `--only` set of command reviewers combined with `--no-external`. `--no-<name>` for an invalid reviewer only warns. `external_flag` is `""`, `"on"`, or `"off"`.
- `apply_detection <reviewers_json>`: runs `detect` and `auth_check` (bounded by `CC_REVIEW_DETECT_TIMEOUT`, default 15 seconds, stdin closed) for every `kind: command` entry that is still `ready`, and moves a failing one to `skipped`. The reason carries the last non-empty stderr line of the failing check (terminal escapes and control characters removed, at most 160 characters): `not authenticated: <line>`.
