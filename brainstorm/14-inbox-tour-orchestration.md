# Brainstorm: Streamlined Inbox Report with Guided Tour and Fan-Out

**Date:** 2026-11-06
**Status:** active

## Problem Framing

The `inbox` report ([#07](07-repository-inbox.md), [#08](08-inbox-action-alignment.md)) is accurate but hard to read. Every item in "Needs your attention" is a numbered paragraph, so a busy repository produces a wall of prose with no way to scan it. The user wants two things on top of the existing read-only overview:

1. A streamlined report that can be scanned at a glance, with a table.
2. A way to work through the items one at a time, and to act on them directly through the existing `review`, `triage`, and `issue` commands rather than copying numbers into a separate command by hand.

What success looks like: open `inbox`, scan a table, read the detail only where it matters, then optionally step through the top items and launch the right command on the ones worth acting on, without inbox growing its own review or apply logic.

What would make this a failure even if it technically works:

- The streamlined report drops the per-item explanation that makes the overview worth reading. A terse table alone is a regression.
- Acting becomes implicit. The default run must stay read-only; nothing should post, push, or launch an agent as a side effect of asking "what needs my attention?".
- inbox reimplements review/triage/apply instead of delegating, so two code paths drift (the exact problem [#08](08-inbox-action-alignment.md) set out to avoid between inbox and bulk).

This deliberately reopens one decision from [#07](07-repository-inbox.md), which rejected the "interactive inbox" (Approach C there) to keep the command read-only. The user now wants that interactivity back, as an explicit opt-in layered on top of a still-read-only default.

## Approaches Considered

Two separate design questions came up: how to present the report, and how to drive the real commands when the user chooses to act.

### Report presentation

**Chosen: table plus detailed assessment section.** The "Needs your attention" group renders as a scannable table (item, what, why you, certainty, next step), followed by a detailed pass below it: one short block per item that explains the situation, the model's take on whether a reply is actually worth it, and the suggested action. "Waiting on others" and "No current action" become brief two-column lists. Scope and coverage compress to a couple of lines.

- Pros: scan the table, drop into detail only where it matters; keeps the explanation the report earns its keep from; directly fixes the readability complaint.
- Cons: the detailed section is still long for a busy repository, though it is now below the scannable index rather than the only entry point.

Rejected: a pure table with no prose (loses the explanation, a regression) and moving all depth into the tour only (the user explicitly wants the detail in the default report, not gated behind an opt-in).

### Fan-out to the existing commands

**A. Thin per-item launcher (tour-driven).** Each toured item ends with an offer to work on it now, launching the matching command for that one item: `review --pr N`, `triage --pr N`, or `issue` for an issue. Control returns to the tour. Discussions get a suggestion only (no command exists).

- Pros: smallest change; each command runs exactly as today with its own confirmations and write permissions; report and tour stay read-only; handles every item type; matches "act on what I am looking at."
- Cons: one item at a time, so several PRs mean several sequential runs; each launched command re-gathers context the snapshot partly already holds.

**B. Curated batch into bulk.** After the user picks a set, inbox groups it and hands the PRs to the existing `bulk` engine (a review and/or triage run seeded with exactly those PRs), and issues to `issue`.

- Pros: reuses bulk's worktree/decision-table/apply machinery; efficient for several PRs; extends the inbox/bulk alignment [#08](08-inbox-action-alignment.md) built, which already anticipated "an explicit PR-list handoff."
- Cons: bulk selects its own PRs today, so this needs a new "run on this exact list" entry point; issues still go one at a time; heavier, and the per-item tour intimacy is lost for the batch; PRs only.

**C (chosen). A as default, B as opt-in for multiple PRs.** The tour drives per-item delegation. When the selection has several PRs the user would rather not tour individually, offer to batch them into bulk. inbox stays a thin orchestrator in both paths and never reimplements review or apply.

- Pros: keeps the common case simple and read-only-by-default; reuses existing commands and their safety; adds the batch path only when it pays off.
- Cons: the one genuinely new piece either way is letting bulk accept an explicit PR list.

## Decision

Build all three together as one presentation-and-orchestration layer on `inbox`:

1. **Streamlined default report.** Scannable "Needs your attention" table, then a detailed per-item assessment section below (situation, the model's take on whether a reply is worth it, suggested action), keeping the explicit/inferred/uncertain markers. "Waiting on others" and "No current action" as brief lists. Compressed scope and coverage. The default run stays read-only.
2. **Opt-in guided tour** over the attention items: the user picks up to 5 (default: the top 5), steps through them one at a time with focused per-item context, then pages to the next 5 or re-runs.
3. **Opt-in fan-out (Approach C).** Per-item, launch `review` / `triage` / `issue` from the tour. For several PRs, offer to batch them into `bulk`. inbox orchestrates by delegating; it never reimplements review or apply.

The user confirmed:

- The default report keeps the detailed explanation and the model's own assessment, not just a table.
- The tour is opt-in; the streamlined report stays the default.
- The read-only boundary from [#07](07-repository-inbox.md) is reopened deliberately, as an opt-in. Report collection and rendering never act; acting is always a separate, explicit, user-initiated step.
- The opt-in is an **end-of-report prompt**, not a flag. (This is a deliberate reversal of the current command rule "return the report without an action menu." The report content stays read-only; the prompt is a separate interaction offered after rendering.)
- Fan-out delegates to the existing commands rather than inbox growing its own machinery.

## Key Requirements

### Streamlined report

- Render "Needs your attention" as a table that can be scanned without reading prose: at least item (type/number/link), what it is, why it is relevant to the user, certainty (explicit/inferred/uncertain), and the suggested next step.
- Below the table, a detailed section with one block per attention item: the situation from collected evidence, the model's take on whether a reply is worth it and what it would do, and the suggested action with its evidence link.
- Keep the explicit/inferred/uncertain discipline from [#07](07-repository-inbox.md)/[#08](08-inbox-action-alignment.md). The model's suggestion is layered on top as a clearly labeled "my take," so an opinion never reads as a manufactured obligation.
- "Waiting on others" and "No current action" render as brief lists (item plus what the user is waiting on, or the state), not full paragraphs.
- Scope line and coverage account survive but compress; coverage limits are never hidden.

### Guided tour

- Opt-in via an end-of-report prompt. The default report alone is complete and read-only.
- The user selects up to 5 attention items to tour; default is the top 5 in report order.
- The tour steps through the selected items one at a time with focused context per item, then offers to tour the next 5 or re-run.
- Proposed (model's call): the tour reads from the single collected snapshot and does not re-fetch, to preserve the collector's "collect once, read-only" boundary. Whether focused per-item context needs a subagent, and the fallback where subagents are unavailable, is an open question below.

### Fan-out orchestration (Approach C)

- Per item in the tour, offer to act: `review --pr N` or `triage --pr N` for a PR, the `issue` command for an issue. Discussions get a suggestion only.
- For several selected PRs, offer to batch them into `bulk` (review and/or triage) seeded with exactly those PRs. Issues are still handled one at a time via `issue`.
- inbox never reimplements review, triage, apply, posting, or merging. It decides what needs doing and launches the real command, which keeps its own confirmations and write permissions.
- The read-only report and tour never act on their own. Acting is always an explicit user choice at the end-of-report prompt or a per-item tour prompt.

### Constraints the user chose to own

- The read-only report works anywhere, including with `--repo owner/name` outside a checkout. Fan-out requires a local checkout, because `review`, `triage`, and `bulk` operate there. inbox should say so when acting is not possible.
- Launched commands retain their existing confirmation and write-permission behavior; inbox adds no new write authority of its own.

### New capability needed in a sibling command

- `bulk` must accept an explicit PR list to run on, instead of only selecting its own PRs. [#08](08-inbox-action-alignment.md) already listed "an explicit PR-list handoff" as a possible follow-up; this feature makes it a requirement. How the handoff reconciles inbox's assessment with bulk's own selection is an open question below.

### Success criteria

- A busy "Needs your attention" group can be scanned from the table alone, and the detailed section still explains each item and gives a recommendation.
- Running `inbox` with no further interaction changes nothing in the repository or working tree.
- From the tour, launching `review` / `triage` / `issue` on a single item runs that command exactly as invoking it directly would.
- Selecting several PRs and batching them produces the same bulk run as invoking bulk on that explicit list, with no duplicated or divergent selection logic.

## Open Questions

- Exact shape of the end-of-report prompt and the tour's per-item prompts, given the command's current "no action menu" rule that this feature deliberately relaxes.
- Does the tour work purely off the one-shot snapshot, or does a toured item need fresh context, and if so how does that stay within the collector's read-only "collect once" boundary?
- Does focused per-item context require a subagent (a Claude Code mechanism), and what is the fallback on harnesses without subagents (Codex, OpenCode) so the tour degrades gracefully rather than failing?
- Batch handoff into bulk: pass the explicit PR list and skip bulk's reselection, or reuse the shared action assessment from [#08](08-inbox-action-alignment.md) so inbox and bulk still agree on each PR's eligible actions? What happens when a toured PR is not eligible under bulk's own rules?
- Selection and paging UX for picking up to 5 items and moving to the next 5 (numbers, a multi-select prompt, ranges), and how it reads across the supported harnesses.
- How the model's "my take" recommendation is bounded so it stays an opinion the user can ignore and never hardens into a claimed obligation, consistent with the [#07](07-repository-inbox.md)/[#08](08-inbox-action-alignment.md) discipline.
- Which harnesses get the full interactive experience versus a reduced one, and whether the streamlined report (table plus detail) ships independently of the tour and fan-out.
