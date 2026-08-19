# Brainstorm: Meta-Reviewer for Review Quality Assessment

**Date:** 2026-08-14
**Status:** active

## Problem Framing

The cc-review pipeline dispatches 6 specialized review agents that produce findings independently. There is no quality control on the findings themselves before they reach the gate check, fix loop, or PR comments. Problems observed in practice:

- False positives that waste fix loop rounds or clutter PR comments
- Severity inflation (Minor issues flagged as Critical)
- Contradictions between agents (one says "race condition", another says "thread-safe by design")
- No visibility into which agents are producing signal vs noise over time

A meta-reviewer layer would act as quality assurance on the review output, filtering bad findings and tracking agent performance.

## Approaches Considered

### A: Inline Step with Parallel Critics (chosen, with config gating from B)

Add Step 4b to review.md between merge/dedup and gate check. Dispatch 2 subagents in parallel, each with a fresh context:

- **Skeptic**: Gets all findings + the code. Adversarially tries to refute each finding. Produces per-finding verdicts: confirmed, weak (downgrade), or false-positive (remove). Must cite specific code.
- **Calibrator**: Gets all findings + the code. Checks severity proportionality. Flags contradictions between findings. Produces per-agent quality scores (precision estimate, signal-to-noise).

Orchestrator applies verdicts, agent scores go into the report.

Config-gated: `meta_review.enabled` (default true), `meta_review.min_findings` (default 5), `--no-meta-review` CLI flag.

- Pros: Clean pipeline integration, fresh contexts, parallel execution, findings filtered before any action
- Cons: Adds token cost (2 extra subagent calls), mitigated by min_findings threshold

### B: Config-Gated Optional Step

Same mechanism as A but default disabled, discovery problem. Folded into A as the config layer.

### C: Standalone Post-Review Command

Separate `/cc-review:meta-review` command, runs after the fact. Cannot filter findings before gate/PR. Useful for auditing but not for quality control. Deferred as a possible future addition.

## Decision

**Approach A with config gating from B.** Two critics (Skeptic + Calibrator) dispatched as parallel subagents with fresh contexts in a new Step 4b. Config-gated with min_findings threshold.

## Key Requirements

- New Step 4b in review.md between merge/dedup (Step 4) and gate check (Step 5)
- 2 critic subagents dispatched in parallel with fresh contexts (Agent tool, not inline)
- Skeptic agent: adversarial refutation, per-finding verdicts (confirmed/weak/false-positive)
- Calibrator agent: severity calibration, contradiction detection, per-agent quality scores
- Orchestrator applies verdicts: downgrades weak findings, removes false positives, annotates contradictions
- Agent quality scores included in findings report (Step 7) and console summary (Step 8)
- Config: `meta_review.enabled` (default true), `meta_review.min_findings` (default 5)
- CLI flag: `--no-meta-review` to skip
- Agent prompt files: `core/agents/meta-skeptic.md`, `core/agents/meta-calibrator.md`

## Open Questions

- Should the critics see which agent produced each finding, or should findings be anonymized to prevent bias?
- What is the exact schema for verdict output (per-finding verdict + agent score structure)?
- Should quality scores influence future reviews (e.g., confidence multiplier for noisy agents)?
