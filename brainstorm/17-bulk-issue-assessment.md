# Brainstorm: Bulk Issue Assessment with Optional Fixes

**Date:** 2026-11-23
**Status:** spec-created (specs/014-bulk-issue-assessment)

## Problem Framing

New issues from other people never reach the maintainer through cc-review today. The inbox discovers only items tied to the user (authored, assigned, mentioned, commented, reviewed, review requested; `review/core/scripts/inbox.py`), so an issue opened by a stranger stays invisible until someone touches it. The `issue` command assesses one issue at a time and must be pointed at an explicit number. CI can assess new issues automatically, but the user switched issue assessment to on-demand and wants to approve every reply before it is posted.

The inbox run on 2026-11-22 showed a related limitation: the per-type cap cut off issues without any way to keep going ("--limit 15 would include them").

The goal is a way to work through incoming issues in batches: select issues matching labels and keywords, skip those already handled, assess each one, approve and post the replies one by one, and for small issues optionally fix them right away as a draft PR. PRs already have this shape through `review --bulk --all-open` / `--search`; issues are the missing side.

Success: a maintainer can clear a batch of untouched incoming issues in one sitting, every posted reply was seen and approved, small confirmed problems turn into draft PRs without manual setup, and nothing drops out silently.

Anti-goals:

- Posting anything without the maintainer's per-issue approval.
- Implementing anything that is not small, or that the assessment did not recommend pursuing.
- Touching the maintainer's own checkout.
- Silently skipping issues: every skip has a stated reason in the report.
- Turning the read-only inbox into a write command.

## Approaches Considered

### A: `issue --bulk`, built like `review --bulk`, script-first (chosen)

Add a bulk mode to the `issue` command that follows the bulk review structure: selection, resumable run state, fresh context per issue, a decision step, worktrees for fixes. The deterministic parts (argument handling, selection with paging and skip rules, run state, loop control, fix PR creation, report counts) live in scripts; the prompt only covers judgment and conversation.

- Pros: one mental model for PRs and issues; reuses proven bulk patterns (resume, worktrees, per-item workers); inbox stays read-only; the "review PR #M" handoff goes straight into `review --bulk --prs`; script-first keeps the new flow deterministic and gives the later runner refactor a template.
- Cons: a third item kind next to the PR-shaped `bulk.md`; creating a PR from an issue is new capability either way.

### B: "New issues" mode inside the inbox

The inbox gets a second discovery mode and its guided tour hands each issue to `issue`, then runs fixes.

- Pros: closest to the original phrasing; one command to look at.
- Cons: the inbox is read-only and collects once by design; the tour hands off one item at a time in the same context (the accumulation bulk mode exists to avoid); five-item batch cap; it would need write and push authority it deliberately lacks.

### C: A plus an inbox pointer

As A, and the inbox report gains a line such as "12 new unassessed issues match; run `issue --bulk`", with a list handoff like `--prs`.

- Pros: discovery stays in the inbox without writes there.
- Cons: needs one shared definition of "unassessed", or the counts drift.

### Dropped: CI scheduled sweep

The CI sweep already picks up unfinished items, but it posts unattended. The maintainer wants per-issue approval, so it does not fit.

## Decision

Approach A, built script-first. C's inbox pointer is a small follow-up once the selection and skip rules exist in one shared place.

Moving review and triage bulk onto a deterministic runner is a separate project, recorded in [#18: Bulk Runner Scripts](18-bulk-runner-scripts.md). Issue bulk should not wait for it, but its shared pieces must not assume PRs, so they can become that runner's base.

## Key Requirements

### Selection

- Candidates are open issues in the repository, regardless of author, including issues opened by maintainers (for example the maintainer's own upstream reports).
- Filters: labels and optional keywords against title and body. When both are given, an issue must match both. *(My call: AND keeps noise down.)*
- Newest issues first. *(My call.)*
- `--limit N` is the batch size, default 10 like the inbox.
- Paging: when skip rules leave a batch short, selection continues into older candidates until the batch is full or candidates run out. A scan ceiling bounds the number of candidates inspected so a large backlog cannot stall the run. *(Ceiling is my call.)*

### Skip rules ("already worked on", broad meaning)

- The issue carries a cc-review assessment marker (`<!-- cc-review:assessment`).
- A maintainer already replied. Maintainer means a commenter GitHub records as owner, member or collaborator. *(My call: the role is on every comment.)*
- A linked or referencing PR exists **and** a maintainer opened it or has already reviewed or commented on it.
- A linked PR from a non-maintainer with no maintainer activity does **not** cause a skip. Otherwise an issue plus its "Fixes #N" PR opened by the same newcomer would fall through: the issue skipped, the PR possibly missed by a label search or excluded as a draft, and the need-and-fit question never asked.
- The final report lists every skipped issue with its reason (for example "skipped: maintainer PR #M").

### Assessment pass

- Each issue is assessed in a fresh context, with the same judgment as the `issue` command (`templates/need-and-fit.md`, `templates/issue-assessment.md`, maintainer voice): need, fit, recommendation, reply draft.
- The assessment also marks whether the issue is fix-eligible: recommendation Pursue, the problem confirmed in code (or a clearly bounded small change), and touching only a few places.
- When a non-maintainer PR is linked, the assessment mentions it and the reply may refer to it.
- Issue content stays untrusted data, as in the existing command.

### Approval pass (one issue at a time)

- The maintainer sees the full reply draft and chooses post, edit or skip. Posting applies the recommendation label.
- For fix-eligible issues, a separate choice: fix it, or leave it. This is independent of posting.
- For issues with a non-maintainer linked PR, the fix choice is replaced by "review PR #M", which hands the PR to `review --bulk --prs` after the approval pass.

### Fix pass (after all approvals)

- Fixes run one at a time, each in its own worktree with a fresh context. The maintainer's checkout is never touched.
- Each fix pushes a branch and opens a **draft PR** under the maintainer's account that says "Fixes #N". The draft PR is the review checkpoint; no diff approval before it opens.
- The fix runs the project's own tests when the project documents how; the PR body states the result either way.
- A fix that fails or grows beyond small opens no PR and is reported back. The posted reply stays.

### Report

- Per issue: posted, skipped (with reason), draft PR link, PR handed to review, or fix abandoned (with reason).
- Coverage: candidates scanned, skipped by reason, scan ceiling reached or not.

### Construction constraints (user-owned)

- Script-first: arguments, selection, paging, skip rules, run state, loop control, fix PR creation and report counts are deterministic scripts. The prompt holds only judgment and conversation.
- Shared pieces are written without PR assumptions, so the later runner refactor (#18) can adopt them.
- The existing single-issue `issue` command keeps its behavior.

## Open Questions

- Command surface: `issue --bulk --search '<query>'` mirroring review, or dedicated `--label` / `--keyword` flags translated into a query?
- Exact definition and default of the scan ceiling, and how reaching it is reported.
- How "small enough to fix" is judged reliably, and what the fix worker does when a fix turns out larger mid-way.
- Branch naming, PR title and body template for fix PRs, and behavior when the maintainer lacks push rights or the repository is a fork.
- Does run state need resume across sessions as in bulk review, and what happens to queued fixes when a run is interrupted after posting?
- Should `review --bulk` selection adopt the same paging rule (fill the batch past exclusions) for consistency?
- Which harnesses get the full flow, and how Codex/OpenCode degrade without subagents.
- Shared source of the skip rules for the later inbox pointer (approach C).
