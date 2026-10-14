# Brainstorm: Pluggable Reviewers

**Date:** 2026-10-13
**Status:** active
**Supersedes:** #03 (reviewer-abstraction)

## Problem Framing

cc-review hard-codes its reviewers. The six internal agents are listed by name in `review/core/commands/review.md`, each with its own config toggle, and the three external CLI tools (CodeRabbit, Copilot CLI, Codex CLI) each have bespoke detection, invocation, and output parsing inline in the same file. Adding a reviewer means editing the core command, the config template, the CLI flag list, and the console summary table.

The goal is to make reviewers pluggable so that users and the community can contribute new review perspectives by dropping in a file, without touching the core. The mechanism should be as harness-agnostic as the rest of cc-review: a plugin must work unchanged under Claude Code, Codex, and OpenCode.

### First use case: gator (NVIDIA/OpenShell)

Research into https://github.com/NVIDIA/OpenShell (commit 5e414ea) showed that "gator" is not a drop-in reviewer skill. It is a headless GitHub issue/PR gatekeeper: a `gator:*` label state machine that runs inside an OpenShell sandbox under Codex CLI only, launched via `scripts/agents/run.sh --agent gator`, hard-coded to the NVIDIA/OpenShell repository. It never pushes fixes and runs no tests.

The actual code review inside gator is delegated to a sub-agent defined in `.claude/agents/principal-engineer-reviewer.md` (274 lines, prompt-only, tools Read/Grep/Glob/Bash). That reviewer emits a JSON envelope defined in `skills/gator-gate/references/review-findings-schema.md`:

- Severity: Critical / Warning / Suggestion
- Stable finding IDs `GATOR-<head8>-<nn>` carried across review rounds
- An evidence contract per finding: invariant, attacker or operator prerequisite, supported entry point, sink, changed location, base behavior, head behavior, observable impact, reproducer, PR ownership, requested change, scope (`latest_delta` / `carried` / `unchanged_critical`), sibling sites
- A `jq` validator (`bin/validate-review-findings`) downgrades any Critical or Warning missing an evidence field to a non-blocking `hypothesis`

The portable pieces are the reviewer prompt, the findings contract, and the calibration rules ("block only on concrete, reachable, PR-owned, material problems with a proportionate fix"). Decision: port the reviewer prompt as the first contributed plugin. Wrapping gator's sandbox pipeline is out of scope.

## Approaches Considered

### A: Single markdown file with YAML frontmatter, plus directory escape hatch (chosen)

A reviewer is `reviewers/<name>.md`. Frontmatter carries metadata, the body is the prompt. For reviewers that need supporting files, the alternative form `reviewers/<name>/reviewer.md` with sibling files is allowed. Same shape as a SKILL.md or a harness agent file.

- Pros: one file per reviewer, droppable into any discovery directory. Harness-agnostic by construction since the prompt body never names harness tools. Familiar to anyone who has written a skill or agent definition. The six built-ins migrate by adding a frontmatter block each.
- Cons: `command`-kind reviewers with non-trivial output parsing need the directory form to hold a parser script. Two valid layouts to document.

### B: Directory per reviewer with manifest.yml

`reviewers/<name>/manifest.yml` + `prompt.md` + optional `scripts/`, `references/`. Mirrors OpenShell's `agent.yaml` layout.

- Pros: room for supporting files. Clean separation of metadata and prompt.
- Cons: heavier for the common case. Six directories with two files each for the built-ins. More ceremony for a contributor who just wants to add a prompt.

### C: YAML descriptor pointing at a prompt file (#03 extended)

`reviewers/<name>.yml` with a `prompt:` field. Direct continuation of brainstorm #03.

- Pros: pure data, validatable with a JSON schema.
- Cons: two files per prompt reviewer, paired by convention. Less familiar than the frontmatter pattern every harness already uses.

## Decision

**Chosen: Approach A** with the directory form from B as an escape hatch. Gator ships in the directory form because it carries a reference schema, which also demonstrates the escape hatch.

Further decisions made during the session:

- **Unify**: the six built-in agents and the three external CLI tools migrate to the plugin format. `review.md` dispatches whatever discovery returns instead of a hard-coded list.
- **Two kinds**: `kind: prompt` (dispatched as a fresh-context subagent) and `kind: command` (shell out, detect, invoke, parse). One discovery and config model for everything that produces findings.
- **Three discovery layers**, same precedence as config: project `.cc-review/reviewers/`, then user `~/.cc-review/reviewers/`, then bundled `review/core/reviewers/`. A reviewer with the same name in a higher layer overrides the lower one.
- **Brainstorm #03 is superseded** by this document.

## Key Requirements

### Plugin format

```yaml
---
name: gator
display_name: "Gator (Principal Engineer)"
kind: prompt                 # prompt | command
category: external           # finding category written into each finding
enabled: true                # default; overridable via config and CLI
requires: [pr]               # optional preconditions: pr, spec, gh, binary:<name>
severity_map:                # optional, when the prompt uses its own scheme
  Warning: Important
  Suggestion: Minor
---
<prompt body for kind: prompt>
```

For `kind: command`, the frontmatter additionally carries detection (`detect`, optional `auth_check`), invocation (`invoke`, `timeout_seconds`), and output parsing (`output.format` plus field mapping). The body is empty or holds parsing notes. A `parser:` field may point to a script in the directory form.

Alternative layout: `reviewers/<name>/reviewer.md` with arbitrary sibling files (references, scripts).

### Harness independence

- Plugin bodies never reference harness tool names (no `ReportFindings`, no `Agent`). The orchestrator appends the common preamble and the output contract at dispatch time, as it does today for the six built-ins.
- Dispatch mechanism (subagent vs. shell) stays in the core orchestrator, which already adapts per harness.

### Discovery and dispatch

- Scan the three layers, merge by name with higher layer winning, validate frontmatter, skip and warn on invalid plugins.
- Evaluate `requires` preconditions; skip with a logged reason when unmet (replaces the ad-hoc `GOALS_AVAILABLE` and `*_AVAILABLE` checks).
- Dispatch all enabled, satisfied `prompt` reviewers in a single parallel response as fresh-context subagents. Run `command` reviewers alongside.
- Console summary and findings report list reviewers by `display_name` from discovery, not from a hard-coded table.

### Configuration

- `agents.*` and `external_tools.*` collapse into `reviewers.<name>: true|false`.
- CLI flags `--no-<name>` and `--only <name,...>` derived from discovered names. `--no-external` disables all `kind: command` reviewers.
- `/cc-review:init` lists discovered reviewers and runs their precondition checks.

### Built-in migration

- `core/agents/{correctness,architecture,security,production,test-quality,goal-alignment}.md` move to `core/reviewers/` with frontmatter. Goal alignment declares `requires: [pr]`.
- CodeRabbit, Copilot CLI, Codex CLI become `kind: command` reviewers in `core/reviewers/`, carrying the detection, invocation, and parsing rules currently inline in `review.md`.

### Gator plugin

- `core/reviewers/gator/reviewer.md` ported from OpenShell's `principal-engineer-reviewer.md`, plus `references/findings-contract.md` adapted from `review-findings-schema.md`.
- Strip OpenShell specifics: Rust/Python project context, Fern docs check, Windows label routing, `sync-agent-infra` map, review-ledger handling.
- Keep: the three-priority persona (pragmatism, user empathy, security with CWE / OWASP ASVS / LLM Top 10), the pragmatic calibration rules, grouping equivalent cases under one invariant.
- Require the evidence fields (invariant, prerequisite, entry point, sink, base vs head behavior, impact, reproducer, PR ownership) as the content of `rationale` and `failure_scenario`.
- Severity map: Critical to Critical, Warning to Important, Suggestion to Minor.
- Attribution to the upstream source in the plugin file.

## Open Questions

- Exact frontmatter schema and validation: a JSON schema for the frontmatter, and how strictly to reject unknown fields?
- How does `kind: command` express output parsing without a script (delimited / JSON / regex), and when is a `parser:` script required?
- Do the meta-review agents (skeptic, calibrator) also become plugins, or stay core? They currently hard-code `ReportFindings`.
- Config migration: keep `agents.*` and `external_tools.*` as deprecated aliases for one release, or break cleanly?
- Should a plugin be able to opt its findings out of the autonomous fix loop (gator is review-only upstream)?
- Should triage auto-discover bot profiles from `kind: command` reviewer metadata (carried over from #03)?
- Remote plugin sources (git URLs in config, community catalog): parked for a later brainstorm.
