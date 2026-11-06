# Data Model: Inbox Tour and Fan-Out

The feature adds no new persistent storage. It reuses the existing read-only snapshot and introduces a few in-flight conceptual entities used while rendering the report and running the tour.

## Reused: Snapshot (from `inbox.py`, unchanged)

Produced once per run into `$INBOX_TMP/snapshot.json`. Relevant shape (existing):

- `repository`, `repository_url`, `host`, `user`, `collected_at`
- `scope`: `types`, `limit_per_type`, `since`, `known_limits`, `detail_bounds`, detail timeout
- `sources[]`: per-type status and coverage counts/warnings
- `items[]`: each has identity (type, number, title, link), author, state, update time, `reasons[]`, `is_draft`, `detail` (comments, actors, timestamps, checks, thread/answer state), `context_complete`, `warnings`; PRs also carry the shared `assessment` (review/triage eligibility, role, evidence).

The tour and per-item subagents read this file. No field is added or removed.

## Attention item (in-flight, derived)

One entry in the "Needs your attention" group, derived from a snapshot item the assessment placed there.

- **identity**: type (`pr` | `issue` | `discussion`), number, title, link.
- **reasons**: all discovered relevance reasons (preserved, item shown once).
- **certainty**: `explicit` | `inferred` | `uncertain` (from the existing assessment discipline).
- **situation**: concise factual summary from collected evidence.
- **recommendation** ("my take"): the assistant's opinion on whether a response is worthwhile and what to do; may be "no response needed". Distinct from `situation`.
- **next_step**: the suggested action phrase shown in the table (e.g., "answer comment", "reply, then triage").
- **evidence_link**: at least one supporting URL from the item/event fields.
- **fan_out_action**: the mapping to a command (see below).

Ordering: explicit before uncertain, then most recently updated (unchanged from today).

## Tour selection (in-flight)

The set chosen for one tour batch.

- **items**: up to five attention items.
- **source**: `default-top-5` or `custom` (user-typed item numbers).
- **visited**: items already toured in this run (so "next five" = next unvisited attention items in report order, FR-010).

Validation: at most five items; every pick must be an attention-group item; invalid picks are rejected with a clear message.

## Fan-out action (in-flight)

The mapping from an attention item to how it is acted on.

- **pr** -> `review --pr N`, `triage --pr N`, or (several PRs) a batch into `bulk` via the explicit list.
- **issue** -> the `issue` command for that issue.
- **discussion** -> textual suggestion only (no command).
- **availability**: present only inside a local checkout of the target repo (FR-016); otherwise acting is reported unavailable.

## Bulk explicit list (selector input, new)

Input to the bulk selection path (FR-017).

- **prs**: ordered list of pull-request numbers, passed unfiltered by `inbox`.
- **resolution**: resolved through the shared assessor (`pr_actions.py select`) into the existing `{selected[], excluded[]}` contract, carrying bulk's own eligibility, role, reason, evidence, and exclusions.
- **selector kind**: recorded on the bulk run as `explicit` (alongside the existing `default`/`all-open`/`search`).

Constraints: `--prs` is mutually exclusive with `--all-open`, `--search`, and `--pr`; numbers must be positive integers.
