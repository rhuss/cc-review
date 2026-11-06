# Brainstorm: Review Metrics Log for Tuning Reviewers

**Date:** 2026-11-06
**Status:** active (raw idea, to be refined after the cc-review talk)
**Issue:** -

## Problem Framing

Every run already produces the numbers needed to tune the panel, and then throws them away:

- The Calibrator computes `agent_scores` (precision, signal/noise, finding count) per reviewer. They land in the report's "Agent Quality Scores" table and the console summary, then nothing reads them again.
- Critic outcomes (removed as false positive, marked weak, severity raised or lowered) are logged per run only.
- The posting step knows which findings the user held back; the fix loop knows what was fixed and what remained; follow-up reviews and `triage` learn which posted findings were addressed, rejected or withdrawn.

For the talk (slides 11 to 14) these numbers had to be collected by hand: parsing 140 local `review-findings*.md` reports scattered across projects and labeling 208 OpenShell findings by their GitHub outcome. That took hours and is not repeatable.

Without a history, tuning is guesswork. "test-quality is the lowest reviewer in every run" was only visible after aggregating six reports by hand.

**Success (draft):** after a few weeks of normal use, one command answers "which reviewer should I tune or switch off in this project, and why", backed by outcomes, not only the model's self-assessment.

**Anti-goals (draft):** storing code, descriptions or file contents; a tool that changes config on its own; extra cost per run beyond writing a small file; a dashboard nobody opens.

## Proposed Shape

1. **Per-run record:** append one JSON line per run to `.cc-review/metrics/runs.jsonl` in the project (gitignored, like the rest of `.cc-review/`). Contents:
   - run id, date, mode (local branch, PR, bulk worker), profile, cc-review version
   - reviewers that ran, were skipped (with reason), timed out
   - per reviewer: findings by severity, Calibrator precision and signal/noise
   - critic outcomes: removed, weak, calibrated down, calibrated up, contradictions
   - posting: findings posted, held back by the user, edited before posting
   - fix loop: fixed, remaining, rounds, tests turned into findings
   - finding keys only (id, reviewer, severity, category, file hash), no text
2. **Outcome back-fill:** follow-up reviews and `triage` already classify prior findings (addressed, accepted explanation, open, rejected, withdrawn). Write those outcomes back as separate lines keyed by run id and finding id, so the log gains ground truth over time.
3. **Opt-in global rollup:** `~/.cc-review/metrics/` keeps per-reviewer aggregates only (no paths, no repo names unless the user allows it), for comparing reviewers across projects.
4. **A stats command:** for example `/cc-review:stats` (or a `--stats` view of `inbox`). Reads the log and prints per-reviewer trends with concrete, explained suggestions:
   - "test-quality: precision below 0.7 in 5 of the last 6 runs, 40% of its findings held back. Consider review hints or `--no-test-quality`."
   - "codex: 3 timeouts in 10 runs. Consider raising its timeout."
   - "Skeptic: 0 removals in 20 runs while 31 findings were held back by hand."
   Suggestions only; the user edits config or hints.

## Relation to Other Work

- **#13 Skeptic false positives:** the outcome-labeled log is the evaluation set #13 needs to measure Skeptic recall and false-removal rate before changing the prompt.
- **#04 meta-reviewer:** answers its open thread "should quality scores influence future reviews?" in the cautious form: they inform the user, they do not silently reweight findings.
- **#09 incremental review / #10 review convergence:** already produce the per-thread outcomes the back-fill needs.

## Open Questions

- Where does the back-fill hook live: in follow-up review, in `triage`, or in both, and how are outcomes matched when a finding was edited before posting?
- How is "resolved without reply" labeled: addressed, low value, or unknown?
- Retention: rotate the log by size or age, or keep everything (it is small)?
- Bulk runs: one line per PR worker, plus a bulk summary line?
- Should a project be able to commit an anonymized rollup (for example for team-wide tuning), and what exactly is safe to share?
- Is the Calibrator's precision worth keeping at all once outcome data exists, or only as a cheap early signal?
