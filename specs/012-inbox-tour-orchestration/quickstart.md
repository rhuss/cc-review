# Quickstart: Validate Inbox Tour and Fan-Out

Runnable validation scenarios mapped to the success criteria. Run from a GitHub repository checkout with `gh` authenticated.

## Prerequisites

- `gh` CLI authenticated; a GitHub repository with several open PRs/issues that are relevant to the authenticated user.
- cc-review installed so `inbox`, `review`, `triage`, `issue`, and `bulk` resolve.
- `jq` and Python 3.9+ available (collector).

## Scenario 1 — Streamlined report (US1 / SC-001, SC-002, SC-005)

1. Run `inbox` in the repository.
2. Expect: a header block, then a "Needs your attention" **table** with one row per attention item carrying all five columns (Item, What, Why you, Certainty, Next step), then a detailed section with one block per item (situation, labeled "My take", evidence link), then brief two-column lists for "Waiting on others" and "No current action", then a compressed coverage account.
3. Verify (SC-002): `git status` is unchanged, and no comment/thread/branch activity occurred.
4. Verify (SC-005): every attention item has a situation line, a "My take" line, and at least one evidence link.

## Scenario 2 — Guided tour, default and custom selection (US2 / SC-006)

1. Run `inbox`; at the end-of-report prompt, accept the tour.
2. Accept the default top five. Expect items presented one at a time; after the batch, an offer of the next five (or fewer if that many remain) or a re-run.
3. Re-run and instead type specific item numbers (e.g., `1 3 5`). Expect exactly those presented; then "next five" offers the next unvisited attention items in report order.
4. Verify (SC-006): no batch ever exceeds five items; a next-batch/re-run choice is offered whenever unvisited attention items remain.
5. Decline case: run `inbox` and decline the prompt. Expect the command to end with the read-only report and nothing else.
6. Empty case: run `inbox` where no item needs attention. Expect no tour prompt.

## Scenario 3 — Fan-out to single commands (US3 / SC-003)

1. During a tour (inside a local checkout), choose to act on a PR and pick review (or triage).
2. Expect `review --pr N` (or `triage --pr N`) to run exactly as if invoked directly; on return, the tour resumes with the remaining selected items.
3. Choose to act on an issue; expect the `issue` command to run for that issue. For a Discussion, expect a textual suggestion only.
4. Verify (SC-003): the delegated run's outcome matches invoking that command directly on the same item.

## Scenario 4 — Batch fan-out to bulk (US3 / SC-004)

1. During a tour, select several PRs and choose the batch option.
2. Expect `inbox` to invoke `review --bulk --prs <list>` (and/or `triage --bulk --prs <list>`).
3. Independently run `bulk-select.sh review --prs <same list> --user <login>` and confirm the `{selected, excluded}` result matches what the batch used (SC-004): same selection, no divergent logic in inbox.
4. Include a PR bulk would exclude (e.g., a draft for review) and confirm it appears as an `excluded` entry, not silently dropped (FR-018).

## Scenario 5 — Acting unavailable without a checkout (FR-016)

1. Run `inbox --repo owner/name` from outside a checkout of that repo (or from a different repo's checkout).
2. Expect the full read-only report plus a clear statement that acting is unavailable in this context; the tour, if offered, does not offer fan-out.

## Scenario 6 — Cross-harness degradation (FR-019)

1. On a harness without subagent support, run the tour: expect inline sequential presentation rather than per-item subagents.
2. On a harness that cannot chain command invocations in one session, choose to act: expect the exact command printed as a text handoff instead of an in-session launch.

## Automated checks

- Report structure: drive the collector against a fixed snapshot fixture and assert the rendered table columns, detail blocks, and brief lists (extends `tests/test_inbox.py`).
- Explicit-list selection: assert `bulk-select.sh --prs` returns the shared-assessor `{selected, excluded}` shape and rejects `--prs` combined with `--all-open`/`--search`/`--pr`.
