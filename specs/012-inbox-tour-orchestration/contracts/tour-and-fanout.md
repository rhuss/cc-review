# Contract: End-of-Report Prompt, Guided Tour, Fan-Out

Behavioral contract for the opt-in layers that follow the read-only report.

## End-of-report prompt

- Offered only when the "Needs your attention" group is non-empty AND the harness is interactive.
- Declining (or a non-interactive run) ends the command with the read-only report intact.
- This is the single deliberate relaxation of the current "return the report without an action menu" rule. The report content above the prompt is already complete and read-only.

## Tour selection

- On accept, offer the default top five attention items, or let the user type specific item numbers from the table.
- Cap: five items per batch. Invalid picks (non-attention items, more than five) are rejected with a clear message.
- After a batch: offer the next five unvisited attention items in report order, or a re-run. When fewer than five attention items remain unvisited, offer only what remains; when none exist, do not offer a next batch.

## Tour presentation (per item)

- Items are presented one at a time.
- Where the harness supports subagents: a per-item subagent reads only that item's slice of `snapshot.json` and returns its focused briefing (situation, evidence, suggested action). Clean context per item.
- Where subagents are unavailable: present inline in sequence (FR-019).
- The tour reads only the already-collected snapshot; it never triggers a new collection (FR-011).

## Fan-out (per item, explicit choice only)

- Each toured item offers "work on it now." Nothing acts without this explicit choice (FR-014).
- Mapping:
  - PR -> `review --pr N` or `triage --pr N` (offer both when both apply; do not choose precedence).
  - Issue -> the `issue` command for that issue.
  - Discussion -> textual suggestion only.
- Several selected PRs -> offer a batch: `review --bulk --prs <list>` and/or `triage --bulk --prs <list>` (see bulk-explicit-list contract).
- Call/return: `inbox` invokes the command, then resumes the tour with the remaining selected items or the next-batch prompt. `inbox` keeps none of the delegated command's context.
- Availability: fan-out is offered only inside a local checkout of the target repo. Otherwise the report states acting is unavailable and still delivers the full read-only report (FR-016).
- Degradation: where a harness cannot chain command invocations in one session, print the exact command(s) as a text handoff instead of launching (FR-019).

## Snapshot lifecycle

- The private temp dir / `snapshot.json` is removed only at the true end of the command: after the user declines the tour, or after the tour/fan-out completes. (Moved from the current immediately-after-report cleanup.)
- Cleanup stays scoped to the private temp dir; the project and its configuration are untouched.
