# Feature Specification: Streamlined Inbox Report with Guided Tour and Fan-Out

**Feature Branch**: `012-inbox-tour-orchestration`

**Created**: 2026-11-06

**Status**: Draft

**Input**: Brainstorm `brainstorm/14-inbox-tour-orchestration.md`. Streamline the cc-review `inbox` report so it can be scanned, add an opt-in guided tour of the items that need attention, and let the user act on those items by handing off to the existing `review`, `triage`, and `issue` commands (and `bulk` for several pull requests at once). The default report stays read-only; acting is always an explicit, user-initiated step.

## Clarifications

### Session 2026-11-06

- Q: How does the user choose which attention items to tour and move through batches? → A: The end-of-report prompt offers the default top five; the user accepts that or replies with specific item numbers from the table (up to five), and after each batch a prompt offers the next five (the following attention items in report order) or a re-run.
- Q: When several pull requests are batched into `bulk`, which component decides eligibility? → A: `inbox` passes the explicit pull-request list to `bulk` without pre-filtering; `bulk` applies its own eligibility rules and surfaces any pull request it would exclude. `inbox` holds no separate selection logic.
- Q: How is focused context kept for each toured item? → A: On harnesses that support subagents, each toured item is presented via a per-item subagent reading only that item's slice of the collected snapshot; where subagents are unavailable, the tour falls back to inline sequential presentation.
- Q: After the user launches an action on a toured item, what happens to the tour? → A: Control passes to the launched command; when it returns, `inbox` resumes the tour with the remaining selected items (or the next-batch prompt).
- Q: Does the `inbox` read-only boundary also constrain the delegated commands? → A: No. The boundary applies only to `inbox`'s report and tour, which never act and never re-collect. Once the user explicitly launches `review`, `triage`, `issue`, or `bulk`, those commands operate normally with their own data collection, confirmations, and write actions.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Scannable inbox report (Priority: P1)

A maintainer runs `inbox` on a busy repository and wants to understand, at a glance, which pull requests and issues need their attention, without reading a wall of numbered paragraphs. They scan a compact table of the attention items, then drop into a detailed explanation only for the items they care about, where the report also tells them whether a reply is worth it and what it suggests doing.

**Why this priority**: This is the core complaint the feature addresses and the minimum viable improvement. It delivers value on its own, even without the tour or fan-out: the existing report becomes readable while keeping the per-item explanation that makes it useful.

**Independent Test**: Run `inbox` on a repository with several attention items and confirm the output leads with a scannable table (one row per attention item) followed by a detailed assessment section, with the other groups reduced to brief lists, and that nothing in the repository or working tree changed.

**Acceptance Scenarios**:

1. **Given** a repository with multiple items needing attention, **When** the user runs `inbox`, **Then** the "Needs your attention" group is rendered as a table with one row per item showing its identity and link, a short description, why it is relevant to the user, the certainty of the assessment, and the suggested next step.
2. **Given** the same report, **When** the user reads below the table, **Then** a detailed section explains each attention item's situation, gives a clearly labeled recommendation on whether and how to respond, and links to the supporting evidence.
3. **Given** a repository with items in the other two groups, **When** the report is produced, **Then** "Waiting on others" and "No current action" appear as brief lists rather than full paragraphs, and the scope and coverage information is present but compact.
4. **Given** any `inbox` run that produces only the report, **When** it completes, **Then** no comment is posted, no thread is resolved, no branch is pushed, no review or triage agent is launched, and the working tree is unchanged.

---

### User Story 2 - Opt-in guided tour of attention items (Priority: P2)

After reading the report, the maintainer wants to work through the top items one at a time instead of scanning everything at once. They accept an end-of-report prompt, pick up to five items (or take the default top five), and step through them one by one with focused context for each, then choose to continue with the next five or stop.

**Why this priority**: The tour improves how the user consumes the attention items but depends on the streamlined report existing first. It is independently valuable: a guided walkthrough helps even before any acting capability is added.

**Independent Test**: With a report already produced, accept the end-of-report prompt, confirm the user can select up to five items (default top five), that items are presented one at a time, and that after the batch the user is offered the next five or a re-run, all without any repository change.

**Acceptance Scenarios**:

1. **Given** a completed report with attention items, **When** the report finishes, **Then** the user is offered an end-of-report prompt to start a guided tour, and declining leaves a complete, read-only report.
2. **Given** the user starts a tour, **When** they are asked which items to tour, **Then** they can select up to five attention items and the default selection is the top five in report order.
3. **Given** a tour selection, **When** the tour runs, **Then** each selected item is presented individually with focused context, one at a time.
4. **Given** a completed tour batch, **When** it ends, **Then** the user is offered the next five attention items or a re-run of the tour.
5. **Given** fewer than five attention items exist, **When** a tour starts, **Then** all of them are selected and no "next five" option is offered.

---

### User Story 3 - Opt-in fan-out to the real commands (Priority: P3)

While touring an item, the maintainer decides to act on it. For a pull request they choose to review or triage it; for an issue they choose to work it with the issue command. When several pull requests are worth processing together, they batch them into one bulk run. In every case `inbox` hands the work to the existing command rather than doing it itself, and only when the user explicitly chooses to act.

**Why this priority**: Fan-out is the most advanced capability and depends on both the report and the tour. It turns the inbox into an orchestration step, but only on explicit request, so it is layered last.

**Independent Test**: During a tour inside a local checkout, choose to act on a pull request and confirm the matching command (`review` or `triage`) runs on exactly that pull request as if invoked directly; select several pull requests and confirm they are handed to `bulk` as an explicit list; confirm nothing acts without the user's explicit choice.

**Acceptance Scenarios**:

1. **Given** a toured pull request, **When** the user chooses to act, **Then** `inbox` offers to review or triage it and launches the matching existing command scoped to that pull request.
2. **Given** a toured issue, **When** the user chooses to act, **Then** `inbox` launches the issue command for that issue; for a Discussion, `inbox` offers only a textual suggestion because no command exists.
3. **Given** several pull requests selected during a tour, **When** the user chooses to process them together, **Then** `inbox` hands exactly those pull requests to `bulk` as an explicit list rather than launching each one individually.
4. **Given** any item in the report or tour, **When** the user does not explicitly choose to act, **Then** `inbox` performs no review, triage, posting, or merge action.
5. **Given** `inbox` is run without a local checkout of the target repository, **When** the report is produced, **Then** it states that acting is unavailable in this context and still delivers the full read-only report.

---

### Edge Cases

- No attention items: the end-of-report tour prompt is not offered; the report still shows the (empty) groups and coverage.
- Incomplete coverage (the collector could not inspect everything): the report discloses the gap, and the tour and fan-out operate only on what was collected, never implying the queue is empty.
- A selected pull request is not eligible for the action under the target command's own rules (for example a draft, or a pull request closed since collection): the divergence is surfaced to the user rather than silently dropped.
- A toured item's suggested command is not available in the current harness: the suggestion is given as text instead of being launched.
- The user selects more than five items, or an item that is not in the attention group: the selection is bounded to five attention items and invalid picks are rejected with a clear message.

## Requirements *(mandatory)*

### Functional Requirements

#### Streamlined report (User Story 1)

- **FR-001**: `inbox` MUST render the "Needs your attention" group as a scannable table with one row per item, each row carrying the item identity (type, number, link), a short description, the reason it is relevant to the user, the certainty of the assessment (explicit, inferred, or uncertain), and the suggested next step.
- **FR-002**: Below the table, `inbox` MUST present a detailed section with one entry per attention item, giving the current situation from collected evidence, a recommendation on whether a response is worthwhile and what to do, and a link to the supporting evidence.
- **FR-003**: The recommendation MUST be clearly labeled as the assistant's own judgment and MUST NOT be presented as an obligation; the existing explicit/inferred/uncertain discipline MUST be preserved.
- **FR-004**: `inbox` MUST render "Waiting on others" and "No current action" as brief lists (item plus what the user is waiting on, or the state) rather than full paragraphs.
- **FR-005**: `inbox` MUST keep the scope line and the coverage account in the report in compressed form, and MUST NOT hide coverage limits, source failures, or unavailable item types.
- **FR-006**: A default `inbox` run (report only) MUST remain read-only: it MUST NOT post comments, resolve threads, push branches, launch review or triage agents, or modify the working tree.

#### Guided tour (User Story 2)

- **FR-007**: After producing the report, `inbox` MUST offer an end-of-report prompt to begin an opt-in guided tour of the attention items; declining MUST leave a complete, read-only report.
- **FR-008**: `inbox` MUST let the user select up to five attention items for a tour, with the default selection being the top five in report order. The user MUST be able to accept the default or reply with specific item numbers from the table.
- **FR-009**: The tour MUST present the selected items one at a time, each with focused context. Where the harness supports subagents, that focused context MAY be produced by a per-item subagent reading only that item's slice of the collected snapshot; otherwise the tour presents items inline in sequence.
- **FR-010**: After a tour batch, `inbox` MUST offer to tour the next five attention items or to re-run the tour, where "the next five" are the next attention items in report order that have not yet been toured in this run (independent of whether the previous batch was the default top five or a custom selection).
- **FR-011**: The tour MUST operate on the data already collected for the report and MUST NOT trigger a fresh collection of repository state.

#### Fan-out orchestration (User Story 3)

- **FR-012**: During the tour, for each item `inbox` MUST offer to act on it by delegating to the matching existing command: `review` or `triage` for a pull request, the `issue` command for an issue. A Discussion MUST receive a textual suggestion only. After a launched command returns, `inbox` MUST resume the tour with the remaining selected items or the next-batch prompt.
- **FR-013**: When the user selects several pull requests to process together, `inbox` MUST offer to hand them to the `bulk` command as an explicit list instead of launching each pull request individually; issues are still handled one at a time.
- **FR-014**: Acting MUST be an explicit user choice made at the end-of-report prompt or a per-item tour prompt; `inbox` MUST NOT act on any item without that explicit choice.
- **FR-015**: `inbox` MUST NOT reimplement review, triage, apply, posting, or merge logic; it MUST delegate to the existing commands, which retain their own confirmation and write-permission behavior. `inbox` MUST add no new write authority of its own. The `inbox` read-only boundary applies only to the report and tour; a delegated command, once launched, performs its own data collection and write actions normally.
- **FR-016**: `inbox` MUST offer fan-out only when running inside a local checkout of the target repository; when it is not (for example when the repository is specified by name only, or when the current checkout is a different repository than the target), it MUST state that acting is unavailable and still produce the full read-only report.
- **FR-017**: The `bulk` command MUST accept an explicit list of pull requests to operate on, so that `inbox` can hand it exactly the selected pull requests.
- **FR-018**: `inbox` MUST pass the selected pull requests to `bulk` without pre-filtering them; `bulk` MUST apply its own action-eligibility rules to that explicit list and surface any pull request it would exclude, rather than silently dropping it. `inbox` MUST NOT hold a separate selection authority that could diverge from `bulk`.

#### Cross-harness behavior

- **FR-019**: The streamlined report MUST be available on all harnesses that currently support `inbox`. The guided tour and fan-out MAY offer a reduced experience where a harness lacks the required interactive or isolation capability, but MUST degrade gracefully (for example, sequential presentation) rather than fail.

### Key Entities *(include if feature involves data)*

- **Attention item**: an entry in the "Needs your attention" group. Represents one pull request, issue, or Discussion, with its identity and link, the reasons it is relevant to the user, the certainty of the assessment, the situation summary, the recommendation, and the supporting evidence links.
- **Tour selection**: the set of up to five attention items the user chooses for a single tour batch, ordered by the report order.
- **Fan-out action**: the mapping from an attention item to the command that would act on it. A pull request maps to `review`, `triage`, or (for several) `bulk`; an issue maps to the issue command; a Discussion maps to a textual suggestion only.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every item in the "Needs your attention" group is represented by exactly one table row carrying all five required columns, so the group can be understood from the table alone.
- **SC-002**: A default `inbox` run (report only, no explicit act choice) produces zero changes to the repository and the working tree.
- **SC-003**: Acting on a single toured item produces the same outcome as invoking the matching command (`review`, `triage`, or the issue command) directly on that item.
- **SC-004**: Batching N selected pull requests produces the same run as invoking `bulk` on that explicit list of N pull requests, with no separate or divergent selection logic in `inbox`.
- **SC-005**: For every attention item, the detailed section contains a situation explanation, a labeled recommendation, and at least one evidence link.
- **SC-006**: A tour never presents more than five items per batch and always offers a next-batch or re-run choice when more attention items remain.

## Assumptions

- The platform is GitHub, consistent with the existing `inbox`, `review`, `triage`, and `bulk` commands.
- The existing read-only collector and its single snapshot remain the data source; the report and the tour read from that snapshot, and the tour does not re-collect (assistant's proposal from the brainstorm, to preserve the "collect once, read-only" boundary).
- The existing `review`, `triage`, `issue`, and `bulk` commands are the only things that act; `inbox` orchestrates by delegating to them.
- The opt-in mechanism is an end-of-report prompt rather than a command flag (user's explicit choice in the brainstorm). This deliberately relaxes the current rule that the report returns without an action menu; the report content itself stays read-only, and the prompt is a separate interaction offered after rendering.
- "Up to five items per tour batch" and "default to the top five in report order" are the agreed bounds; report order keeps the existing rule of explicit before uncertain, then most recently updated.
- Discussions have no dedicated command, so fan-out offers them a textual suggestion only.
- Graceful degradation of the tour and fan-out across harnesses (assistant's proposal) covers harnesses that lack the interactive selection or context-isolation mechanism the richest experience uses.
- The reconciliation detail between `inbox` selection and `bulk` eligibility (reuse of the shared action assessment versus passing a raw list) is left to planning; FR-018 only requires that divergences are surfaced.

### Planning inputs (from spec review)

- The plan MUST validate that `inbox` can hand control to a delegated command (including the heavy `review` and `bulk` orchestrators, which spawn their own subagents or worktrees) and then resume the remaining tour items, on each supported harness. This call/return model is the feature's central orchestration risk; FR-019 graceful degradation applies where a harness cannot support it.
- The collected snapshot and its temporary storage MUST live until the tour completes. Today the collector deletes the snapshot immediately after rendering the report; the plan must move that cleanup past the tour lifetime, since the tour and any per-item subagents (FR-009) read the already-collected snapshot and no fresh collection is allowed (FR-011).
