---
name: codex
display_name: "Codex"
kind: command
category: external
enabled: true
detect: "command -v codex"
invoke: "codex review --base {base_branch}"
timeout_seconds: 180
severity_map:
  P0: Critical
  P1: Important
  P2: Minor
  P3: Notable
output:
  format: delimited
  delimiter: "\n\n"
  fields:
    file: "File"
    line: "Line"
    severity: "Severity"
    description: "Description"
    rationale: "Rationale"
---
Parsing notes for Codex CLI output.

Codex CLI output is not stable across versions: findings may arrive as
labeled blocks, as markdown bullets with `path:line` references, or as prose
paragraphs separated by blank lines. The declared `delimited` format with a
blank-line delimiter and best-effort labels is a starting point, not a
guarantee.

For each paragraph that references a source file:

- Extract `file` and `line` from a `path:line` or `path:start-end` reference
  (use the start of a range as `line`).
- Current `codex review` output tags each finding title with a priority
  `[P0]` to `[P3]`; report that tag without brackets (`P0` ... `P3`) as the
  native severity, which `severity_map` translates.
- Otherwise extract `severity` from an explicit label or from wording such as "critical",
  "bug", "must fix" (Critical or Important), "consider", "nit", "style" (Minor).
  Values that are neither a `P0`-`P3` tag nor a cc-review severity are
  dropped, so normalize to `Critical`, `Important`, or `Minor` before reporting.
- Use the first sentence as `description` and the rest of the paragraph as
  `rationale`.
- Paragraphs without a file reference (overall summary, verdict) are not
  findings.
- Default `confidence` to 75 for every finding.
