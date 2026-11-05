# Write a command reviewer

<!-- Sources:
cc-review:review/core/reviewers/greptile/reviewer.md:1-19
cc-review:review/core/reviewers/greptile/reviewer.md:20-41
cc-review:review/core/reviewers/greptile/reviewer.md:43-53
cc-review:review/core/reviewers/greptile/parse.sh:1-10
cc-review:review/core/reviewers/greptile/parse.sh:18-28
cc-review:docs/reviewer-plugins.md:24
cc-review:docs/reviewer-plugins.md:36-37
cc-review:docs/reviewer-plugins.md:138-153
cc-review:docs/reviewer-plugins.md:196
cc-review:review/core/schemas/reviewer.schema.json:13-33
cc-review:review/core/schemas/reviewer.schema.json:40-54
cc-review:review/core/schemas/reviewer.schema.json:67-109
-->

A command reviewer wraps an external command-line tool, such as a linter or a hosted review service, so its output becomes cc-review findings that join the ones the built-in agents report. It uses `kind: command` rather than `kind: prompt`. In place of a prompt, its frontmatter declares how to detect the tool, how to run it, and how to turn its output into findings, and the body holds parsing notes for the orchestrator.

cc-review ships Greptile as a bundled command reviewer in `review/core/reviewers/greptile/`. The reviewer wraps the `greptile` CLI to review the committed diff and fold the results into the report. Its directory is a complete worked example, so the steps below walk through it field by field. Build your own command reviewer the same way: drop its directory into `.cc-review/reviewers/` for one project, or `~/.cc-review/reviewers/` for every project.

1. **Use the directory form.** A command reviewer that ships a parser script uses the directory form, a `reviewer.md` beside the parser in a directory named for the reviewer. The Greptile reviewer's directory holds `reviewer.md` and a parser named `parse.sh`.

2. **Declare the frontmatter.** The frontmatter is the whole contract for running the tool. Greptile's reads:

   ```yaml
   ---
   name: greptile
   display_name: "Greptile"
   kind: command
   category: external
   enabled: false
   detect: "command -v greptile"
   auth_check: "greptile whoami >/dev/null && greptile init --json >/dev/null"
   invoke: "greptile review --json --agent -b {base_branch}"
   timeout_seconds: 540
   severity_map:
     P0: Critical
     P1: Important
     P2: Minor
     P3: Notable
   output:
     format: parser
     parser: parse.sh
   ---
   ```

   Each field has a job:

   - `kind: command` marks the reviewer as a tool wrapper. `name`, `display_name`, and `category` behave as they do for a prompt reviewer, and here `category: external` is written to every Greptile finding.
   - `enabled: false` leaves the reviewer off until you turn it on, because every Greptile run spends credits (a base review costs one).
   - `detect` is a shell check that runs before dispatch. Exit 0 means the tool is available; any other exit skips the reviewer with the reason `not available`. Greptile's `command -v greptile` confirms the CLI is on `PATH`.
   - `auth_check` is an optional shell check that runs after `detect`. A non-zero exit skips the reviewer with `not authenticated`, and the last line the check wrote to stderr is appended to the reason. Greptile's check confirms a login and that the repository is connected to a Greptile organization; `greptile init --json` exits 1 for a repository that is not connected, so an unconnected repository is skipped rather than failed.
   - `invoke` is the command template. cc-review substitutes three placeholders, `{base_branch}`, `{files}`, and `{pr_number}`. Greptile uses only `{base_branch}`; `--json` selects machine output and `--agent` suppresses prompts, browser sign-in, and update notices.
   - `timeout_seconds` is the wall-clock bound on the invoke command (the default is 120). Greptile sets 540, because a base review of a roughly 3,000 line diff took about 200 seconds and the harness caps a single call at 600 seconds.
   - `severity_map` translates the tool's native severity names into cc-review's four levels: Critical, Important, Minor, or Notable. Greptile maps `P0` through `P3`. A native value absent from the map passes through only when it is already a cc-review severity, and is otherwise dropped with a warning.
   - `output.format` says how raw output becomes findings, one of `json`, `delimited`, or `parser`. Greptile prints a single JSON object that needs reshaping, so it uses `parser` and names `parse.sh`.

3. **Write the parser.** `greptile review --json` prints one JSON object with a `comments` array, alongside summary fields that cc-review ignores. A `parser` script reads that raw output on standard input and prints cc-review's `json` finding shape on standard output. The script runs through its own shebang, so any language works. The core of `parse.sh` builds each finding from one comment inside a `jq` `map(...)`:

   ```sh
   | {
       file: .path,
       line: $line,
       line_end: $line_end,
       severity: .severity,
       description: ($first | gsub("^\\s*\\*\\*|\\*\\*\\s*$"; "")),
       rationale: $body,
       confidence: 75
     }
   + (if (.suggestion | type) == "string" and .suggestion != "" then {fix: .suggestion} else {} end)
   ```

   The parser builds each finding like this:

   - `path` becomes `file`, and `startLine` and `endLine` become `line` and `line_end`.
   - The comment body's bold title line becomes `description`, and the whole body becomes `rationale`.
   - A non-empty `suggestion` becomes `fix`.
   - `confidence` is fixed at 75 for every finding, because Greptile's top-level confidence is a merge-readiness score for the whole change, not a per-finding value.

   When standard input is empty, holds more than one value, or is not a review object with a `comments` array, the parser exits non-zero, and the review records a parse error rather than reading a failed run as a clean one.

4. **Enable it and check the preconditions.** Greptile is off by default, so a plain run skips it. A `kind: command` reviewer in a project's `.cc-review/reviewers/` also runs none of its commands until you trust it. Enabling a reviewer and trusting a project command reviewer are both covered in [Trust and configuration](trust-and-config.md). Greptile reviews committed changes only, and the repository's remote must be connected to a Greptile organization, or the `auth_check` skips it.

Check: the parser turns one Greptile comment into a cc-review finding that carries the file path.

```bash
printf '%s' '{"comments":[{"path":"src/app.js","startLine":10,"endLine":12,"severity":"P1","body":"**Null deref**\nvalue may be null","suggestion":"guard the value"}]}' | review/core/reviewers/greptile/parse.sh
```
<!-- expect: contains "src/app.js" -->

> [!NOTE]
> This page was verified against cc-review <!-- guide:attr cc-review-version -->1.4.0<!-- /guide:attr -->.
