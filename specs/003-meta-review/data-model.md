# Data Model: Meta-Review Quality Gate

## Entities

### Finding (extended)

The existing Finding entity gains 5 optional fields from the meta-review step. All existing fields remain unchanged.

**New fields** (all optional, only present when meta-review ran):

| Field | Type | Description |
|-------|------|-------------|
| `verdict` | string enum: `confirmed`, `weak`, `false-positive` | Skeptic's assessment of finding validity |
| `verdict_reasoning` | string | Skeptic's code-cited justification for non-confirmed verdicts |
| `calibrated_severity` | string enum: `Critical`, `Important`, `Minor`, `Notable` | Calibrator's recommended severity (may differ from original) |
| `calibration_reasoning` | string | Calibrator's justification for severity adjustment |
| `contradiction_id` | string | Shared ID linking contradictory findings (e.g., `CONTRADICTION-1`) |

**Lifecycle**: Fields are populated in Step 4b after both critics complete. The orchestrator then applies verdicts: findings with `verdict=false-positive` are removed from the list, findings with `verdict=weak` have their `severity` replaced by `calibrated_severity`.

### Agent Score

A new entity computed by the Calibrator during Step 4b. Not persisted in the finding schema; exists only in the report output.

| Field | Type | Description |
|-------|------|-------------|
| `agent_name` | string | Name of the review agent (e.g., `correctness`, `security`) |
| `total_findings` | integer | Number of findings this agent produced |
| `confirmed` | integer | Findings with verdict `confirmed` |
| `weak` | integer | Findings with verdict `weak` |
| `false_positives` | integer | Findings with verdict `false-positive` |
| `precision` | float (0-1) | `confirmed / total_findings` |
| `signal_to_noise` | float (0-1) | `(confirmed + weak) / total_findings` |

### Contradiction

A logical grouping, not a separate stored entity. Two findings form a contradiction when:
1. They reference the same file
2. Their line ranges overlap (within 5-line tolerance)
3. Their assessments are opposing (e.g., one claims an error exists, the other claims the code is correct)

Both findings receive the same `contradiction_id` value.

## Config Model

New section in `config-template.yml`:

```yaml
meta_review:
  enabled: true       # Enable/disable the meta-review step
  min_findings: 5     # Minimum finding count to trigger meta-review
```

CLI override: `--no-meta-review` sets `meta_review.enabled=false`.

## State Transitions

```
Findings (from Step 4: Merge/Dedup)
  │
  ├─ meta_review.enabled=false OR count < min_findings
  │   └─ Pass through unchanged to Step 5
  │
  └─ meta_review.enabled=true AND count >= min_findings
      │
      ├─ Dispatch Skeptic + Calibrator in parallel
      │
      ├─ Either subagent fails/times out
      │   └─ Pass through unchanged + warning to Step 5
      │
      └─ Both complete
          │
          ├─ Apply verdicts:
          │   ├─ false-positive → remove from list
          │   ├─ weak → replace severity with calibrated_severity
          │   └─ confirmed → unchanged
          │
          ├─ Annotate contradictions
          │
          ├─ Compute agent scores
          │
          └─ Filtered findings → Step 5 (Gate Check)
```
