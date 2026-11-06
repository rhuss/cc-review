# Code Review: Streamlined Inbox Report with Guided Tour and Fan-Out

**Spec:** specs/012-inbox-tour-orchestration/spec.md
**Date:** 2026-11-06
**Reviewer:** Claude (speckit.spex-gates.review-code)
**Branch:** 012-inbox-tour-orchestration

## Compliance Summary

**Overall Score: 100%**

- Functional Requirements: 19/19 (100%)
- Success Criteria: 6/6 (100%)
- Edge Cases: 5/5 covered
- Spec-Declared Constants: n/a (no `## Constants` section in spec)

The feature is delivered almost entirely as harness-agnostic prompt command
files (`review/core/commands/{inbox,review,triage,bulk}.md`) plus the harness
shims, with one executable change: the `--prs` explicit-list selector in
`review/core/scripts/bulk-select.sh`. Compliance for the prompt files is
assessed as "does the command prompt instruct the behavior the FR requires";
the executable path is assessed against its tests and its control flow.

## Detailed Review

### Functional Requirements

#### Streamlined report (US1)

- **FR-001** Attention table, one row per item, five fixed columns — **Compliant**.
  `review/core/commands/inbox.md:130-138` documents the table with columns
  `Item | What | Why you | Certainty | Next step` in order. Test:
  `tests/test_inbox_report.py::test_attention_table_has_the_five_columns`.
- **FR-002** Detail section per attention item (situation, recommendation, evidence link) — **Compliant**.
  `inbox.md:140-155` ("Attention detail") defines the per-item block with
  situation, `My take:` and `Evidence:`.
- **FR-003** Recommendation labeled as the assistant's judgment, not an obligation; explicit/inferred/uncertain preserved — **Compliant**.
  `inbox.md:153-155` ("an opinion and never an obligation"); certainty tokens
  `Explicit/Inferred/Uncertain` carried through section 3 and the table.
- **FR-004** "Waiting on others" / "No current action" as brief lists — **Compliant**.
  `inbox.md:157-159` ("brief two-column lists, not paragraphs").
- **FR-005** Scope line and coverage account compressed; limits/failures not hidden — **Compliant**.
  `inbox.md:161-174` ("Coverage account (compressed)"), explicitly keeps
  `scope.known_limits`, `detail_bounds`, source failures, partial-run guard.
- **FR-006** Report-only run is read-only — **Compliant**.
  `inbox.md:24-34` (Boundaries) and `inbox.md:176` (read-only guarantee:
  no comment posted, no thread resolved, no branch pushed, no agent launched,
  no working-tree change). Test: `test_read_only_guarantee`.

#### Guided tour (US2)

- **FR-007** End-of-report opt-in tour prompt; declining leaves a read-only report — **Compliant**. `inbox.md:178-187` (section 5).
- **FR-008** Select up to five, default top five in report order, accept default or name numbers — **Compliant**. `inbox.md:193-198` (section 6a).
- **FR-009** Present one at a time with focused context; per-item subagent where supported, else inline — **Compliant**. `inbox.md:200-205` (section 6b).
- **FR-010** After a batch, offer next five unvisited or re-run; "unvisited" independent of prior selection — **Compliant**. `inbox.md:223-225` (section 6d).
- **FR-011** Tour reads the already-collected snapshot; no fresh collection — **Compliant**. `inbox.md:189-191`; snapshot lifecycle moved to step 7 Clean Up (`inbox.md:227-229`) so the snapshot outlives the tour.

#### Fan-out orchestration (US3)

- **FR-012** Per-item fan-out to review/triage/issue; Discussion textual only; resume after return — **Compliant**. `inbox.md:207-217` (section 6c).
- **FR-013** Several PRs handed to `bulk` as one explicit list, not launched individually; issues one at a time — **Compliant**. `inbox.md:219` ("Batch.").
- **FR-014** Acting is an explicit user choice only — **Compliant**. `inbox.md:207-209`, Boundaries.
- **FR-015** No reimplementation of review/triage/apply/post/merge; delegate; no new write authority — **Compliant**. `inbox.md:27, 211`.
- **FR-016** Fan-out only inside a local checkout of the target repo; else state unavailable but still deliver report — **Compliant**. `inbox.md:209`.
- **FR-017** `bulk` accepts an explicit list of PRs — **Compliant**. `bulk.md` Inputs (`--prs`), `bulk-select.sh` `--prs` selector with `explicit_candidates_review`/`explicit_candidates_triage` (`bulk-select.sh:224-262, 310-315, 401-408`). Test: `test_bulk_select_explicit_list`.
- **FR-018** inbox passes PRs unfiltered; bulk applies its own eligibility and surfaces exclusions; no separate selection authority in inbox — **Compliant**. `inbox.md:219`; explicit candidates pass through the shared `classify`/`pr_actions.py` assessor (`bulk-select.sh:311-315, 406`), which excludes drafts/reviewed-at-head/closed and reports them. Test asserts a draft is surfaced as `excluded`, not dropped.

#### Cross-harness behavior

- **FR-019** Streamlined report on all harnesses; tour/fan-out degrade gracefully — **Compliant**. `inbox.md:221` (text-handoff degradation); shims updated: `review/opencode/command/inbox.md`, `review/skills/inbox/SKILL.md`, `speckit/commands/speckit.cc-review.inbox.md`.

### Success Criteria

- **SC-001** One table row per attention item, five columns — **Compliant** (FR-001).
- **SC-002** Default run produces zero repo/working-tree changes — **Compliant** (FR-006).
- **SC-003** Acting on one item == invoking the command directly — **Compliant**. `inbox.md:217` ("exactly as if it were invoked directly").
- **SC-004** Batching N PRs == invoking `bulk` on that explicit list; no divergent selection in inbox — **Compliant** (FR-013, FR-018).
- **SC-005** Every attention item: situation + labeled recommendation + >=1 evidence link — **Compliant** (FR-002); test `test_every_item_has_reasons_and_evidence`.
- **SC-006** Tour never >5 per batch; always offers next-batch/re-run when more remain — **Compliant** (section 6a, 6d).

### Edge Cases

All five spec edge cases are addressed: empty attention group suppresses the
tour prompt (`inbox.md:187`), incomplete coverage disclosed (coverage account),
ineligible PR surfaced by `bulk` (FR-018 path + test), unavailable command
degrades to text (`inbox.md:221`), and over-limit/invalid selections rejected
with a clear message (`inbox.md:197`).

### Extra Features (Not in Spec)

None observed. All changes map to FR-001..019.

## Code Quality Notes

- `bulk-select.sh` reuses the existing shared `pr_actions.py` assessor for the
  explicit list rather than adding a parallel eligibility path, which is what
  keeps FR-018/SC-004 honest (no divergent selection logic).
- `parse_prs` de-duplicates while preserving order and rejects non-positive
  integers; mutual-exclusion with `--pr`/`--all-open`/`--search` is enforced in
  both `bulk-select.sh` and the `bulk.md` flag-validation block, and in the
  `review.md`/`triage.md` front-door checks.

## Conclusion

Spec compliance is 100% (19/19 FR, 6/6 SC); well above the 95% gate for deep
review. Proceeding to deep review.

---

# Deep Review Report

**Date:** 2026-11-06
**Branch:** 012-inbox-tour-orchestration
**Rounds:** 1
**Gate Outcome:** PASS
**Invocation:** quality-gate (ship pipeline)

## Summary

| Severity | Found | Fixed | Remaining |
|----------|-------|-------|-----------|
| Critical | 0 | 0 | 0 |
| Important | 5 | 5 | 0 |
| Minor | 7 | 3 | 4 |
| Notable | 3 | 1 | 2 (captured) |
| **Total** | **15** | **9** | **6** |

**Internal agents completed:** 5/6 (Goal Alignment skipped: no PR for the branch)
**External tools:** CodeRabbit completed (4 findings), Codex completed (1 finding), Copilot skipped (disabled in config)
**Test suite:** `make test` green after fixes — 1456 passed, 0 failed (baseline 1451; +5 from added/split tests)

The five Important findings collapsed to two distinct issues after dedup: one
executable defect (reported by CodeRabbit + three internal agents) and three
test-quality weaknesses. All were fixed in round 1.

## Findings (Important — all fixed)

### FINDING-1 — explicit `--prs` review aborted the whole batch on one bad PR
- **Severity:** Important **Confidence:** 85
- **File:** review/core/scripts/bulk-select.sh:227-241
- **Category:** correctness / production-readiness / FR-018
- **Source:** CodeRabbit (major) + correctness-agent + production-agent + architecture-agent
- **Resolution:** fixed (round 1)

**What was wrong:** `explicit_candidates_review` fetched each PR with `gh_json`,
which `exit 1`s on any non-rate-limit failure. A single unresolvable PR number
in the explicit `--prs` list (deleted, transferred, access lost) aborted the
entire selection and discarded every valid PR. The sibling
`explicit_candidates_triage` already degraded gracefully. This violated FR-018
("surface any pull request it would exclude, rather than silently dropping it")
and the spec edge case at spec.md:80.

**How it was resolved:** Replaced the `gh_json` call with a `try`-based fetch;
on non-rate-limit failure it emits `selection_warning "PR #n detail
unavailable; assessment incomplete"` and appends an incomplete placeholder
record so the shared assessor surfaces the PR as excluded, while the remaining
PRs resolve normally. Rate-limit `exit 75` still propagates. Verified
empirically (a placeholder record normalizes to an `incomplete-evidence`
exclusion) and covered by a new behavioral test (`--prs 101,777`).

### FINDING-2 — evidence test was a tautological wrong-reason pass
- **Severity:** Important **Confidence:** 92
- **File:** tests/test_inbox_report.py:46-54
- **Category:** test-quality (SC-005, FR-002)
- **Source:** test-quality-agent
- **Resolution:** fixed (round 1)

**What was wrong:** `test_every_item_has_reasons_and_evidence` claimed to verify
detail-section evidence but searched `json.dumps(item)` over the whole item,
which the top-level `url` always satisfies — the detail slice was never checked
(issue #88 has no detail URL yet passed).

**How it was resolved:** Split into `test_every_item_has_reasons_and_link` and a
new `test_detail_section_carries_its_own_evidence_link` that checks
`item["detail"]` specifically, scoped to items with collected activity, and
(per CodeRabbit re-review) asserts at least one item was actually checked so it
cannot pass vacuously.

### FINDING-3 — bulk `--prs` usage-error tests asserted exit code only; `--pr` case tested nothing
- **Severity:** Important **Confidence:** 85
- **File:** tests/run.sh:3505-3513 (test_bulk_select_explicit_list)
- **Category:** test-quality
- **Source:** test-quality-agent
- **Resolution:** fixed (round 1)

**What was wrong:** The mutual-exclusion cases asserted only `rc == 2`. The
`--prs 101 --pr 5` case was a wrong-reason pass: `bulk-select.sh` has no `--pr`
flag, so it hit the catch-all usage error, not any `--prs`/`--pr` rule.

**How it was resolved:** Removed the misleading `--pr` case (the real
`--prs`/`--pr` exclusivity is covered in `test_bulk_md_validation_errors`), and
the `--all-open`/`--search` cases now capture stderr and assert the exact
message. Added an empty-token case (`--prs 1,,2`) and a graceful-failure case
(`--prs 101,777`).

### FINDING-4 — no tests for the guided-tour (US2) and fan-out (US3) contract
- **Severity:** Important **Confidence:** 80
- **File:** tests/test_inbox_report.py (steps 5-6 of inbox.md)
- **Category:** test-quality (FR-007..019, SC-006)
- **Source:** test-quality-agent
- **Resolution:** fixed (round 1)

**What was wrong:** `ReportContract` asserted only the US1 report contract;
nothing asserted the tour-offer gate, five-item batch rule, next-batch choice,
per-item fan-out offers, Discussion-textual-only, local-checkout gating, or the
degradation handoff — all string-assertable prompt text.

**How it was resolved:** Added a `TourAndFanoutContract` test class (11 tests)
covering FR-007..019 and SC-006 against inbox.md steps 5-6.

### FINDING-5 — snapshot temp dir leaked on abnormal termination
- **Severity:** Important **Confidence:** 75
- **File:** review/core/commands/inbox.md step 1 / step 7
- **Category:** production-readiness (FR-011 snapshot lifecycle)
- **Source:** production-agent
- **Resolution:** fixed (round 1)

**What was wrong:** The feature deliberately extended the snapshot dir's life
across the whole multi-turn opt-in tour, but cleanup existed only as the step-7
prose. An error mid-report, an abandoned interactive tour, or a fresh shell that
lost `INBOX_TMP` would leak the dir with no reclamation (no trap, no sweep).

**How it was resolved:** Added a stale-dir orphan sweep at the start of step 1
(`find ... -name 'cc-review-inbox.*' -mmin +720 -exec rm -rf`) so abnormal exits
no longer accumulate leaked snapshots, with a comment explaining why an EXIT
trap cannot cover a tour that spans turns.

## Additional hardening applied (Minor)

- **bulk-select.sh `parse_prs`:** empty tokens in the list (`1,,2`) are now
  rejected instead of silently skipped, aligning the script's own validator with
  the `bulk.md` PRS_FLAG guard (CodeRabbit minor + test-quality).
- **inbox.md tool-call boundary:** the step-6c fan-out handoff is now stated as
  the explicit exception to the "no tool calls of its own" boundary (CodeRabbit
  minor), resolving an apparent internal contradiction.
- **inbox.md tour subagent:** the per-item presentation subagent prompt must now
  restate the untrusted-data boundary (security-agent, Notable) — folded in as
  defense-in-depth since the subagent reasons over attacker-controllable text.

## Remaining Findings (Minor — not gate-blocking, deferred)

| # | Finding | File | Source | Why deferred |
|---|---------|------|--------|--------------|
| M-1 | Present-but-empty `--prs` falls back to the default bulk queue instead of erroring | review/core/commands/bulk.md:130 | Codex (P2) | Reclassified Minor: backstopped by `parse_prs` (rejects empty `--prs`) one layer down; only reachable by manually typing `--prs ""`, and the fallback is the user's normal default queue, not arbitrary PRs. Clean fix needs a `PRS_GIVEN` sentinel across bulk.md + shims; deferred to avoid destabilizing a 1001-line prompt for a near-nil trigger. |
| M-2 | Explicit mode applies the default `--limit 10`, capping a long explicit list and fetching PRs it will then exclude | review/core/scripts/bulk-select.sh:285-315 | CodeRabbit + production-agent | Over-limit exclusions are already surfaced (FR-018-compliant), and the inbox tour caps selections at 5, so no real cap is hit. Changing fetch/limit semantics is a design choice, not a defect. |
| M-3 | `explicit_candidates_triage` duplicates the REVIEWER_QUERY fetch/fallback loop already in `do_triage` | review/core/scripts/bulk-select.sh:246-262 vs 436-448 | architecture-agent | A refactor (extract a shared `fetch_reviewer_detail` helper) with no behavior change; deferred to keep the fix diff focused. |
| M-4 | The `inbox` command `description` frontmatter diverged across the three harness surfaces (only SKILL.md mentions the tour) | inbox.md:3, speckit.cc-review.inbox.md:3 vs SKILL.md:3 | architecture-agent | Cosmetic metadata wording; no behavioral impact. |

## Notable Observations (captured to brainstorm/idea-inbox.md)

- Explicit `--prs` test asserts `review.eligible` only, not canonical-assessment
  equivalence (SC-004 would be more strongly pinned) — `explicit-prs-canonical-equivalence-test`.
- No fixture item exercises the "Uncertain"/"Inferred" certainty branch, making
  `test_certainty_values_are_known` near-tautological — `uncertain-certainty-fixture-coverage`.

## Post-Fix Spec Coverage

The fix loop replaced and renamed code but dropped no spec requirement. All 19
functional requirements remain implemented (FR-017/FR-018 are strengthened by
FINDING-1's fix). Spec coverage: 19/19 verified after the fix loop.

## Test Suite Results

| Round | Command | Exit | Failures | Status |
|-------|---------|------|----------|--------|
| 1 | make test | 0 | 0 | passed (1456 passed, 0 failed) |

## Gate Outcome

**PASS** after fix round 1. Critical + Important remaining = 0. Four Minor
findings and two Notable observations remain (documented above; Notables
captured to the idea inbox); none block the gate.

---
