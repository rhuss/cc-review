# Brainstorm: Skeptic That Actually Finds False Positives

**Date:** 2026-11-04
**Status:** parked (raw idea, to be refined after the cc-review talk)
**Issue:** -

## Problem Framing

The meta-review Skeptic (`core/agents/meta-skeptic.md`) is supposed to refute findings and remove false positives. In practice it never does:

- 6 local reports with meta-review results (2026-10-19 to 2026-10-28, 128 findings): **0 removed** as false positive, 10 marked weak, 17 recalibrated (13%, all downward where stated) by the Calibrator.
- NVIDIA/OpenShell runs: [#3123](https://github.com/NVIDIA/OpenShell/pull/3123) 0 removed, 3 weak; [#3338](https://github.com/NVIDIA/OpenShell/pull/3338) 22 findings checked, 0 removed, 6 weak.

At the same time there are signs of real noise that the Skeptic lets through:

- The Calibrator scores lanes as low as 0.65 precision (test-quality, lowest in every run; goal-alignment 0.74), yet the Skeptic confirms those same findings.
- The user held back **29 findings** at the posting step across 7 OpenShell runs; the human did the Skeptic's job.
- 28 posted OpenShell threads were resolved without reply or code change, 3 were withdrawn by the reviewer as false positive or out of scope, 1 was rejected by the author.

Open question first: is "0 removed" a bug in the Skeptic or the truth (the preamble's evidence and confidence rules already filter)? The data above suggests at least part of it is the Skeptic.

**Success (draft):** the Skeptic removes or demotes most findings a human would hold back or an author would reject, without removing findings that later get fixed; its precision and recall are measured, not assumed.

**Anti-goals (draft):** a Skeptic that removes real bugs to look effective; large extra token cost on every run; hiding removed findings (they must stay visible in the report).

## Suspected Causes

- **Anchoring:** the Skeptic reads the reviewer's rationale, confidence and source before judging; LLMs tend to agree with a plausible narrative.
- **No burden of proof for "confirmed":** confirming costs nothing, refuting needs an argument. "weak" acts as a hedge instead of a decision.
- **Threshold gate:** meta-review skips runs below 5 findings (`meta_review.min_findings`).
- **Same model family as the reviewers:** shared blind spots.

## Ideas (unrefined)

1. **Ground truth first: a labeled eval set.**
   - True positives: findings that were fixed (77 verified fixes on OpenShell, 547 Critical/Important fixed in local reports).
   - Likely false positives: findings held back at posting, withdrawn by the reviewer, rejected by the author, resolved without reply.
   - Seeded false positives: a guard 30 lines above the cited range, documented intentional behavior, a misread variable, a test-only path.
   - Measure the current Skeptic's recall on false positives and its false-removal rate before changing anything.
2. **Blind refutation:** give the Skeptic only the claim (file, line range, failure scenario), not the reviewer's rationale, confidence or `source_agent`. It must reproduce the problem independently. (Already an open thread from brainstorm #04: should critics see which agent produced a finding?)
3. **Reachability proof for "confirmed":** a confirmed Critical/Important finding needs a concrete path from an input or caller to the cited line. Without it: weak, then demoted to Notable or removed.
4. **Executable check where cheap:** for correctness findings, write a minimal failing test or snippet; confirmed when it fails before the fix. Optional, Critical/Important only, budgeted.
5. **Cross-vendor second skeptic:** a different model (for example Codex) votes on Critical/Important findings; disagreement demotes. Fits the multi-vendor panel idea.
6. **Reconcile with the Calibrator:** if the Calibrator scores a lane low, the Skeptic must justify each confirmation from that lane.
7. **Learn from history:** prior author rebuttals and held-back findings in the same repository become negative examples ("this project intentionally does X").

## Data Sources

- `docs/extras/presentation/data/openshell-findings-labeled.jsonl`: 208 OpenShell inline findings with outcome labels (collected 2026-11-04).
- `docs/extras/presentation/data/local-reports-aggregate.json`: parse of 140 local `review-findings*.md` reports (contains private project paths; do not commit as is).
- Review bodies on OpenShell list held-back findings per run.

## Open Questions

- Is removal the right action, or should the Skeptic only demote to Notable and let the posting step drop them?
- How to label "resolved without reply": false positive, low value, or silently fixed elsewhere?
- What extra cost per run is acceptable for blind refutation and reachability proofs?
- Should the eval set live in `tests/` as a regression suite for the meta-review prompts?
