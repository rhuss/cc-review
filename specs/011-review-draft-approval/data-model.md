# Data Model: Review Draft Approval

All files are JSON unless noted, written under the run's ignored state directories. `<draft dir>` is `$PR_DIR/post` (bulk) or `$REVIEW_RUN_DIR/post` (single-PR). `<facts>` is `$PR_DIR/facts.json` (bulk) or `$REVIEW_RUN_DIR/facts.json` (single-PR).

## Run facts (`<facts>`)

```json
{
  "curated": false,
  "executed": [
    {"round": 1, "command": "go test ./...", "outcome": "passed"}
  ]
}
```

| Field | Rules |
|---|---|
| `curated` | `true` only when the user answered every Critical and Important finding individually in the findings decision (FR-008). Written once at decision time; absent means `false`. |
| `executed[]` | One entry per fix round that ran the test step: `round` (int >= 1), `command` (string, empty for `no-test-command`), `outcome` in `passed`, `failed`, `no-test-command`. Appended by the fix worker (bulk) or Step 6 (single-PR) right after the tests ran. |

Written only through `review_draft.py facts-set` (atomic replace). Never written by the prose rewrite.

## Slots (`<draft dir>/slots.json`)

The assembly input. The drafting step fills it; the prose rewrite may change only the `text` values marked rewritable.

```json
{
  "event": "COMMENT",
  "commit_id": "<40-hex>",
  "run_marker": "<run-id>/pr-<n>",
  "completion": "<completion or incomplete marker line(s)>",
  "comments": [
    {"id": "F-3", "path": "a/b.go", "line": 42, "start_line": 40,
     "severity": "Important", "what": "...", "why": "...", "fix": "...",
     "source": "correctness agent (also flagged by: security agent)",
     "user_text": false, "removed": false}
  ],
  "summary_only": [{"id": "F-9", "severity": "Minor", "file": "x.md", "line": 3,
                     "description": "...", "source": "...", "reason": "outside the diff"}],
  "follow_up": "<prose or null>",
  "went_well": ["<bullet>", "..."],
  "counts": {"rejected": 2},
  "gate": "PASS",
  "reviewers": ["correctness", "coderabbit"],
  "repro_present": true,
  "attribution_override": null
}
```

| Field | Rules |
|---|---|
| `event` | `COMMENT` or `REQUEST_CHANGES`; an edit may only downgrade to `COMMENT`. |
| `commit_id` | Required; missing makes the draft stale (FR-014a). Not editable. |
| `comments[]` | Order is posting order. `path`, `line`, `start_line` not editable. `what`/`why`/`fix` rewritable unless `user_text` is true (edited by the user in 7.5g; FR-003a). `removed: true` drops the finding from inline comments, the findings table and the posted count (FR-016). |
| `follow_up`, `went_well` | Rewritable prose; `follow_up` present only with prior history (FR-004). |
| `attribution_override` | `null` normally; set only by a user edit at approval (FR-016). |

## Draft (`<draft dir>`)

| File | Content |
|---|---|
| `payload.json` | Exact submission body: `{body, event, comments[], commit_id}`. Produced only by `review_draft.py assemble`. |
| `thread-actions.json` | Array proposed by 7.5f, in posting order; empty array when none. Resolution entries (no `kind`, or `kind: "resolution"`): `{thread_id, reply_body, resolve, activity}`. Continuation responses of Follow-up Continuity: `{kind: "continuation", thread_id, source_id, reply_body, resolve: false}` (a reply in the existing thread) and `{kind: "pr-comment", source_id, source_url, reply_body}` (a linked PR conversation comment for a summary-only discussion, no `thread_id`). Continuation entries never resolve; `lint` applies the dash, spacing, claim and result rules to their `reply_body`, and the dash and spacing rules to every other `reply_body`. |
| `preview.md` | Rendered by `review_draft.py preview` from `payload.json` + `thread-actions.json` + `lint.json` (Markdown). |
| `lint.json` | `[{rule, location, message}]`, empty when clean. |
| `draft.json` | `{inputs_key, fingerprint, lint_attempts}`. |

`fingerprint` = SHA-256 of canonical JSON of `{"payload": payload, "thread_actions": thread_actions}`. `inputs_key` = SHA-256 of canonical JSON of `{expected_head, finding_ids_to_post, facts}`.

## Approval record

- **Bulk**: in `state.json` per PR: `.draft = {fingerprint, inputs_key}`, `.approval = {answer, fingerprint, at}` with `answer` in `approved`, `skipped`, `policy` (unattended/non-interactive checked draft).
- **Single-PR**: `<draft dir>/approval.json` with the same fields; lives for the session (spec assumption). Thread actions approved without a review add `thread_actions_only: true`; the draft then has no `payload.json` and the fingerprint covers `thread-actions.json` alone.

## Conversation snapshot

Analysis writes `$SCOPE_DIR/threads.json`, `comments.json`, `reviews.json` (existing) and `analyzed-at.json` (`{"analyzed_at": "<UTC ISO 8601>"}`, taken before the first conversation read). This feature requires each item's author to keep `login` and a bot indicator (`__typename`/`type` or `[bot]` suffix). The post check fetches the same three collections fresh and compares identities.

## PR status (bulk) transitions added

| From | Event | To |
|---|---|---|
| `applying` | lint still failing after redraft (unattended) | `withheld` (reason: lint findings) |
| `applying` | conversation change or history mismatch, unattended | `withheld` (reason) |
| `applying` | conversation change, user chose re-run later | `stale` |
| `applying` | user skipped at approval | `skipped`, or `actioned` with reason "fixes pushed, review not posted" when `.actions.pushed_sha` is set |
| `applying` | head moved or commit missing | `stale` (existing) |
| `applying` | posted (or found by marker) | `actioned` (existing) |

`withheld` is a final status for the run (like `stale`): the next run selects the PR again.
