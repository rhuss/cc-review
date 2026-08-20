# Tasks: Meta-Review Quality Gate

**Branch**: `003-meta-review` | **Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

## Phase 1: Setup

- [x] T001 Extend finding schema with meta-review fields in `review/core/schemas/finding.schema.json`
- [x] T002 Add `meta_review` section to config template in `review/config/config-template.yml`

## Phase 2: Foundational (Agent Prompts)

- [x] T003 [P] Create Skeptic agent prompt in `review/core/agents/meta-skeptic.md`
- [x] T004 [P] Create Calibrator agent prompt in `review/core/agents/meta-calibrator.md`

## Phase 3: Config Gating and CLI Flag (US5 - Config-Gated Activation, P1)

**Story goal**: Meta-review only runs when enabled and finding count exceeds threshold.
**Independent test**: Run review with < 5 findings, verify skip. Run with >= 5, verify it runs.

- [x] T005 [US5] Add `--no-meta-review` CLI flag handling and config resolution in `review/core/commands/review.md` (argument-hint, CLI overrides section)
  - **Interfaces (exports)**: Sets `NO_META_REVIEW` variable ("true"/"false") from CLI flag; adds `meta_review.enabled=false` to `CLI_OVERRIDES` array when flag is present
- [x] T006 [US5] Add Step 4b skeleton in `review/core/commands/review.md` with config gate logic (read `meta_review.enabled` and `meta_review.min_findings`, skip with log message when below threshold)
  - **Interfaces (imports)**: `NO_META_REVIEW` variable from T005; `resolve_config "meta_review.enabled"` and `resolve_config "meta_review.min_findings"` keys from T002
  - **Interfaces (exports)**: `## Step 4b: Meta-Review` section in review.md containing the config gate block; subsequent dispatch code (T007, T009) is inserted inside this section after the gate check passes

## Phase 4: False Positive Filtering (US1 - Filtering False Positives, P1)

**Story goal**: Skeptic evaluates findings and removes false positives before gate check.
**Independent test**: Review code with known false-positive patterns, verify removals with cited reasoning.

- [x] T007 [US1] Add Skeptic subagent dispatch to Step 4b in `review/core/commands/review.md` (prompt construction using preamble + meta-skeptic.md, findings list, changed files)
  - **Interfaces (imports)**: Step 4b section from T006; Skeptic prompt file `core/agents/meta-skeptic.md` from T003
  - **Interfaces (exports)**: Skeptic subagent returns JSON array of `{finding_id, verdict, verdict_reasoning}` objects where `verdict` is one of `confirmed`, `weak`, `false-positive`
- [x] T008 [US1] Add verdict application logic to Step 4b orchestrator in `review/core/commands/review.md` (remove false-positive findings, log removals with reasoning)
  - **Interfaces (imports)**: Skeptic results array from T007; schema fields `verdict`, `verdict_reasoning` from T001

## Phase 5: Severity Calibration and Contradiction Detection (US2/US3, P2)

**Story goal**: Calibrator adjusts inflated severities and flags contradictions between agents.
**Independent test**: Review code where one agent over-classifies severity, verify downgrade. Create contradictory findings, verify annotation.

- [x] T009 [US2] Add Calibrator subagent dispatch to Step 4b in `review/core/commands/review.md` (prompt construction using preamble + meta-calibrator.md, findings list with source_agent)
  - **Interfaces (imports)**: Step 4b section from T006; Calibrator prompt file `core/agents/meta-calibrator.md` from T004
  - **Interfaces (exports)**: Calibrator subagent returns JSON with `calibrations` array of `{finding_id, calibrated_severity, calibration_reasoning}`, `contradictions` array of `{finding_id_a, finding_id_b, explanation}`, and `agent_scores` object keyed by `source_agent` with `{precision, signal_to_noise, finding_count}`
- [x] T010 [US2] Add severity calibration application to Step 4b orchestrator in `review/core/commands/review.md` (apply calibrated_severity to weak findings, handle conflict resolution with Skeptic)
  - **Interfaces (imports)**: Calibrator results from T009; Skeptic verdicts from T007/T008; schema fields `calibrated_severity`, `calibration_reasoning` from T001. Conflict rule: when Skeptic says `confirmed` but Calibrator downgrades, the more conservative verdict (downgrade) wins
- [x] T011 [US3] Add contradiction annotation logic to Step 4b orchestrator in `review/core/commands/review.md` (assign contradiction_id to paired findings)
  - **Interfaces (imports)**: Calibrator `contradictions` array from T009; schema field `contradiction_id` (pattern `^CONTRA-[0-9]+$`) from T001

## Phase 6: Agent Performance Scoring (US4, P3)

**Story goal**: Per-agent quality scores in report and console output.
**Independent test**: Run review with meta-review, verify agent score table in report.

- [x] T012 [US4] Add "Agent Quality Scores" section to findings report template in Step 7 of `review/core/commands/review.md`
  - **Interfaces (imports)**: `agent_scores` object from Calibrator results (T009/T010); keyed by `source_agent`, each value has `precision` (float 0-1), `signal_to_noise` (float), `finding_count` (int)
- [x] T013 [US4] Add per-agent score summary line to console output in Step 8 of `review/core/commands/review.md`
  - **Interfaces (imports)**: Same `agent_scores` data structure as T012

## Phase 7: Polish and Error Handling

- [x] T014 Add subagent failure/timeout handling to Step 4b in `review/core/commands/review.md` (skip meta-review, pass findings through unchanged, log warning)
- [ ] T015 Commit all changes with descriptive message

## Dependencies

```
T001, T002 ─── no dependencies (setup)
T003, T004 ─── no dependencies (parallel, independent files)
T005 ──────── depends on T002 (config must exist)
T006 ──────── depends on T005 (CLI flag must be parsed)
T007 ──────── depends on T003, T006 (Skeptic prompt + Step 4b skeleton)
T008 ──────── depends on T001, T007 (schema fields + Skeptic dispatch)
T009 ──────── depends on T004, T007 (Calibrator prompt + Skeptic dispatch establishes Step 4b dispatch pattern)
T010 ──────── depends on T001, T009 (schema fields + Calibrator dispatch)
T011 ──────── depends on T010 (calibration logic must exist)
T012 ──────── depends on T008, T010 (verdicts must be applied)
T013 ──────── depends on T012 (report format before console)
T014 ──────── depends on T007, T009 (both dispatches must exist)
T015 ──────── depends on all prior tasks
```

## Parallel Execution Opportunities

| Group | Tasks | Rationale |
|-------|-------|-----------|
| Setup | T001, T002 | Independent files (schema vs config) |
| Agent Prompts | T003, T004 | Independent files (skeptic vs calibrator) |
| Dispatch | T007, T009 | Both insert into Step 4b of review.md; implement sequentially (T007 first) to avoid merge conflicts in the same markdown section |
| Reporting | T012, T013 | Different output targets (report file vs console) |

## Implementation Strategy

**MVP (Phase 1-4)**: Config gating + Skeptic false-positive filtering. This delivers the highest-value capability (removing bad findings) with the simplest critical path.

**Increment 2 (Phase 5)**: Calibrator severity adjustment + contradiction detection. Builds on the dispatch infrastructure from Phase 4.

**Increment 3 (Phase 6-7)**: Reporting and error handling. Polish layer that makes the feature production-ready.
