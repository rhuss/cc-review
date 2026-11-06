# Contract: Drafting, Approval and Posting Flow

Extends `specs/005-bulk-review-triage/contracts/worker-protocol.md` (status-line protocol unchanged).

## Drafting step (single-PR Step 7.5 draft half; bulk worker (g), now the drafting worker)

Input: findings to post (`accepted.json` or `findings.json` minus fixed and carried), `facts.json`, `reviewers.json` (bulk), positive observations, history/continuity, `EXPECTED_HEAD`, `RUN_MARKER`, `CAN_REQUEST_CHANGES`, `REVIEW_EVENT_OVERRIDE`, `MAX_COMMENTS`, `<draft dir>`.

1. If `<draft dir>/draft.json` exists and its `inputs_key` equals `review_draft.py inputs-key` for the current inputs, reuse the draft: return immediately.
2. 7.5a to 7.5e and 7.5k2 as today (partition, history, matching, event type, truncation); 7.5f only collects proposed thread actions into `thread-actions.json` (no writes).
3. Write `slots.json` from the template fields of each finding. When the prose plugin is available, rewrite slot text only (`what`, `why`, `fix` of findings without `user_text`, `follow_up`, `went_well`), in place in `slots.json`.
4. `review_draft.py assemble`, then `review_draft.py lint`.
5. Lint findings other than `commit` → rewrite the affected slot text once with the findings as guidance, re-assemble, re-lint. A `commit` finding is never redrafted (stale).
6. `review_draft.py preview`.

Bulk worker returns `STATUS ok draft=<dir> fingerprint=<sha> lint=<n>` (or `STATUS failed reason=stale-commit`, `STATUS failed reason=<error>`). No write API call is allowed in this step.

## Approval (interactive modes only)

- Show `preview.md` in full, then ask: approve, edit, skip (bulk adds "stop, resume later").
- Edit: the user's words are applied to `slots.json` (text, `removed`, `attribution_override`) or to the event (downgrade only) with the file-write tool, never through a shell literal; then assemble, lint, preview, ask again. User-written text is marked `user_text: true` and is not rewritten.
- Approve: record `{answer: approved, fingerprint}`; skip: `{answer: skipped}`.
- Bulk: previews are answered one at a time in state order after all drafts exist; each answer is recorded immediately (`bulk-state.sh pr-set`). A resumed run skips PRs whose recorded approval fingerprint equals the draft fingerprint.

Unattended and non-interactive: no preview; a clean lint records `{answer: policy, fingerprint}`; a lint still failing after the redraft withholds (`withheld` in bulk, reported in the single-PR summary).

## Posting

1. Head check of `bulk.md` Apply (bulk), then `post-review.sh` with the recorded fingerprint.
2. Map results: `POSTED`/`FOUND` → record `review_id` (bulk `bulk-state.sh record`), show the link; `STALE` → stale; `CHANGED <reason>` → interactive: show the new items and ask post anyway, skip, or re-run later. "Post anyway" calls `post-review.sh` again with `--accept-changes <hash of the reason>`; skip and re-run later set `skipped` and `stale`. Unattended: `withheld`; `REFUSED` → ask again (show the current preview); `FAILED` → failed with reason; rc 75 → pause.
3. After `POSTED`, perform `thread-actions.json` with the existing 7.5f guard, freshness recheck, activity marker and record, using the approved reply bodies verbatim. Bulk does this in a subagent only when the file is non-empty.

`--accept-changes <hash>`: `post-review.sh` skips step 5 only when the hash of the current `CHANGED` reason equals the given value, so a further change after the user's choice still withholds.
