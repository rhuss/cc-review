# Brainstorm: Incremental (Follow-Up) Review

**Date:** 2026-10-27
**Status:** active
**Issue:** https://github.com/rhuss/cc-review/issues/8

The original exploration below is retained for context. The agreed direction is recorded in the revisit dated 2026-10-28, which supersedes the original proposal and draft requirements.

## Problem Framing

A re-review today is a full review. When a PR's head moves after a cc-review review, `review` runs every reviewer over the whole diff against base, then reconciles with the earlier run after the fact:

- 7.5d finds the most recent cc-review review by its `<!-- cc-review:run-id: -->` marker.
- 7.5e drops current findings that match an earlier inline comment (same path, line within 3, same category).
- 7.5f treats every earlier thread without a matching current finding as fixed, replies "Resolved: this issue appears to be addressed in the current code." and resolves it.

The only scope narrowing in `review.md` is inside the fix loop (re-review only the files a fix round changed, `review.md:219`).

This has costs and a correctness gap:

- **Cost.** A follow-up after a two-line fix pays for a full multi-agent pass over the whole PR. Bulk review makes this visible: a dry run on NVIDIA/OpenShell selected #4830 and #3338 as re-reviews ([#08](08-inbox-action-alignment.md)). #3338 had only been rebased after a second pass had already verified every finding.
- **Noise.** A fresh full pass finds new things in code that did not change since the first review. That moves the goalposts for the author, which the reviewer voice and the upstream gator reviewer both warn against ("Do not mine unchanged code for new findings", `specs/004-reviewer-plugins/upstream/principal-engineer-reviewer.md:94`).
- **False resolution.** 7.5f infers "fixed" from the absence of a matching finding. Reviewer variance, a moved line or a changed category is enough to resolve a thread whose issue still exists. Triage Step 11b verifies fixes deliberately; review does not.
- **Rebases.** A plain `git diff <reviewed head>..<new head>` after a rebase shows upstream changes as if they were the author's.

Useful facts already in place:

- The reviewed head is known without a marker change: GitHub records the commit of every review (`.commit.oid`), and `bulk-select.sh` already uses it for `reviewed_at_head`.
- Triage Step 11b already knows how to verify a claimed fix against the code and reply with `<!-- cc-review-triage -->`.
- The upstream gator schema has a per-finding `scope` (`latest_delta`, `carried`, `unchanged_critical`) for exactly this distinction.

## Approaches Considered

### A: Delta-scoped review mode

When an earlier cc-review review exists and the head moved, review only what changed since that review's commit. Reviewers get the delta as their primary scope and the full PR diff as context. Earlier findings are verified explicitly (reusing the Step 11b logic) instead of being inferred from absence.

- Pros: cheaper; no goalpost moving; explicit fix verification replaces the 7.5f heuristic; matches the gator model.
- Cons: needs a robust delta (rebases), a way to tell reviewers what is in scope versus context, and a rule for when a new problem in unchanged code is still worth raising.

### B: Full review, smarter reconciliation

Keep the full pass, but tag each finding as in-delta or not, suppress or demote findings outside the delta, and replace 7.5f's absence heuristic with explicit verification.

- Pros: smallest change to the reviewer pipeline; fixes the false-resolution problem.
- Cons: no cost saving; reviewers still spend their attention on unchanged code.

### C: Route follow-ups to triage

Treat "author responded to my review" as reviewer-side triage (Step 11b) and only run a review when the delta goes beyond the fixes.

- Pros: reuses what exists; ties in with [#08](08-inbox-action-alignment.md) approach A.
- Cons: deciding "beyond the fixes" needs the delta analysis anyway; new code in the delta still deserves a review.

## Relationship to Inbox Action Alignment

The discussion in [#08](08-inbox-action-alignment.md) agreed on shared PR action assessment for inbox and bulk selection. Triage verifies earlier findings and handles their conversations; review examines first-time or additional code changes. A PR can require both and remains eligible for both actions. Completing triage alone does not satisfy outstanding review work, and running both flows must avoid duplicate thread replies or resolutions.

This brainstorm owns the follow-up review behavior: scope, baselines, rebase handling and explicit verification of earlier findings. The detailed approach below remains proposed; #08's decision establishes the command boundary without settling those choices.

## Proposed Direction

Not yet decided. The current recommendation is A, with C as the cheap path inside it:

1. Compute the delta since the last cc-review review's commit.
2. Verify each open earlier finding against the new head (Step 11b logic): confirm and resolve, keep open with a reply, or leave for the user.
3. If the delta contains changes beyond what the findings asked for, run the reviewers on the delta with the full PR as read-only context.
4. Post one review that combines verification results and new delta findings, tagged by scope.

B's explicit verification replaces 7.5f in every mode, including full reviews.

## Key Requirements (draft)

**Delta computation**
- Baseline: the commit of the most recent cc-review review (not a no-findings marker) by the user, or by anyone when the config says so.
- New commits on top of the baseline: `git diff <baseline>..<head>`.
- Rebased or force-pushed branches: compare the patch series (`git range-diff <base>..<baseline> <base>..<head>`, or the PR diff at baseline versus the PR diff at head) so upstream changes from the rebase are not attributed to the author.
- Baseline commit no longer reachable (squash, history rewrite): fall back to a full review and say so.

**Reviewer scope**
- Reviewers receive the delta as scope and may read the full PR diff and files for context.
- New findings on unchanged code are allowed only for Critical (security, data loss, correctness) with stated new evidence, as in the gator rules; they are tagged `unchanged_critical`.
- Each finding carries a scope: `latest_delta`, `carried` (an earlier finding still present), `unchanged_critical`.

**Earlier findings**
- Every unresolved thread from earlier cc-review runs is verified against the head, with the result recorded (fixed, still present, unclear).
- Only verified fixes are resolved. "No matching finding" alone never resolves a thread.
- Author replies on those threads (won't fix, deferred, question) are handled as in triage Step 11b-3, not overwritten by a re-review.

**Invocation**
- Single PR: automatic when an earlier cc-review review exists and the head moved, with `--full` to force a full review; or opt-in with `--since-last`. Open.
- Bulk review: re-review selections use incremental mode; first reviews stay full.
- The summary states the mode and baseline ("Follow-up review since `86d7f480`, 2 commits, 4 files").

**Rebase-only changes**
- When the range-diff shows no author change (pure rebase), post nothing new; at most report "rebased, no changes since the last review" and leave the earlier verdict standing. Bulk review should exclude such PRs or mark them as such.

## Original Open Questions

- Automatic incremental mode with `--full`, or opt-in `--since-last`? What does bulk review default to?
- Range-diff output is hard for reviewers to read. Is a reconstructed "PR diff at baseline vs PR diff at head" a better input, and how is it produced in a worktree?
- Whose review is the baseline when several people ran cc-review on the same PR?
- How do command reviewers (CodeRabbit, gator) get delta scope? Gator has its own follow-up mode; CodeRabbit may only support full or incremental on its own terms.
- Does the meta-review (Skeptic, Calibrator) see the earlier findings, so it can reject duplicates and goalpost-moving findings?
- Where does the shared verification logic live, so review (follow-up) and triage (Step 11b) do not drift apart?
- How should the posted review read when it mixes verifications and new findings: one summary with two sections, or verification replies in the threads plus a short summary?

---

## Revisit: 2026-10-28

### Updated Problem Framing

[Issue #8](https://github.com/rhuss/cc-review/issues/8) follows the implemented inbox action alignment work in #7. Review and triage now have independent action assessments, and exact handled-activity checks prevent some duplicate thread actions. Follow-up review still examines the full PR, and its thread reconciliation still infers a fix when an earlier finding has no match in the new review. Freshness checks do not establish that the underlying problem was fixed.

The intended outcome is a cheaper, focused follow-up review that examines all changed author content, verifies earlier findings explicitly, and avoids moving the goalposts through ordinary new findings on unchanged code. Rebases must not make upstream changes appear to be new author work. Review and triage must agree on verification outcomes without either silently clearing separate work.

### New Approaches Considered

1. **A: Delta review plus explicit verification (chosen).** Review the entire delta, including changes intended to fix earlier findings, and verify those findings individually. This reduces repeated review work and checks fixes for regressions, but requires reliable baseline and change evidence.
2. **B: Full review with filtered findings.** Retain a full PR review and suppress repeated or out-of-scope findings afterward. This simplifies review scope handling but retains the cost and attention demands of a full pass.
3. **C: Triage first, review additional changes separately.** Verify requested fixes and review only changes judged to go beyond them. This can be cheaper, but depends on distinguishing fixes from other changes and can miss regressions introduced by fixes. The user chose to review the entire delta instead.

### Updated Decision

Choose Approach A for both single-PR and bulk review: automatic incremental review from the authenticated user's latest trustworthy completed cc-review run, with `--full` to request a full PR review. First reviews and runs without reliable baseline or comparison evidence use full review and explain the reason.

The user explicitly confirmed automatic mode, a personal baseline, review of the entire delta including fixes, an evidence-backed critical-only exception for unchanged code, and verification plus acknowledgment for renewed review requests on proven unchanged contributions. The user also accepted the fallback, partial-fix, incomplete-coverage, independent-action and existing-approval defaults below.

### Agreed Key Requirements

**Mode and baseline**

- Apply the same automatic mode rules to single-PR and bulk runs. First reviews are full; follow-ups use the user's latest trustworthy completed cc-review run. Another person's review does not establish the user's baseline.
- Support `--full` as an explicit override. Incremental review does not require `--since-last`.
- Missing or unreliable baseline or diff evidence triggers a full review with an explanation. If the full review itself lacks necessary evidence or coverage, report it as incomplete.
- Incomplete runs cannot establish a completed baseline. Completion means the required review and verification work was performed, not that every finding was fixed or that the result was approval.

**Changed content and scope**

- Review the entire delta, including code changed to address earlier findings. Do not skip review merely because changes appear to be requested fixes.
- Let reviewers consult the full PR and surrounding code for context, while keeping ordinary new findings within the delta.
- Permit a new finding in code unchanged since the baseline only for a critical problem supported by concrete evidence. Distinguish such findings from delta findings and carried unresolved findings.
- Distinguish changes in the author's contribution from upstream movement during a rebase. Conflict resolutions or other substantive changes must not be classified as unchanged merely because a rebase occurred.

**Earlier findings and triage**

- Explicitly verify the user's unresolved earlier cc-review findings against current code, including findings from runs older than the chosen baseline. Record fixed, still present or unclear; absence from the new finding list is never proof of a fix.
- Resolve only verified fixes, respecting existing triage behavior for accepted explanations, disagreements, deferrals and questions. Partial fixes leave the remaining concern open in its existing thread.
- Missing or incomplete thread evidence cannot justify resolution or a claim that verification is complete.
- Review and triage use consistent verification outcomes and handled-activity rules. Either execution order must avoid duplicate replies, resolutions and reposted findings.
- Triage does not advance the code-review baseline or satisfy a separate review obligation. Review clears overlapping triage work only when the associated thread work was actually handled.

**Rebases and explicit requests**

- Proven unchanged author contribution after a rebase creates no new code-review work by itself and requires no new review post. Keep pending thread work independently actionable.
- A renewed explicit review request remains actionable even when the author contribution is proven unchanged: verify earlier findings and acknowledge the unchanged contribution. Do not automatically repeat a full review; `--full` remains available.
- Uncertain contribution equivalence is not proof of a rebase-only change. Use the explained full-review fallback when a trustworthy incremental comparison cannot be established.

**Reporting and boundaries**

- Report the mode, baseline, effective scope, fallback reasons and incomplete coverage. Distinguish new delta findings, carried findings, critical exceptions and verification outcomes.
- Apply the agreed scope across reviewers and reconciliation. Disclose coverage limitations instead of claiming that unsupported reviewers performed an incremental review.
- Keep existing posting, approval, worktree and author/reviewer-role restrictions. This feature does not introduce new automatic posting permissions.
- Keep inbox read-only and retain independent review and triage eligibility from #7. Any contribution evidence used to refine selection must preserve explicit requests, pending thread work and visible uncertainty.
- This brainstorm agrees behavior only. Formal specification, implementation planning, code, tests and user documentation follow separately under issue #8.

### Success Criteria

- A fix-only follow-up reviews its whole delta and verifies earlier findings without repeating the full PR review.
- A still-present, partially fixed or unverifiable finding is never resolved solely because a new reviewer did not rediscover it.
- Repeating review and triage at unchanged code and conversation state causes no duplicate thread actions or reposted findings.
- A proven rebase-only change avoids another code review while retaining pending thread work; a renewed request receives verification and acknowledgment.
- History rewrites, missing baselines and incomplete evidence produce explained fallbacks or incomplete results, never unsupported completion claims.
- Single-PR and bulk runs follow the same mode and baseline rules, and reports make scope and remaining work clear.

### Open Threads

The behavioral direction is agreed. The questions below remain for specification and planning; issue #8 tracks that follow-up work.

## Open Questions

- What evidence establishes a trustworthy completed personal baseline, including no-findings reviews, reviewer/configuration differences and chains of incremental runs?
- What comparison evidence reliably separates author changes from upstream movement across rebases, force pushes and conflict resolutions, and when is full-review fallback required?
- How should unsupported command-reviewer scope and incomplete reviewer coverage affect fallback, reporting and baseline completion?
- What shared verification evidence should review, triage and meta-review receive to preserve findings across moved code, avoid duplicates and enforce the critical-only unchanged-code exception?
- How should verification outcomes and new findings be presented between existing threads and the review summary, including acknowledgment of a renewed request on unchanged content?
