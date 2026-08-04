# Brainstorm: External Reviewer Abstraction

**Date:** 2026-08-04
**Status:** active

## Problem Framing

External review tools (CodeRabbit, Copilot, Codex) are currently hardcoded in `review.md` with tool-specific invocation commands, output parsing, and severity mapping. Adding a new external reviewer requires editing the review command directly, adding detection logic, and wiring up output parsing. There is no plugin-like interface for registering new reviewers.

The user wants an abstraction that makes adding a new external reviewer as easy as dropping in a definition file, without modifying the core review command. Precondition detection (is the tool installed? is it authenticated?) should be part of the abstraction.

Depends on brainstorm #02 (config-system) for reviewer configuration entries.

## Approaches Considered

### A: Descriptor Files (Recommended)

Each external reviewer is defined by a YAML descriptor file in `review/core/reviewers/<name>.yml`. The descriptor specifies: name, detection command, invocation command, output format, severity mapping, and authentication check. The review command dynamically discovers and dispatches all descriptors.

- Pros: No code changes to add a new reviewer. Declarative. Easy to understand. Config system controls which are enabled.
- Cons: Limited to what the descriptor schema supports. Complex reviewers may need escape hatches.

### B: Shell Script Plugins

Each reviewer is a shell script in `review/core/reviewers/<name>.sh` that implements a standard interface (detect, invoke, parse). The review command sources and calls each script.

- Pros: Maximum flexibility. Scripts can handle any complexity.
- Cons: More code to write per reviewer. Interface contract is implicit (no schema).

### C: Hybrid (Descriptor + Optional Script)

YAML descriptor for the common case. Optional companion script (`<name>.sh`) for custom parsing or invocation logic that the descriptor can't express.

- Pros: Simple reviewers stay declarative. Complex ones get escape hatches.
- Cons: Two file types to understand. Slightly more complex discovery logic.

## Decision

**Chosen: Approach A (Descriptor Files)** with the understanding that if a reviewer needs custom parsing beyond what the descriptor supports, a parsing script path can be specified in the descriptor as an optional field.

## Key Requirements

### Reviewer Descriptor Schema

```yaml
name: coderabbit
display_name: "CodeRabbit"
bot_login: "coderabbitai[bot]"

detection:
  command: "command -v coderabbit"
  auth_check: "coderabbit auth status"

invocation:
  command: "coderabbit review --agent --files {files}"
  timeout_seconds: 120

output:
  format: "delimited"
  delimiter: "============="
  fields:
    file: "file"
    line: "line"
    severity: "severity"
    description: "description"
    rationale: "rationale"

severity_mapping:
  critical: "Critical"
  major: "Important"
  minor: "Minor"
  info: "Notable"

defaults:
  enabled: true
  confidence: 75
  category: "external"
```

### Discovery and Dispatch

- Review command scans `review/core/reviewers/*.yml` at startup
- Filters by config (`external_tools.<name>: true/false`)
- Runs detection command to verify tool is available
- Dispatches enabled + detected reviewers alongside internal agents
- Parses output using the descriptor's format specification

### Precondition Detection

- `detection.command`: Check if the tool binary exists
- `detection.auth_check`: Verify authentication (optional, only run if command exists)
- Init skill (`/cc-review:init`) runs all precondition checks and reports status

### Integration with Config System

- `external_tools.<name>: true/false` in config enables/disables each reviewer
- Descriptor's `defaults.enabled` provides the default when not specified in config
- CLI flags (`--no-<name>`) override config for individual reviewers

### Triage Integration

- `bot_login` in the descriptor tells triage how to identify this reviewer's threads
- Triage auto-discovers reviewer descriptors to build its bot profile list (instead of hardcoding)

## Open Questions

- Should the descriptor support multiple output formats (structured JSON vs delimited text vs free-form)?
- Should there be a "test" subcommand that runs a reviewer's detection + auth check + sample invocation?
- How should reviewer descriptors handle tools that post directly to the PR (like CodeRabbit's bot) vs tools that output to stdout?
- Should the abstraction support internal agents too (unifying the dispatch model), or stay external-only?
