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
Parsing notes for CodeRabbit CLI output.

`coderabbit review --agent` prints JSON lines (one object per line) with a
`type` field: `review_context`, `status`, `heartbeat`, `finding`, and
`complete`. `parse.sh` keeps the `finding` objects and converts them to
cc-review's `json` finding shape:

- `fileName` becomes `file`.
- The line range is taken from the header line of the `codegenInstructions`
  text, `Review comment at @<path> around lines <start> - <end>:` or
  `... at line <n>:`; `line` is the start, `line_end` the end. Line numbers
  mentioned in the comment body are ignored. Without a header, `line` is 1.
- The text after that header line is the review comment: its first line is
  `description`, the whole comment is `rationale`.
- `severity` uses CodeRabbit's vocabulary (critical, major, minor, info,
  trivial, none) and is translated through `severity_map`.
- `confidence` is 75 for every finding.
- A `complete` object with `findings: 0` means a clean run; the parser emits
  an empty array. A stream with an `error` or `action_required` object, or
  without a `complete` object (failed or truncated run), makes the parser exit
  non-zero, which the review reports as a parse error instead of a clean run.
- Real agent-mode runs take several minutes on a large diff, hence the
  540 second bound (below a 600 second per-call harness limit).
