---
name: copilot
display_name: "Copilot"
kind: command
category: external
enabled: false
detect: "command -v copilot"
auth_check: "! command -v gh >/dev/null 2>&1 || gh auth status"
invoke: >-
  copilot -s -p "Review the git diff between {base_branch} and HEAD for bugs,
  security issues, and code quality problems. Report each problem as a separate
  block that starts with a line '### FINDING' followed by these lines:
  'File: <relative path>', 'Line: <line number>', 'Severity: <Critical|Important|Minor>',
  'Description: <what is wrong>', 'Rationale: <why it matters>'.
  Report nothing else and do not include praise."
timeout_seconds: 180
output:
  format: delimited
  delimiter: "### FINDING"
  fields:
    file: "File"
    line: "Line"
    severity: "Severity"
    description: "Description"
    rationale: "Rationale"
---
Parsing notes for Copilot CLI output.

The prompt in `invoke` asks Copilot to emit one `### FINDING` block per issue
with `File`, `Line`, `Severity`, `Description`, and `Rationale` lines. Text
before the first delimiter is preamble and is ignored.

- Discard findings whose `File` is under `specs/`; those are specification
  documents, not code.
- Severities are expected in cc-review vocabulary already (`Critical`,
  `Important`, `Minor`); anything else is dropped by the identity severity map.
- When Copilot ignores the format and prints prose, treat the output as a
  parse error: the reviewer is marked `failed (parse error)` and the review
  continues.
- Default `confidence` to 75 for every finding.
