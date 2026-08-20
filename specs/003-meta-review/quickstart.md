# Quickstart: Meta-Review Quality Gate

## Prerequisites

- cc-review plugin installed (`make install` from repo root)
- A git repository with changed files to review

## Validation Scenarios

### Scenario 1: Meta-review runs and filters findings

1. Run a review on a PR or branch with enough changes to produce >= 5 findings:
   ```bash
   /cc-review:review --pr <number>
   ```

2. Verify in the console output that Step 4b runs:
   ```
   Step 4b: Meta-Review (2 critics)...
   - Skeptic: N confirmed, N weak, N false-positive
   - Calibrator: N severity adjustments, N contradictions
   ```

3. Check the findings report (`review-findings.md`) for:
   - An "Agent Quality Scores" section with per-agent precision and signal-to-noise
   - Findings with `verdict` annotations
   - Any contradictions flagged with matching IDs

### Scenario 2: Meta-review skipped (below threshold)

1. Run a review on a small change that produces < 5 findings:
   ```bash
   /cc-review:review
   ```

2. Verify the console output shows:
   ```
   Step 4b: Meta-Review skipped (N findings < min_findings threshold 5)
   ```

3. Verify the findings report has no "Agent Quality Scores" section.

### Scenario 3: Meta-review disabled via CLI

1. Run a review with the skip flag:
   ```bash
   /cc-review:review --no-meta-review
   ```

2. Verify meta-review is skipped regardless of finding count.

### Scenario 4: Config override

1. Create or edit `.cc-review/config.yml`:
   ```yaml
   meta_review:
     enabled: false
   ```

2. Run a review and verify meta-review is skipped.

3. Change config to custom threshold:
   ```yaml
   meta_review:
     enabled: true
     min_findings: 3
   ```

4. Run a review with >= 3 findings and verify meta-review runs.

## Expected Artifacts

After implementation, these files should exist:

| File | Purpose |
|------|---------|
| `review/core/agents/meta-skeptic.md` | Skeptic agent prompt |
| `review/core/agents/meta-calibrator.md` | Calibrator agent prompt |
| `review/core/commands/review.md` | Updated with Step 4b, report/console changes |
| `review/core/schemas/finding.schema.json` | Extended with verdict/calibration fields |
| `review/config/config-template.yml` | Updated with meta_review section |
