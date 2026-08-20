# Feature Specification: Meta-Review Quality Gate

**Feature Branch**: `003-meta-review`

**Created**: 2026-08-14

**Status**: Draft

**Input**: Add a meta-review quality gate (Step 4b) to the cc-review pipeline that filters findings before they reach the gate check, fix loop, or PR comments. Two critic subagents (Skeptic and Calibrator) evaluate findings in parallel with fresh contexts.

## User Scenarios & Testing

### User Story 1 - Filtering False Positives Before Action (Priority: P1)

A developer runs `/cc-review:review` on a PR. The 6 review agents produce 12 findings, but 3 are false positives (the agents misread the code). The meta-review step catches these false positives and removes them before the gate check, preventing wasted fix loop rounds and noisy PR comments.

**Why this priority**: False positives are the most common quality problem. They waste developer time, erode trust in the review tool, and clutter PRs with invalid comments.

**Independent Test**: Run a review on code with known false-positive-prone patterns (e.g., intentional error swallowing with documentation). Verify that the meta-review removes findings that cite non-existent issues while keeping legitimate ones.

**Acceptance Scenarios**:

1. **Given** a review produces findings including false positives, **When** the meta-review step runs, **Then** false-positive findings are removed from the findings list before the gate check.
2. **Given** a review produces only legitimate findings, **When** the meta-review step runs, **Then** all findings pass through unchanged.
3. **Given** a finding is removed as a false positive, **Then** the removal is logged with the Skeptic's refutation reasoning citing specific code.

---

### User Story 2 - Severity Calibration (Priority: P2)

A developer runs a review and 2 findings are marked Critical, but only 1 is truly critical (the other is a Minor style concern that was over-classified). The Calibrator downgrades the inflated finding, preventing an unnecessary gate failure.

**Why this priority**: Severity inflation triggers unnecessary fix loops and REQUEST_CHANGES on PRs. Correct calibration reduces developer friction.

**Independent Test**: Run a review on code where one agent flags a naming convention as Critical. Verify the Calibrator downgrades it to Minor.

**Acceptance Scenarios**:

1. **Given** a finding has severity disproportionate to its evidence, **When** the Calibrator evaluates it, **Then** the finding's severity is adjusted to match the evidence.
2. **Given** a Critical finding with strong evidence, **When** the Calibrator evaluates it, **Then** the severity remains Critical.

---

### User Story 3 - Contradiction Detection (Priority: P2)

Two review agents produce contradictory findings about the same code (e.g., one flags a race condition, another asserts thread safety). The Calibrator flags the contradiction so the developer can see the disagreement rather than receiving two confident but opposing comments.

**Why this priority**: Contradictions between agents confuse developers and undermine trust. Surfacing them as contradictions rather than independent findings improves the review experience.

**Independent Test**: Create a code change where concurrent access patterns could be interpreted differently. Verify the Calibrator annotates the conflicting findings.

**Acceptance Scenarios**:

1. **Given** two findings reference the same file and overlapping line range with opposing assessments, **When** the Calibrator evaluates them, **Then** both findings are annotated with a contradiction flag and cross-reference.
2. **Given** findings on the same file that do not contradict each other, **When** the Calibrator evaluates them, **Then** no contradiction is flagged.

---

### User Story 4 - Agent Performance Scoring (Priority: P3)

After a review completes, the findings report and console summary include per-agent quality scores showing which agents produced high-signal findings and which produced noise.

**Why this priority**: Performance visibility enables prompt tuning and helps identify which agents need improvement. Lower priority because it is informational, not action-gating.

**Independent Test**: Run a review and verify the report contains a per-agent score table with precision estimates.

**Acceptance Scenarios**:

1. **Given** a review with meta-review enabled, **When** the findings report is generated, **Then** it includes a per-agent quality score section.
2. **Given** a review where the meta-review was skipped (below threshold or disabled), **When** the report is generated, **Then** no agent score section appears.

---

### User Story 5 - Config-Gated Activation (Priority: P1)

The meta-review only runs when enabled and when the finding count exceeds the configured threshold, avoiding overhead on small reviews.

**Why this priority**: Without gating, the meta-review would add token cost to every review including trivial ones with 1-2 findings.

**Independent Test**: Run a review with 3 findings (below default threshold of 5). Verify the meta-review step is skipped.

**Acceptance Scenarios**:

1. **Given** `meta_review.enabled` is true and findings count >= `meta_review.min_findings`, **When** the review reaches Step 4b, **Then** the meta-review runs.
2. **Given** `meta_review.enabled` is true but findings count < `meta_review.min_findings`, **When** the review reaches Step 4b, **Then** the meta-review is skipped with a log message.
3. **Given** `meta_review.enabled` is false, **When** the review reaches Step 4b, **Then** the meta-review is skipped regardless of finding count.
4. **Given** `--no-meta-review` is passed on the CLI, **When** the review reaches Step 4b, **Then** the meta-review is skipped regardless of config.

---

### Edge Cases

- What happens when all findings are removed by the meta-review? The gate check receives zero findings and passes.
- What happens when the Skeptic and Calibrator disagree about a finding (Skeptic says confirmed, Calibrator says downgrade)? The more conservative verdict wins (downgrade over confirmed, remove over downgrade).
- What happens when a meta-review subagent fails or times out? The step is skipped and all findings pass through unchanged. A warning is logged.
- What happens when exactly `min_findings` findings exist? The meta-review runs (threshold is >= not >).

## Requirements

### Functional Requirements

- **FR-001**: System MUST insert a new Step 4b in `review.md` between merge/dedup (Step 4) and gate check (Step 5)
- **FR-002**: Step 4b MUST dispatch exactly 2 subagents (Skeptic and Calibrator) in parallel using the Agent tool, each with a fresh context
- **FR-003**: The Skeptic agent MUST evaluate each finding and produce a verdict of `confirmed`, `weak`, or `false-positive`, citing specific code evidence for non-confirmed verdicts
- **FR-004**: The Calibrator agent MUST evaluate severity proportionality for each finding and produce a calibrated severity
- **FR-005**: The Calibrator agent MUST detect contradictions between findings that reference the same file and overlapping line ranges with opposing assessments
- **FR-006**: The Calibrator agent MUST produce per-agent quality scores including precision estimate and signal-to-noise ratio
- **FR-007**: The orchestrator MUST apply verdicts after both subagents complete: remove `false-positive` findings, apply the Calibrator's calibrated severity to `weak` findings (if no calibrated severity exists, lower severity by one level, with Minor as the floor), annotate contradictions
- **FR-008**: When the Skeptic and Calibrator produce conflicting assessments for the same finding, the more conservative verdict MUST win
- **FR-009**: Agent quality scores MUST be included in the findings report (Step 7) and console summary (Step 8)
- **FR-010**: The meta-review MUST be gated by config: `meta_review.enabled` (default true) and `meta_review.min_findings` (default 5)
- **FR-011**: The `--no-meta-review` CLI flag MUST skip the meta-review regardless of config settings
- **FR-012**: Agent prompt files MUST be created at `core/agents/meta-skeptic.md` and `core/agents/meta-calibrator.md`
- **FR-013**: Findings MUST include the `source_agent` field when passed to the critics (not anonymized), as agent identity is needed for per-agent scoring
- **FR-014**: If either subagent fails or times out, the meta-review step MUST be skipped and all findings MUST pass through unchanged with a warning logged. Subagent timeouts inherit from the harness defaults (same as review agents)

### Key Entities

- **Finding**: An issue discovered by a review agent, with severity, confidence, file, line range, category, description, and source agent. Extended with meta-review verdict and calibrated severity.
- **Verdict**: The Skeptic's assessment of a finding: `confirmed` (real issue), `weak` (evidence insufficient for claimed severity), or `false-positive` (not a real issue).
- **Agent Score**: Per-agent quality metrics: precision (findings confirmed / total findings), signal-to-noise ratio (confirmed + weak / total), finding count.
- **Contradiction**: A pair of findings from different agents on the same code region with opposing assessments.

### Schema Extensions

The finding schema (`core/schemas/finding.schema.json`) MUST be extended with the following optional properties:

| Field | Type | Description |
|---|---|---|
| `verdict` | `string` enum: `confirmed`, `weak`, `false-positive` | Skeptic's assessment of finding validity |
| `verdict_reasoning` | `string` | Skeptic's code-cited justification for non-confirmed verdicts |
| `calibrated_severity` | `string` enum: same as `severity` | Calibrator's adjusted severity (present only when changed) |
| `calibration_reasoning` | `string` | Calibrator's justification for severity adjustment |
| `contradiction_id` | `string` pattern: `^CONTRA-[0-9]+$` | Links contradictory findings into a pair |

Agent scores are NOT part of the finding schema. They are a separate output structure included in the report (Step 7) and console summary (Step 8).

## Success Criteria

### Measurable Outcomes

- **SC-001**: Every finding removed or severity-adjusted by the meta-review includes a code-cited justification in the report
- **SC-002**: The meta-review step completes within the time it takes for the slowest review agent (parallel execution, not additive)
- **SC-003**: Every finding removal or severity change is accompanied by a specific code citation in the report
- **SC-004**: Agent quality scores are visible in every review report when meta-review runs
- **SC-005**: Reviews with fewer than the configured threshold of findings skip the meta-review with zero overhead

## Clarifications

### Session 2026-08-14

- Q: What timeout should apply to meta-review subagents? → A: Inherit from harness defaults (same as review agents)

## Out of Scope

- Meta-review does not re-evaluate external tool findings (CodeRabbit, Copilot); those pass through unchanged
- Meta-review does not influence the deduplication step (Step 4); it operates on already-deduplicated findings
- No persistent learning or cross-review calibration; each meta-review is stateless

## Assumptions

- The existing finding schema (`core/schemas/finding.schema.json`) can be extended with verdict and calibration fields without breaking existing consumers
- The Agent tool is available in all harnesses where cc-review runs (Claude Code, OpenCode, Codex)
- Two additional subagent calls per review is an acceptable token cost tradeoff for quality improvement
- The `source_agent` field on findings provides sufficient information for per-agent scoring (no need for additional agent metadata)
- Config defaults (enabled=true, min_findings=5) provide the right balance between quality and overhead for typical reviews
