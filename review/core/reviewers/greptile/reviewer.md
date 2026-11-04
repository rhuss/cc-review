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
Parsing notes for Greptile CLI output.

`greptile review --json` prints one JSON object with `summary`, `confidence`,
`confidenceReasoning`, `securitySummary`, `effort`, and a `comments` array.
`--agent` suppresses prompts, browser sign-in, and update notices. `parse.sh`
converts each comment to cc-review's `json` finding shape:

- `path` becomes `file`; `startLine` and `endLine` become `line` and
  `line_end`.
- Comments on removed lines (`side: "old"`) carry old-file line numbers and
  are anchored at the start of their hunk in the new file
  (`hunk.newRange.start`).
- `body` starts with a bold title line (`**Title**`); the title without the
  bold markers is `description`, the whole body is `rationale`.
- A non-empty `suggestion` becomes `fix`.
- `severity` uses Greptile's vocabulary (`P0` to `P3`) and is translated
  through `severity_map`.
- `confidence` is 75 for every finding. Greptile's top-level `confidence` is a
  1 to 5 merge-readiness score for the whole change, not a per-finding value,
  and is ignored together with the summary fields.
- Output that is empty or not a single object with a `comments` array makes
  the parser exit non-zero, which the review reports as a parse error.

Operational notes:

- Greptile reviews committed changes only (merge base of `{base_branch}`
  through `HEAD`), like CodeRabbit with `--committed`.
- The repository's remote must be connected to a Greptile organization. The
  `auth_check` runs `greptile init --json`, which exits 1 for a repository
  that is not connected, so the reviewer is skipped instead of failing.
- Every run spends Greptile credits (a Base review costs 1), so the reviewer
  is disabled by default. Enable it with `greptile: true` in the config.
- A Base review of a ~3,000 line diff took about 200 seconds, hence the 540
  second bound (below a 600 second per-call harness limit).
