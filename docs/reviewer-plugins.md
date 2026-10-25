# Reviewer Plugins

cc-review reviewers are plugins: a markdown file with YAML frontmatter and a body. The six built-in review agents, the three external CLI integrations, and the opt-in `gator` reviewer all use this format. You add a reviewer by dropping one file into your project; no core file, config template, or command definition changes.

## Where reviewers live

Discovery runs on every review and scans three layers:

| Layer | Path | Precedence |
|-------|------|------------|
| project | `<git root>/.cc-review/reviewers/` | highest |
| user | `~/.cc-review/reviewers/` | middle |
| bundled | `review/core/reviewers/` (shipped with the plugin) | lowest |

When the same reviewer `name` exists in more than one layer, the higher layer replaces the lower one entirely (no field merging), and the console notes the override, for example `Security (project override)`. An invalid higher-layer reviewer never shadows a valid lower one: the valid one is used and a warning explains the fallback.

Invalid reviewers never abort a review. Each one produces a `Warning:` line naming the file and the reason, and the review continues.

## Project reviewers and the change under review

The project layer is read from the checkout being reviewed, so whoever authors a change also controls those files. Two rules keep a change from steering its own review:

- **A reviewer the change edits does not judge it.** When a project reviewer's file (its `.md`, any file of its plugin directory, a reference, or its parser) is part of the change under review, discovery ignores that reviewer for this run with a warning. The bundled or user reviewer of the same name runs instead; a reviewer the change adds is listed as `skipped (changed in the reviewed change)`. The new or edited reviewer takes effect for every later change, once it is committed.
- **Project command reviewers need your trust.** A `kind: command` reviewer in `.cc-review/reviewers/` runs shell commands with your credentials, so cc-review runs none of its commands (`detect`, `auth_check`, `invoke`, parser) until you trust it. Until then it shows as `skipped (untrusted project command reviewer (trust with: <name> <sha256>))`. To trust the current version, add that line to `~/.cc-review/trusted-reviewers`:

  ```text
  # ~/.cc-review/trusted-reviewers: <name> <sha256>, one per line
  lint-service 3f1c...e9a0
  ```

  The hash covers the reviewer file, or for a directory-form reviewer every file in its directory (parser and any helper it sources included), so any edit needs a new line. A reviewer directory with a symlink is never trusted. Keep everything a command reviewer runs inside its directory: a project script that `invoke` or the parser calls from elsewhere in the repository is not covered by the hash. `/cc-review:init` prints the line for every untrusted project command reviewer. The trust file is only read from your home directory, never from the project. Project prompt reviewers, and every reviewer in the user and bundled layers, need no trust.

## Two forms

**File form**: `<layer-dir>/<name>.md`

**Directory form**: `<layer-dir>/<name>/reviewer.md` plus any supporting files. Use this when the prompt needs reference material (see `references`) or when a command reviewer ships a parser script. A directory without a `reviewer.md` is ignored silently, so it can hold data for another reviewer.

If both `<name>.md` and `<name>/reviewer.md` exist in the same layer, the file form wins and a warning is logged.

## Frontmatter fields

| Field | Required | Default | Applies to | Notes |
|-------|----------|---------|------------|-------|
| `name` | yes | | both | `^[a-z0-9][a-z0-9-]*$`; must equal the file basename or directory name; see reserved names below. Quote a name YAML would read as a number (`name: "007"`) |
| `kind` | yes | | both | `prompt` or `command` |
| `display_name` | no | `name` | both | Shown in the console table and report |
| `category` | no | `name` | both | `^[a-z0-9-]+$`; written to every finding; quote all-digit values |
| `enabled` | no | `true` | both | Default when config has no `reviewers.<name>` key |
| `requires` | no | `[]` | both | Precondition tokens: `pr`, `spec`, `binary:<name>`; an unknown token is unsatisfied |
| `severity_map` | no | identity | both | Native severity to `Critical`, `Important`, `Minor`, or `Notable` |
| `dedup` | no | `cross-category` | both | `isolated`: never merge with findings of other categories |
| `references` | no | `[]` | prompt | Relative paths inside the plugin directory, inlined after the body |
| `context` | no | `[]` | prompt | Extra context blocks the core supplies; only `goals` exists |
| `detect` | command: yes | | command | Shell check; exit 0 means available |
| `auth_check` | no | | command | Shell check; non-zero exit skips with `not authenticated` |
| `invoke` | command: yes | | command | Command template; placeholders `{base_branch}`, `{files}`, `{pr_number}` |
| `timeout_seconds` | no | `120` | command | Wall-clock bound for `invoke` |
| `output.format` | command: yes | | command | `json`, `delimited`, or `parser` |
| `output.delimiter` | delimited: yes | | command | Block separator |
| `output.fields` | delimited: yes | | command | Finding field to label; needs `file`, `line`, `severity`, `description` |
| `output.parser` | parser: yes | | command | Executable script inside the plugin directory |

Unknown fields are ignored (a note is printed at verbose verbosity), so the format can grow without breaking older reviewers. The machine-readable contract is `review/core/schemas/reviewer.schema.json`.

**Reserved names** (they would collide with existing flags): `external`, `fix`, `meta-review`, `only`, `sequential`, `parallel`, `pr`, `spec`, `hints`, `output`, `config`, `profile`, `max-rounds`.

## Prompt reviewers

The body is the reviewer prompt. Write it for a reviewer that reads the changed files itself and reports findings; do not mention harness tools (no `ReportFindings`, no Agent tool). The core assembles the final subagent prompt at dispatch time in this order:

1. The common preamble (`review/core/agents/preamble.md`): anti-sycophancy, distrust, confidence scoring, output format. It is always applied; there is no opt-out. If your body conflicts with it (for example, instructions to praise good code), remove those instructions.
2. Your body.
3. Each `references` file, in order, under a heading `## Reference: <relative path>`.
4. The review target (changed file paths).
5. The spec and review hints when present.
6. Requested `context` blocks. `goals` adds `## Declared Goals` with the PR description, linked issues, and spec requirements; it is supplied only when PR context exists and the PR has a description. Declare `requires: [pr]` as well if your reviewer cannot work without a PR. A reviewer with `requires: [pr]` still runs on a PR with an empty description, just without the block; the bundled `goal-alignment` reviewer then infers the goals from the change and marks them as inferred.
7. The output contract: finding fields (`file`, `line`, `summary`, `failure_scenario`, `category`, `short_summary`, `severity`, `confidence`) and the optional `Positive observations:` section.

Each prompt reviewer may end its final text with a section headed `Positive observations:` holding 2 to 5 bullets that cite a file and function or line. The core aggregates these from all reviewers into the "What Went Well" part of the PR review summary.

Severities you report are translated through `severity_map`. With the default identity map, report `Critical`, `Important`, `Minor`, or `Notable` directly. A native value that is not in the map and not a cc-review severity drops the finding with a warning.

### Worked example: a drop-in prompt reviewer

`.cc-review/reviewers/accessibility.md`:

```markdown
---
name: accessibility
display_name: "Accessibility"
kind: prompt
category: accessibility
---
You are the ACCESSIBILITY REVIEW AGENT.

YOUR ROLE: You ARE responsible for finding accessibility defects in UI code:
missing alternative text, unlabeled form controls, keyboard traps, color-only
signaling, and ARIA misuse.

YOU ARE NOT RESPONSIBLE FOR: correctness bugs, security, performance, or
test quality. Stay in your lane.

For each changed file that renders UI, check:
- Every image and icon has meaningful alternative text or is marked decorative
- Every form control has an associated label
- Interactive elements are reachable and operable with the keyboard
- Information is not conveyed by color alone
- ARIA roles and attributes match the element's behavior

Report each defect as a finding with the exact element and line.
```

Commit the file. On the next `/review` the reviewer runs with the built-ins, its findings carry `source_agent: accessibility` and `category: accessibility`, and the console shows an "Accessibility" row. Disable it for one run with `--no-accessibility`, or run only it with `--only accessibility`.

### Directory form with references

```text
.cc-review/reviewers/api-contract/
├── reviewer.md
└── references/
    └── versioning-policy.md
```

```markdown
---
name: api-contract
kind: prompt
references:
  - references/versioning-policy.md
---
You are the API CONTRACT REVIEW AGENT. Verify every public API change against
the versioning policy that follows this prompt.
```

Only files listed in `references` reach the prompt. A listed file that is missing, absolute, contains `..`, or is (or sits below) a symlink pointing outside the plugin directory makes the reviewer invalid.

## Command reviewers

A command reviewer wraps an external tool. The frontmatter declares how to detect it, how to run it, and how to turn its output into findings; the body holds parsing notes for the orchestrator.

- `detect` runs before dispatch, and only for command reviewers that are still enabled after config and CLI flags (a reviewer turned off by `--no-external`, `--only` or config costs no probe). Non-zero exit: `skipped (not available)`.
- `auth_check` (optional) runs after `detect`. Non-zero exit: `skipped (not authenticated)`. Leave it out when some users authenticate in a way the check cannot see (the bundled `codex` reviewer has none, so an API key in the environment works).
- When a check fails, the last line it printed on stderr is appended to the reason (`not authenticated: token expired`), so a network error or a broken install does not look like a missing login.
- `invoke` is a template. `{base_branch}` is the comparison branch, `{files}` is the space-separated, shell-quoted list of changed files, `{pr_number}` is the PR number. Using `{pr_number}` when no PR exists skips the reviewer with `requires: pr`, whether or not `requires` declares it. Shell constructs such as `${HOME}` or `{}` are left alone; any other `{word}` is reported as an unknown placeholder.
- `detect` and `auth_check` run under a 15 second bound (`CC_REVIEW_DETECT_TIMEOUT`); a check that does not finish skips the reviewer with `detection timed out` or `authentication check timed out`.
- The command runs under `bash -c` bounded by `timeout_seconds` (via `timeout -k 5`, `gtimeout -k 5`, or a `perl` fallback on systems without coreutils; a tool that ignores SIGTERM is killed five seconds later). All enabled command reviewers start together, so the wait is that of the slowest one. Timeout or non-zero exit marks the reviewer `failed (timeout)` or `failed (exit N)`; the review continues. Only stdout is parsed; stderr is shown at verbose verbosity.
- `output.format`:
  - `json`: stdout is a JSON array of objects with `file`, `line` (or `line_start`), `severity`, `description`, `rationale`, and optional `fix`, `confidence`.
  - `delimited`: stdout is split into blocks on `output.delimiter`; inside a block, `<Label>: <value>` lines map to finding fields through `output.fields`. A value continues until the next known label.
  - `parser`: `output.parser` names an executable in the plugin directory that reads the raw output on stdin and prints `json` format. It runs through its own shebang, so any language works; the bundled CodeRabbit reviewer ships a `jq` based one.
- Output that cannot be parsed marks the reviewer `failed (parse error)`; the first lines of raw output are logged at verbose verbosity.
- Every finding gets `source_agent` = `name`, `category` = `category`, severity through `severity_map`, and `confidence` 75 when the tool provides none.

### Worked example: a command reviewer

`.cc-review/reviewers/lint-service/reviewer.md`:

```markdown
---
name: lint-service
display_name: "Lint Service"
kind: command
category: external
detect: "command -v lintctl"
auth_check: "lintctl whoami"
invoke: "lintctl review --base {base_branch} --format cc-review -- {files}"
timeout_seconds: 90
severity_map:
  error: Important
  warning: Minor
  info: Notable
output:
  format: json
---
With `--format cc-review`, lintctl prints one JSON array whose objects already
use `file`, `line`, `severity` (error, warning, info), `description`, and
`rationale`.
```

The `json` format takes the array as is; the body is not consulted. When the tool's output needs any field renaming or reshaping, switch to `output.format: parser` and ship an executable script next to `reviewer.md`. For a tool that prints one object per line with `path`, `line`, `level`, `message`, and `detail`:

```yaml
output:
  format: parser
  parser: parse.sh
```

```sh
#!/bin/sh
exec jq -s 'map({file: .path, line, severity: .level, description: .message, rationale: .detail})'
```

`{files}` expands to the changed paths, each shell-quoted; do not put it inside quotes in `invoke`. A path starting with `-` is passed as `./-...`, and a `--` before `{files}` keeps tools from reading paths as options.

The bundled `copilot` and `codex` reviewers in `review/core/reviewers/` are command reviewers using the `delimited` format, and `coderabbit/` is a directory-form command reviewer with a `parser` script for the CLI's JSON-lines output; read them as further examples.

Discovery needs `jq` 1.6 or newer, mikefarah `yq` 4.18 or newer, and `awk`; it stops with an error naming the missing or wrong tool.

## Preconditions

`requires` tokens are evaluated at discovery:

| Token | Satisfied when |
|-------|----------------|
| `pr` | A PR number is available (`--pr` or auto-detected) |
| `spec` | A spec file was passed with `--spec` |
| `binary:<name>` | `<name>` is on `PATH` |

An unsatisfied precondition skips the reviewer with `skipped (requires: <token>)`. Unknown tokens are unsatisfied and skip with `unknown precondition: <token>`. `--only` never overrides a precondition or a detection result.

## Configuration and CLI

Enable or disable any discovered reviewer in `.cc-review/config.yml` (project) or `~/.cc-review/config.yml` (user):

```yaml
reviewers:
  test-quality: false
  gator: true
  accessibility: true
```

A reviewer without a key uses the `enabled` default from its frontmatter. The bundled config template sets no `reviewers.<name>` key, so this also holds for a user or project plugin that overrides a bundled name: its own `enabled` value applies. The bundled defaults (every reviewer enabled except `copilot` and `gator`) live in the reviewers' frontmatter; the `quick`, `thorough` and `ci` profiles set an explicit key for every bundled reviewer. The legacy keys `agents.<name>` and `external_tools.<name>` still work for the migrated reviewers (underscores map to hyphens, for example `agents.test_quality` to `reviewers.test-quality`) and print a deprecation warning.

`kind: command` reviewers do not run in the checkout of a pull request from a fork (bulk review, or `--pr` for a PR that is not the current branch), because the external tool could load the PR's own agent instruction files. They are reported as `skipped (untrusted checkout)`. Opt a reviewer in per name; the value must be a boolean, and an invalid one is dropped with a warning:

```yaml
allow_untrusted_checkout:
  codex: true
```

CLI flags take precedence over config and are derived from the discovered names:

| Flag | Effect |
|------|--------|
| `--no-<name>` | Disable one reviewer (`--no-codex`, `--no-accessibility`) |
| `--only <a,b>` | Dispatch only the listed reviewers; re-enables config-disabled ones; unknown names are an error listing the discovered names |
| `--only a,b --no-a` | `--no-` subtracts from the `--only` set; an empty result is an error |
| `--no-external` / `--external` | Disable or enable every `kind: command` reviewer; `--only` with only command reviewers plus `--no-external` is an error |
| `--parallel` | Accepted for compatibility; parallel dispatch is the default (`--sequential` changes it) |

`--no-<name>` for a reviewer that failed validation prints a warning and the review continues; `--only <name>` for one is an error.

`/cc-review:init` lists every discovered reviewer with its layer, kind, enabled state, and precondition status, and generates `reviewers.<name>` keys.

## Console and report

Every discovered reviewer appears in the console summary and in `review-findings.md` with its display name and one of: `completed` (with found/fixed/remaining counts), `disabled`, `skipped (<reason>)`, or `failed (<reason>)`. Invalid reviewers are reported as warnings at discovery instead.

## The gator reviewer

`review/core/reviewers/gator/` is the first contributed plugin and a reference for the directory form. It ports the principal-engineer reviewer from NVIDIA's OpenShell project (Apache-2.0, attribution in the file): a pragmatic, user-empathetic, security-aware persona with an evidence contract (`references/findings-contract.md`) that every Critical or Warning finding must satisfy. Its native severities map through `severity_map` (Critical to Critical, Warning to Important, Suggestion to Minor). The Apache-2.0 license text ships as `gator/LICENSE`; it is not a `references` entry, so it never reaches the prompt. It is disabled by default:

```yaml
reviewers:
  gator: true
```

## Checklist for plugin authors

- `name` matches the filename or directory name, is not reserved, and is quoted when YAML would read it as a number
- `kind: prompt` bodies mention no harness tools and do not conflict with the preamble
- `references` paths are relative, inside the plugin directory, and exist
- `kind: command` declares `detect`, `invoke`, and a complete `output` block; `invoke` uses only the three placeholders
- `severity_map` values are `Critical`, `Important`, `Minor`, or `Notable`
- A project `kind: command` reviewer needs a line in `~/.cc-review/trusted-reviewers` before it runs; re-add it after every edit
- Run `review/core/scripts/discover-reviewers.sh --core-dir review/core --project-dir . --skip-detection | jq` to see how discovery classifies your reviewer (it leaves the prompt bodies in a `cc-review-reviewers.*` directory under `$TMPDIR`; remove it when done)
