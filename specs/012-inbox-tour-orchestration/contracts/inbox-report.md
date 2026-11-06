# Contract: Inbox Report Structure

Output contract for the default (read-only) `inbox` run. Rendered as Markdown; no repository-provided HTML or terminal formatting.

## Header

One compact block: repository link, authenticated user, collection time, selected types, active-state/history scope, per-type limit. (Compressed form of today's header.)

## Group 1: Needs your attention (table)

A Markdown table, one row per attention item, ordered explicit-before-uncertain then most-recently-updated.

| Column | Content |
|---|---|
| Item | Type + number as a link (e.g., `[PR #109](url)`, `[Issue #44](url)`) |
| What | Short title / subject |
| Why you | Relevance in a few words (e.g., "tals asked you directly", "your PR, open P1 thread") |
| Certainty | `Explicit` \| `Inferred` \| `Uncertain` |
| Next step | Suggested action phrase (e.g., "Answer the comment", "Reply, then triage") |

Empty group: the row area says "None found in the inspected scope."

## Group 1 detail (below the table)

One block per attention item, in the same order:

```
### <Item> — <short title>
<situation: concise factual summary from collected evidence>
My take: <recommendation; may be "no response needed">
Evidence: <link(s)>
```

Rules:
- The factual situation keeps the explicit/inferred/uncertain discipline.
- "My take" is clearly labeled and separate from the situation; it is an opinion, never an obligation.
- At least one evidence link per item.

## Group 2 & 3: brief lists

"Waiting on others" and "No current action" render as two-column lists (item + what you are waiting on / state), not paragraphs. Empty groups say "None found in the inspected scope."

## Coverage account (compressed)

Keep per-type candidate/selected counts, omissions, capped searches, failed queries, unavailable types, truncated context, the detail-collection timeout, and every `scope.known_limits` entry. Consolidate repeated warnings. Never hide limits or claim an empty queue from a partial run.

## Read-only guarantee

Producing this report performs no write: no comment posted, no thread resolved, no branch pushed, no review/triage agent launched, no working-tree change (FR-006).
