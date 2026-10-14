# Feature Specification: Pluggable Reviewers

**Feature Branch**: `004-reviewer-plugins`

**Created**: 2026-10-13

**Status**: Draft

**Input**: User description: "Pluggable reviewers for cc-review. Make reviewers pluggable via a harness-agnostic plugin format (markdown file with YAML frontmatter, body is the prompt; optional directory form for reviewers with supporting files). Two kinds: prompt and command. Three-layer discovery with override by name. Unify the six built-in agents and three external CLI tools into the plugin format. Config collapses agents.* and external_tools.* into reviewers.<name>. CLI flags derived from discovered names. First contributed plugin: gator, ported from NVIDIA/OpenShell's principal-engineer-reviewer. Out of scope: remote plugin sources, wrapping gator's sandbox pipeline." Derived from brainstorm `brainstorm/05-reviewer-plugins.md`.

## Clarifications

### Session 2026-10-13

- Q: Is the common preamble (anti-sycophancy, distrust, confidence scoring, output format) applied to every `kind: prompt` reviewer, including contributed ones, or can a reviewer opt out? → A: Always applied, no opt-out. The preamble is the core's quality contract; a plugin body that conflicts with it (for example, instructions to praise good code) must be adjusted by the plugin author. The gator port drops its "if something is good, say so" instruction accordingly.
- Q: How do supporting files in the directory form reach the prompt? → A: Through an explicit `references` metadata field listing relative paths inside the plugin directory. The core inlines each listed file after the prompt body, in order, under a heading with the file name. Files not listed are not exposed. No templating or include directives in the body.
- Q: How are the current by-name special cases for goal-alignment (declared-goals context block, dedup exemption against other categories, the "What Went Well" section) expressed so the review command stays free of reviewer names? → A: Through metadata and output contract, not names: a `context` field listing optional extra context blocks the core can supply (`goals` is the only block in this version), a `dedup` field (`cross-category` default, or `isolated` to never merge with other categories), and an optional `positive_observations` list in every prompt reviewer's output that the core aggregates into "What Went Well" when non-empty.
- Q: Which placeholders may a command reviewer's `invoke` template use, and what happens when `{pr_number}` is used but no PR context exists? → A: `{base_branch}`, `{files}` (space-separated changed file paths), and `{pr_number}`. A template that uses `{pr_number}` when no PR is available is treated as an unsatisfied `pr` precondition and skipped with reason "requires: pr", whether or not the reviewer declared it.
- Q: What is the result when `--only a,b` is combined with `--no-a`? → A: `--no-<name>` subtracts from the `--only` set; the result dispatches only `b`. If the subtraction empties the set, the review stops with an error saying no reviewers remain.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Drop-In Prompt Reviewer (Priority: P1)

A developer wants a review perspective that cc-review does not ship, for example an accessibility reviewer for their frontend project. They write a single markdown file with a small metadata header and a prompt body, save it as `.cc-review/reviewers/accessibility.md` in their project, and commit it. On the next `/review` run the accessibility reviewer is dispatched alongside the built-in reviewers, its findings appear in the merged report with the source name "accessibility", and it shows up as a row in the console summary table. No core cc-review file was touched.

**Why this priority**: This is the core value of the feature. Without drop-in discovery and dispatch, nothing else in this spec matters.

**Independent Test**: Create a project-level reviewer file with a distinctive prompt (for example, one that always reports a specific marker string as a Minor finding), run a review, and verify the finding appears with the correct source name and category.

**Acceptance Scenarios**:

1. **Given** a valid reviewer file at `.cc-review/reviewers/accessibility.md` with `kind: prompt`, **When** `/review` runs, **Then** the reviewer is dispatched as its own fresh-context subagent in the same parallel batch as the built-in reviewers.
2. **Given** the accessibility reviewer produced findings, **When** the findings report is written, **Then** each finding carries `source_agent: accessibility` and the `category` declared in the reviewer's metadata.
3. **Given** the accessibility reviewer ran, **When** the console summary is printed, **Then** it contains a row with the reviewer's display name and its found/fixed/remaining counts.
4. **Given** the reviewer file is added to a project, **When** the next review runs, **Then** it is picked up without any install, registration, or restart step. (A review of the change that itself adds or edits the reviewer ignores it for that run, see FR-008a; it takes effect for every later change.)
5. **Given** the reviewer prompt body contains no harness-specific tool names, **When** the review runs under Claude Code, Codex, or OpenCode, **Then** the reviewer works identically because the core appends the preamble and output contract at dispatch time.

---

### User Story 2 - Built-In Reviewers Become Plugins (Priority: P1)

A maintainer upgrades cc-review. The six built-in reviewers (correctness, architecture, security, production, test-quality, goal-alignment) are now shipped as plugins in the bundled reviewers directory, and the review command no longer contains a hard-coded list of them. Existing projects keep working: a config that disabled `agents.test_quality` still disables the test-quality reviewer, with a deprecation warning pointing to the new `reviewers.test-quality` key.

**Why this priority**: Unification is what makes the plugin format the single dispatch model. Without it there are two code paths to maintain and the built-ins never exercise the plugin contract.

**Independent Test**: Run a review on a known diff before and after the migration and confirm the same set of reviewers is dispatched, findings carry the same source names and categories, and existing config toggles still take effect.

**Acceptance Scenarios**:

1. **Given** no project or user configuration, **When** `/review` runs, **Then** the six built-in prompt reviewers are dispatched, plus the command reviewers that are enabled by default and whose detection passes, matching pre-migration behavior.
2. **Given** a config with `reviewers.test-quality: false`, **When** `/review` runs, **Then** the test-quality reviewer is not dispatched and is listed as "disabled" in the console summary.
3. **Given** a config that still uses the legacy key `agents.test_quality: false`, **When** `/review` runs, **Then** the test-quality reviewer is not dispatched and a one-line deprecation warning names the replacement key.
4. **Given** the goal-alignment reviewer declares a precondition that PR context is required, **When** `/review` runs without a PR, **Then** goal-alignment is skipped and the console reports "skipped (requires: pr)".
5. **Given** the review command definition, **When** inspected, **Then** it contains no reviewer-specific names, prompts, or invocation commands; all reviewer knowledge lives in the reviewer files.

---

### User Story 3 - External CLI Tools as Command Reviewers (Priority: P2)

A team uses CodeRabbit CLI. Instead of CodeRabbit's detection, invocation, and output parsing living inside the review command, it is defined as a `kind: command` reviewer plugin in the bundled directory. The plugin declares how to detect the tool, how to invoke it, and how to turn its output into findings. The same mechanism lets the team add their internal linter-as-a-service as a command reviewer in their project directory.

**Why this priority**: Closes the problem that brainstorm #03 raised. Command reviewers are the second half of the unified model but depend on the discovery and dispatch from User Story 1.

**Independent Test**: Define a command reviewer whose invoke command is a script that prints a fixed finding in the declared output format. Run a review and verify the finding appears with the correct source name, category, and mapped severity.

**Acceptance Scenarios**:

1. **Given** a command reviewer whose detection check fails (tool not installed), **When** `/review` runs, **Then** the reviewer is skipped and the console reports "skipped (not available)" without any error.
1b. **Given** a command reviewer whose detection check passes but whose `auth_check` fails, **When** `/review` runs, **Then** the reviewer is skipped and the console reports "skipped (not authenticated)", followed by the last line the check printed on stderr when there is one, without any error.
2. **Given** a command reviewer whose detection check passes, **When** `/review` runs, **Then** its invoke command is executed with the review context (base branch, changed files) substituted, and its output is parsed into findings.
3. **Given** a command reviewer with a severity map `major: Important`, **When** the tool reports a "major" issue, **Then** the finding appears with severity Important.
4. **Given** a command reviewer whose invocation exceeds its declared timeout or exits with an error, **When** `/review` runs, **Then** the failure is logged, the reviewer is marked "failed" in the summary, and the review continues with the remaining reviewers.
5. **Given** CodeRabbit, Copilot CLI, and Codex CLI are shipped as bundled command reviewers, **When** `/review --no-external` runs, **Then** all three are disabled and no other reviewer is affected.
6. **Given** a command reviewer's declared output format cannot be parsed from the tool's actual output, **When** `/review` runs, **Then** the reviewer is marked "failed (parse error)" with the first lines of raw output logged at verbose level.

---

### User Story 4 - Gator Reviewer Bundled (Priority: P2)

A user wants the pragmatic principal-engineer review style from NVIDIA's OpenShell project. cc-review ships a `gator` reviewer in the bundled directory, ported from OpenShell's principal-engineer-reviewer. It is disabled by default. The user enables it with `reviewers.gator: true` in their config. On the next review, gator runs as a prompt reviewer and its findings carry evidence-backed rationale (invariant, reachability, base versus head behavior, reproducer) and severities mapped into cc-review's scheme.

**Why this priority**: First contributed plugin, proving the format on a real external prompt with its own severity vocabulary and supporting reference file. Depends on User Story 1.

**Independent Test**: Enable gator, run a review on a diff with a known reachable bug, and verify a gator finding appears with Critical or Important severity, an evidence-structured rationale, and source name "gator".

**Acceptance Scenarios**:

1. **Given** default configuration, **When** `/review` runs, **Then** gator is not dispatched and appears as "disabled" in the summary.
2. **Given** `reviewers.gator: true`, **When** `/review` runs, **Then** gator is dispatched as a prompt reviewer with fresh context.
3. **Given** gator reports a finding with its native severity "Warning", **When** findings are merged, **Then** the finding has cc-review severity Important; "Suggestion" maps to Minor; "Critical" stays Critical.
4. **Given** gator produced a finding, **When** the report is written, **Then** the finding's rationale states the invariant violated, the entry point, the base-versus-head behavior change, the observable impact, and a reproducer, as required by the plugin's evidence contract.
5. **Given** the gator plugin files, **When** inspected, **Then** they contain no OpenShell-specific instructions (repository context, documentation gates, label routing, review-ledger handling) and carry an attribution to the upstream source.
6. **Given** the gator plugin is in the directory form with its evidence contract listed in `references`, **When** gator is dispatched, **Then** the contract file's content is inlined into the prompt after the body.

---

### User Story 5 - Layered Discovery and Overrides (Priority: P3)

A developer keeps a personal "nitpicky naming" reviewer in `~/.cc-review/reviewers/naming.md` that follows them across projects. Their team also wants a stricter variant of the bundled security reviewer for one repository, so they place `security.md` in the project's `.cc-review/reviewers/`. In that repository the project's security reviewer replaces the bundled one, while every other project still uses the bundled version.

**Why this priority**: Layering gives personal and team customization without forking the plugin. Depends on User Story 1 and is additive.

**Independent Test**: Place a reviewer with the same name as a bundled one in the project directory with a distinctive prompt. Run a review and verify only the project version is dispatched.

**Acceptance Scenarios**:

1. **Given** a reviewer named `security` exists in both the bundled directory and the project directory, **When** `/review` runs, **Then** only the project version is dispatched and the console notes "security (project override)".
2. **Given** a reviewer exists only in the user directory, **When** `/review` runs in any project, **Then** it is discovered and dispatched.
3. **Given** the same name exists in the user and project directories, **When** `/review` runs, **Then** the project version wins (project > user > bundled).
4. **Given** `/cc-review:init` runs, **When** it reports its environment detection, **Then** it lists every discovered reviewer with its layer, kind, enabled state, and whether its preconditions are currently satisfied.

---

### User Story 6 - Derived CLI Flags (Priority: P3)

A developer wants a quick security-only pass. They run `/review --only security,gator`. Only those two reviewers are dispatched. Another time they run `/review --no-production` to skip one reviewer. These flags work for any discovered reviewer, including user-contributed ones, without the flag list being maintained by hand.

**Why this priority**: Convenience layer over config. Depends on discovery.

**Independent Test**: Run `/review --only <contributed-reviewer>` and verify only that reviewer is dispatched.

**Acceptance Scenarios**:

1. **Given** reviewers `a`, `b`, `c` are discovered and enabled, **When** `/review --only a,c` runs, **Then** only `a` and `c` are dispatched.
2. **Given** reviewer `b` is enabled, **When** `/review --no-b` runs, **Then** `b` is not dispatched and all others are unaffected.
3. **Given** `/review --only unknown` is run with no reviewer named `unknown`, **Then** the review stops with an error listing the discovered reviewer names.
4. **Given** reviewer `x` is disabled in config, **When** `/review --only x` runs, **Then** `x` is dispatched (an explicit `--only` wins over config, consistent with CLI-over-config precedence).
4b. **Given** reviewer `y` has an unsatisfied precondition or a failing detection check, **When** `/review --only y` runs, **Then** `y` is still skipped with its reason; `--only` overrides enablement, not preconditions.
5. **Given** the legacy flags `--no-coderabbit`, `--no-copilot`, `--no-codex`, **When** used, **Then** they continue to work because they are the derived flags for the reviewers of the same names.

---

### Edge Cases

- A reviewer file has malformed metadata (invalid YAML, missing `name` or `kind`, unknown `kind` value): the file is skipped with a warning naming the file and the problem; the review continues.
- A reviewer's `name` does not match the allowed pattern (lowercase letters, digits, hyphens) or does not match its filename or directory name: skipped with a warning.
- Two reviewers with the same name exist in the same layer (for example both `foo.md` and `foo/reviewer.md`): the file form wins and a warning is logged.
- A directory in a reviewers folder has no `reviewer.md`: ignored silently (it may be supporting data for another reviewer).
- A `kind: prompt` reviewer has an empty body: skipped with a warning.
- A `references` entry points outside the plugin directory (absolute path or `..`) or to a missing file: the reviewer is skipped with a warning.
- A `kind: prompt` reviewer declares `context: [goals]` but no PR context exists: the block is simply omitted unless the reviewer also declares `requires: [pr]`, in which case it is skipped.
- `--only a,b --no-a` dispatches only `b`; `--only a --no-a` stops with an error that no reviewers remain.
- A `kind: command` reviewer lacks an invoke command or an output format: skipped with a warning.
- A reviewer's name collides with a reserved flag word (at minimum `external`, `fix`, `meta-review`, `only`; that is, any name whose derived `--no-<name>` flag would clash with an existing non-reviewer flag): skipped with a warning explaining the collision.
- No reviewers are discovered at all (for example a broken install): the review stops with an error rather than silently producing an empty report.
- All discovered reviewers are disabled or skipped by preconditions: the review stops with a clear message listing each reviewer and why it did not run.
- A reviewer declares an unknown precondition token: the token is treated as unsatisfied and the reviewer is skipped with a warning.
- A severity map declares a value outside the cc-review scheme: the reviewer is rejected at discovery and listed as invalid with the reason `invalid severity_map value: <v>`, so a misconfigured plugin is visible before any review runs instead of silently losing findings.
- A finding's native severity has no entry in a non-identity severity map: if the native value is already a cc-review severity it passes through unchanged; otherwise the finding is dropped with a warning.
- A reviewer in the user directory has the same name as a bundled one but is invalid: the bundled one is used and a warning explains the fallback.
- Metadata contains unrecognized fields: they are ignored with a verbose-level note, not treated as errors, so the format can grow.
- The fix loop re-dispatches reviewers on modified files: re-dispatch uses the same discovered set, with the same enabled/skipped decisions as the first round.
- A project-layer reviewer whose files (the reviewer file, any file of a directory-form plugin, a reference, or a parser) are in the change under review is ignored for that run with a warning: the next lower layer's reviewer of the same name runs if it is valid, otherwise the entry is skipped with reason `changed in the reviewed change`. A change can therefore not replace or weaken the reviewer that judges it.
- A project-layer `kind: command` reviewer that the user has not trusted is skipped with reason `untrusted project command reviewer (trust with: <name> <sha256>)`; none of its `detect`, `auth_check`, `invoke` or parser commands run. Editing the reviewer file, or any file in a directory-form reviewer's directory, changes the hash and needs a new trust entry; a reviewer directory containing a symlink is never trusted. Project prompt reviewers need no trust.
- A `name` or `category` that YAML reads as a number or boolean (`007`, `1e3`, `0x1f`, `true`) is rejected with reason `name must be a quoted string` (or `category must be a quoted string`), because the original text cannot be recovered after parsing.
- `--no-<name>` for a reviewer that failed validation prints a warning and the review continues; `--only <name>` for such a reviewer is an error.
- `--only` naming only command reviewers combined with `--no-external` stops with an error that no reviewers remain.
- A PR with an empty description still satisfies `requires: [pr]`: goal-alignment runs without a `goals` block and infers the goals from the change, marking them as inferred.
- A failing `detect` or `auth_check` reports the last line of its stderr in the skip reason (control characters removed, length bounded), so a network error or broken install is not mistaken for a missing login.

## Requirements *(mandatory)*

### Functional Requirements

**Plugin format**

- **FR-001**: A reviewer plugin MUST be definable as a single markdown file whose frontmatter holds metadata and whose body holds the prompt (for `kind: prompt`) or parsing notes (for `kind: command`).
- **FR-002**: A reviewer plugin MUST alternatively be definable as a directory named after the reviewer containing a `reviewer.md` file in the same format plus arbitrary supporting files.
- **FR-003**: Reviewer metadata MUST support these fields: `name` (required, identifier), `kind` (required, `prompt` or `command`), `display_name` (defaults to `name`), `category` (defaults to `name`), `enabled` (default true), `requires` (list of precondition tokens, default empty), `severity_map` (native severity to cc-review severity, default identity), `dedup` (`cross-category` default, or `isolated` so findings never merge with findings of other categories).
- **FR-003a**: For `kind: prompt`, metadata MUST additionally support `references` (ordered list of relative paths inside the plugin directory, default empty) and `context` (list of optional extra context blocks the core supplies, default empty; `goals` is the only supported block in this version and is supplied only when PR context exists).
- **FR-003b**: The core MUST inline each file listed in `references`, in order, after the prompt body under a heading naming the file. Files in the plugin directory that are not listed MUST NOT be exposed to the prompt. A listed file that does not exist, or whose path resolves outside the plugin directory (absolute path or `..` segment), MUST cause the reviewer to be skipped with a warning at discovery time.
- **FR-004**: For `kind: command`, metadata MUST additionally support: `detect` (shell check for availability), `auth_check` (optional shell check for authentication), `invoke` (command template; supported placeholders are exactly `{base_branch}`, `{files}` as the changed file paths, each shell-quoted and separated by spaces, with a path that starts with `-` passed as `./-...` so tools cannot read it as an option, and `{pr_number}`), `timeout_seconds` (default 120), and `output` (format declaration: `json` for findings already in cc-review's finding schema, `delimited` with a delimiter and field labels, or `parser` naming a script in the plugin directory that reads raw output and emits cc-review findings).
- **FR-004a**: An `invoke` template that uses `{pr_number}` when no PR context exists MUST be treated as an unsatisfied `pr` precondition and skipped with reason "requires: pr", regardless of the declared `requires` list.
- **FR-005**: The `name` MUST consist of lowercase letters, digits, and hyphens, and MUST equal the file basename (without extension) or the directory name. `name` and `category` MUST be YAML strings; a value YAML reads as a number or boolean is rejected with a reason asking the author to quote it.
- **FR-006**: Reviewer prompt bodies MUST NOT be required to reference any harness-specific tool or mechanism; the core MUST prepend the common preamble and append the review target, optional spec and hints, requested `context` blocks, inlined `references`, and the output contract at dispatch time.
- **FR-006a**: The common preamble MUST be applied to every `kind: prompt` reviewer without exception; the plugin format MUST NOT offer an opt-out. Plugin authors are responsible for removing body instructions that conflict with the preamble.
- **FR-006b**: The output contract for `kind: prompt` reviewers MUST accept an optional `positive_observations` list (short statements of what the change does well), returned as a final text section headed `Positive observations:` because the finding report carries no field for it. The core MUST aggregate non-empty lists from all reviewers into the "What Went Well" section of the PR review summary, replacing the current dependency on a specific reviewer.
- **FR-007**: Supported precondition tokens MUST include `pr` (PR context available), `spec` (spec file provided), and `binary:<name>` (executable on PATH). Unknown tokens MUST be treated as unsatisfied.

**Discovery**

- **FR-008**: The system MUST discover reviewers from three layers in this precedence order: project (`.cc-review/reviewers/`), user (`~/.cc-review/reviewers/`), bundled (the plugin's `core/reviewers/`).
- **FR-008a**: A project-layer reviewer with any of its files (reviewer file, directory-form file, reference, or parser) in the changed-file list of the review MUST be ignored for that run with a warning. The next lower layer's valid reviewer of the same name MUST be used; when there is none, the entry is skipped with reason `changed in the reviewed change`.
- **FR-008b**: A project-layer `kind: command` reviewer MUST NOT run any of its commands (`detect`, `auth_check`, `invoke`, parser) unless the user-level trust file (default `~/.cc-review/trusted-reviewers`, lines `<name> <sha256>`, `#` comments) lists its name with the SHA-256 of its current files (the reviewer file, or every file in a directory-form reviewer's directory). Otherwise it is skipped with reason `untrusted project command reviewer (trust with: <name> <sha256>)`. The trust file is never read from the project under review. Bundled and user layers are trusted; project prompt reviewers are allowed.
- **FR-009**: When the same `name` appears in multiple layers, the higher-precedence layer MUST replace the lower one entirely (no field merging), and the console MUST indicate the override. An invalid higher-precedence reviewer MUST NOT shadow a valid lower-precedence one; the valid one is used and the warning explains the fallback.
- **FR-010**: Discovery MUST validate each reviewer's metadata; invalid reviewers MUST be skipped with a warning that names the file and the reason, and MUST NOT abort the review.
- **FR-011**: Discovery MUST run on every review invocation with no install or registration step.
- **FR-012**: If discovery yields zero valid reviewers, the review MUST stop with an error.

**Configuration and CLI**

- **FR-013**: Reviewer enablement MUST be configurable via `reviewers.<name>: true|false`, with the reviewer's `enabled` metadata as the default when the key is absent. The default configuration template MUST NOT set any `reviewers.<name>` key, so the frontmatter default applies and a user or project override's own `enabled` value takes effect.
- **FR-014**: The legacy configuration keys `agents.<name>` and `external_tools.<name>` MUST continue to work for the migrated reviewers for at least one release, mapped to the new keys with a deprecation warning. Legacy underscore names (for example `test_quality`, `goal_alignment`) MUST map to their hyphenated reviewer names.
- **FR-015**: The CLI MUST accept `--no-<name>` for any discovered reviewer and `--only <name>[,<name>...]` to restrict dispatch to the listed reviewers. `--only` with an unknown name MUST stop with an error listing discovered names.
- **FR-016**: `--no-external` MUST disable all `kind: command` reviewers; `--external` MUST enable them.
- **FR-017**: CLI flags MUST take precedence over configuration, including `--only` overriding a config-disabled reviewer. `--only` MUST NOT override preconditions or detection results.
- **FR-017a**: When `--only` and `--no-<name>` are combined, `--no-<name>` MUST subtract from the `--only` set. If the resulting set is empty, the review MUST stop with an error stating that no reviewers remain. The same error applies when every remaining `--only` reviewer is a command reviewer and `--no-external` is given. `--no-<name>` for an invalid reviewer MUST only warn (FR-010).
- **FR-018**: Profile presets (`quick`, `thorough`, `ci`) MUST be expressed in terms of `reviewers.<name>` keys and the default configuration template MUST carry no legacy keys, so that a fresh install emits no deprecation warnings.

**Dispatch and results**

- **FR-019**: All enabled `kind: prompt` reviewers whose preconditions are satisfied MUST be dispatched as separate fresh-context subagents in a single parallel batch, or sequentially when `--sequential` is passed.
- **FR-020**: All enabled `kind: command` reviewers whose detection passes (and whose `auth_check`, when declared, succeeds; otherwise the reviewer is skipped with reason "not authenticated") MUST be invoked with placeholders substituted, bounded by their timeout, and their output converted to findings per their declared output format. The review command MUST run `detect` and `auth_check` only after config enablement and CLI selection, and only for command reviewers that are still enabled. All enabled command reviewers MUST be started together and awaited together, so the wall time is that of the slowest one.
- **FR-021**: Every finding MUST carry `source_agent` equal to the reviewer `name` and `category` equal to the reviewer's `category`, and MUST have its severity translated through the reviewer's `severity_map` before merging.
- **FR-022**: A reviewer failure (subagent error, command timeout, non-zero exit, parse error) MUST be logged, marked as "failed" in the summary, and MUST NOT block the review.
- **FR-023**: The console summary and the findings report MUST list every discovered reviewer with its display name and one of: completed (with counts), disabled, skipped (with reason), failed (with reason).
- **FR-024**: The fix-loop re-dispatch MUST reuse the discovered reviewer set and enablement decisions from the initial round.
- **FR-025**: Meta-review (skeptic, calibrator) and dedup/merge behavior MUST be unchanged and MUST treat plugin findings identically to built-in findings, with one generalization: dedup MUST honor each reviewer's `dedup` setting instead of a by-name exemption for goal-alignment.

**Migration**

- **FR-026**: The six built-in reviewers MUST be shipped as bundled prompt reviewers named `correctness`, `architecture`, `security`, `production`, `test-quality`, `goal-alignment`, with `goal-alignment` declaring `requires: [pr]`, `context: [goals]`, `dedup: isolated`, and a body that asks for `positive_observations`. Declared change: goal-alignment runs on every PR, including one with an empty description. The pre-plugin command skipped it when no goals were available; now `requires: [pr]` is its only gate, and without declared goals its prompt infers them from the change and marks them as inferred.
- **FR-027**: CodeRabbit, Copilot CLI, and Codex CLI MUST be shipped as bundled command reviewers named `coderabbit`, `copilot`, `codex`, with their current detection, invocation, parsing, and default enablement preserved. Codex detection stays `command -v codex` with no `auth_check`, so users who authenticate through an API key in the environment are not skipped.
- **FR-028**: After migration, the review command definition MUST contain no reviewer-specific names, prompts, or invocation commands.
- **FR-029**: `/cc-review:init` MUST list discovered reviewers with layer, kind, enabled state, and precondition status, and MUST generate `reviewers.<name>` keys instead of legacy keys.

**Gator plugin**

- **FR-030**: A bundled prompt reviewer named `gator` MUST be shipped in the directory form, disabled by default, ported from OpenShell's principal-engineer-reviewer with its persona and pragmatic calibration rules retained, all OpenShell-specific instructions removed, and instructions that conflict with the common preamble (praise of good code) removed. Its evidence contract MUST be a supporting file listed in `references`.
- **FR-031**: The gator plugin MUST require findings to carry the evidence contract (invariant, prerequisite, entry point, sink, base versus head behavior, observable impact, reproducer, PR ownership, requested change) within the finding's rationale and failure scenario.
- **FR-032**: The gator plugin MUST declare `severity_map` of Critical to Critical, Warning to Important, Suggestion to Minor.
- **FR-033**: The gator plugin MUST include an attribution to its upstream source and license.

### Key Entities

- **Reviewer Plugin**: A unit that produces findings. Identified by `name`. Has a `kind`, metadata, and either a prompt body or command definition. Lives in exactly one discovery layer at a time (after override resolution).
- **Reviewer Metadata**: The frontmatter contract (FR-003 through FR-004a). Validated at discovery.
- **Context Block**: An optional, named piece of review context the core can supply to a prompt reviewer on request via `context`. Only `goals` (declared PR goals and linked issues) exists in this version.
- **Reference**: A supporting file inside a directory-form plugin, listed in `references`, inlined after the prompt body.
- **Discovery Layer**: One of project, user, bundled. Ordered by precedence. A reviewer's effective definition is the highest-precedence valid one.
- **Precondition**: A token in `requires` evaluated at review start; unsatisfied preconditions cause a skip with reason.
- **Severity Map**: Translation from a reviewer's native severity vocabulary to cc-review's Critical / Important / Minor / Notable.
- **Output Format**: For command reviewers, how raw tool output becomes findings: `json`, `delimited`, or `parser` script.
- **Finding**: Existing cc-review entity; gains no new required fields. `source_agent` and `category` are populated from the reviewer.
- **Reviewer Status**: Per-run outcome for each discovered reviewer: completed, disabled, skipped (reason), failed (reason). The full status set and the step that sets each value are defined once, in `contracts/discovery-output.md`.
- **Trust File**: A user-level file (default `~/.cc-review/trusted-reviewers`) listing `<name> <sha256>` pairs for project-layer command reviewers the user allows to run.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Adding a new prompt reviewer to a project requires creating exactly one file and zero changes to any cc-review core file, configuration template, or command definition.
- **SC-002**: After migration, running a review with default configuration dispatches the same set of reviewers as before (the six prompt reviewers, plus CodeRabbit and Codex when available; Copilot stays disabled by default), and the console summary lists every discovered reviewer by display name.
- **SC-003**: The review command definition contains zero reviewer-specific references: no paths to the nine migrated reviewers' or gator's files, no per-reviewer prompts or invocation commands, and no branching keyed on a reviewer name (verified by inspection of the command definition).
- **SC-004**: A reviewer written for one harness runs unmodified under all three supported harnesses (Claude Code, Codex, OpenCode).
- **SC-005**: An invalid reviewer file in any layer never aborts a review; the review completes and the warning identifies the file.
- **SC-006**: Existing user configurations using `agents.*` or `external_tools.*` keys continue to produce the same enablement decisions, with a deprecation warning, for at least one release.
- **SC-007**: Enabling gator and reviewing a diff containing a reachable correctness defect produces at least one gator finding whose rationale names the invariant and the base-versus-head behavior change.
- **SC-008**: Every reviewer-specific flag (`--no-<name>`) and `--only` works for user-contributed reviewers without any flag list maintained in the core.

## Assumptions

- The existing finding schema, dedup, meta-review, fix loop, report, and PR posting are unchanged by this feature; plugins only change how findings are produced.
- The orchestrator (review command) remains the single place that knows how to dispatch a subagent or run a shell command per harness; plugins never encode this.
- Reviewer `name` is the stable identifier used everywhere: config keys, derived CLI flags, `source_agent`, console rows. Config keys therefore use hyphens (`reviewers.test-quality`), and legacy underscore keys are mapped for compatibility.
- The output contract appended by the core is the existing one (file, line, summary, failure_scenario, category, short_summary, severity, confidence) plus the optional `positive_observations` list for prompt reviewers, returned as a `Positive observations:` text section. Command reviewers using `output: json` must already emit the finding shape.
- The `delimited` output format covers Copilot's `### FINDING` markers. CodeRabbit's `--agent` mode prints JSON lines rather than delimited blocks, so the CodeRabbit reviewer ships in directory form with a `parser` script. Any other tool that needs more than `json` or `delimited` uses the same approach.
- Meta-review agents (skeptic, calibrator) are not reviewers: they consume findings rather than produce them, so they stay in the core and are out of scope for the plugin format.
- All plugin findings enter the fix loop under the existing severity rules; there is no per-reviewer opt-out of autonomous fixing in this version.
- Triage bot-profile configuration stays as it is; auto-deriving bot profiles from command reviewer metadata is a possible follow-up, not part of this feature.
- Remote plugin sources (git URLs, catalogs) are out of scope. Wrapping gator's OpenShell sandbox pipeline or its GitHub label state machine is out of scope.
- The gator port keeps the three-priority persona (pragmatism, user empathy, security framed with CWE / OWASP ASVS / OWASP LLM Top 10) and the pragmatic calibration rules; it drops OpenShell's project context, Fern documentation checks, Windows label routing, agent-infra sync map, and review-ledger handling. OpenShell is Apache-2.0 licensed, which permits this redistribution with attribution.
- Default enablement after migration: the six prompt reviewers and CodeRabbit and Codex default to enabled, Copilot defaults to disabled (matching the previous config template), gator defaults to disabled. These defaults live in each bundled reviewer's `enabled` frontmatter; the config template sets no `reviewers.<name>` key.
- `--parallel` stays accepted as a no-op: parallel dispatch is the default.

## Changelog

- 2026-10-14: Changes from the PR review. Project-layer reviewers are guarded: a reviewer changed by the change under review is ignored for that run (FR-008a), and project command reviewers run nothing until trusted by name and hash in `~/.cc-review/trusted-reviewers` (FR-008b). The config template no longer sets `reviewers.<name>` keys, so the frontmatter `enabled` default and an override's own `enabled` apply (FR-013, FR-018). Detection runs after enablement and selection, only for enabled command reviewers, and enabled command reviewers run concurrently (FR-020). Goal-alignment on PRs with an empty description is a declared change (FR-026). Codex keeps `command -v codex` detection without `auth_check` (FR-027). `--no-<invalid>` warns, and `--only` with only command reviewers plus `--no-external` is an error (FR-017a). Unquoted numeric or boolean `name`/`category` values are rejected (FR-005). Dedup keeps merging within the same category only, with the `dedup: isolated` field replacing the by-name exemption (FR-025, unchanged text). New edge cases record these rules and the stderr detail in detection skip reasons. The trust digest of a directory-form reviewer covers every file in its directory, and a directory with a symlink cannot be trusted (FR-008b).
- 2026-10-13: Spec evolution after verification. The edge case for a severity map value outside the scheme now describes discovery-time rejection, matching the frontmatter contract's validation rules. FR-004 states how `{files}` is quoted. FR-006b and the output contract assumption name the `Positive observations:` text section. The output format assumption records that CodeRabbit needed a `parser` script.
