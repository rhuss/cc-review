# Research: Meta-Review Quality Gate

## R-001: Verdict Schema Design

**Decision**: Extend the existing finding schema with 5 optional fields rather than creating a separate verdict schema.

**Rationale**: The finding object already flows through the entire pipeline (merge, gate, fix loop, report, PR posting). Adding optional fields keeps the data model flat and avoids a separate join between findings and verdicts. Optional fields mean existing consumers that don't read them are unaffected.

**Alternatives considered**:
- Separate verdict.schema.json with finding ID references: Rejected because it requires lookups and introduces coupling between two schema files.
- Inline verdict object as a nested property: Rejected because it breaks the flat structure that `jq` pipelines expect.

## R-002: Skeptic Agent Prompt Design

**Decision**: The Skeptic receives the full findings list and the list of changed files. For each finding, it reads the referenced file and line range, then attempts to refute the finding by identifying contradicting evidence in the code.

**Rationale**: The Skeptic needs both the finding's claim and the actual code to verify. Reading files independently (rather than receiving pre-read code) ensures the Skeptic forms its own understanding without the original agent's framing bias.

**Alternatives considered**:
- Pass pre-read code snippets in the prompt: Rejected because the original agent chose which lines to read, potentially missing exculpating context.
- Have the Skeptic re-run the full review: Rejected because it duplicates work and defeats the purpose of targeted verification.

## R-003: Calibrator Agent Prompt Design

**Decision**: The Calibrator receives the full findings list with source_agent metadata. It evaluates severity proportionality by comparing each finding's severity claim against the evidence strength, and scans for contradictions by grouping findings by file and line range.

**Rationale**: The Calibrator needs source_agent to compute per-agent scores. Contradiction detection requires seeing all findings together (cannot be done per-finding in isolation).

**Alternatives considered**:
- Anonymize source_agent: Rejected because per-agent scoring is a core requirement (FR-006, FR-013).

## R-004: Verdict Conflict Resolution

**Decision**: When the Skeptic and Calibrator produce different assessments for the same finding, the more conservative verdict wins. Conservation hierarchy: false-positive > weak > confirmed.

**Rationale**: False negatives (missing a real bug) are less costly than false positives (wasting developer time on non-issues). If either critic doubts a finding, that doubt should prevail.

**Alternatives considered**:
- Majority vote (would need 3 critics): Rejected in brainstorm phase to keep the panel lean.
- Always trust the Skeptic over the Calibrator: Rejected because the Calibrator may have better severity context.

## R-005: Config Integration

**Decision**: Add a `meta_review` section to `config-template.yml` with `enabled` (default true) and `min_findings` (default 5). CLI flag `--no-meta-review` overrides config.

**Rationale**: Follows the existing config resolution pattern (CLI > config > defaults). The `min_findings` threshold avoids overhead on small reviews where false positives are unlikely.

**Alternatives considered**:
- Separate config file for meta-review: Rejected because it breaks the single-config-file convention.
- Default disabled: Rejected because the feature provides value by default; users who don't want it can opt out.

## R-006: Report and Console Integration

**Decision**: Add an "Agent Quality Scores" section to the findings report (Step 7) and a one-line per-agent summary to the console output (Step 8). The section appears only when meta-review ran.

**Rationale**: Keeps the report readable. Users who skip meta-review (below threshold or disabled) see no difference.

**Alternatives considered**:
- Separate quality report file: Rejected because it fragments the review output.
