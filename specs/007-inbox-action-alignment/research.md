# Research: Inbox PR Action Alignment

## R1: One shared action assessor

**Decision**: Add a Python standard-library assessor with explicit normalization adapters for inbox and existing bulk inputs. Bulk shell discovery remains a shell integration point; it delegates eligibility rather than copying the rules.

**Rationale**: `bulk-select.sh` currently decides through jq while `commands/inbox.md` supplies model rules. Shared evidence and pure assessment prevent vocabulary and selection drift and are directly testable without live service calls.

**Alternatives**: Wording-only changes preserve the gap; explicit PR handoff leaves defaults inconsistent; a full model review inside inbox exceeds its role and budget.

## R2: Conservative follow-up review

**Decision**: Preserve current review selectors and marker ownership policy. Mark older-head candidates as uncertain possible follow-ups unless stronger evidence establishes the change. Accept reliable explicit unchanged-contribution evidence, but do not compute a new incremental delta in this feature.

**Rationale**: New commit identity alone does not establish substantive work. Detailed delta/baseline/rebase behavior is deliberately left to brainstorm #09.

## R3: Reviewer ownership and bounded history

**Decision**: Require the exact root author to match the viewer and root cc-review source attribution or the exact containing marked review. Collect root identity separately from bounded latest replies. Keep coverage flags and compute fingerprints from original text before display truncation.

**Rationale**: A PR-wide marker can belong to someone else; the current inbox's last-ten-comments window can omit the root. Incomplete roots or decisive activity must remain visibly incomplete.

**Source**: GitHub's [PullRequestReviewComment reference](https://docs.github.com/en/graphql/reference/pulls#pullrequestreviewcomment) exposes stable node identity, the containing review and the original commit. Prefer node identity for thread correlation; retain existing database IDs for the current reply API contract.

## R4: Reviewer activity separate from author legacy state

**Decision**: Add a small atomic cache at `${XDG_STATE_HOME:-$HOME/.local/state}/cc-review/reviewer-activity/<host>/<owner>/<repo>/<viewer>.json`, with `CC_REVIEW_REVIEWER_STATE_FILE` for isolated tests. Validate the stored identity. Missing state is normal; inbox reads do not create paths. Keep existing author state unchanged.

**Rationale**: `triage-state.sh` reads create files and records only handled time/action/reply ID. That is insufficient for fresh activity and cannot serve explicit-repository inbox outside a checkout.

**Alternatives**: Checkout-only state produces different results outside that checkout. Posting bookkeeping comments for no-post verification would create unnecessary remote activity. A bounded deterministic marker on real replies supports crash recovery while the cache records completed no-post outcomes.

## R5: Freshness and idempotent writes

**Decision**: Fingerprint exact thread/root identity, assessed head and conversation content/edits. Exclude the authenticated user's recognized handling replies from the conversation digest. Persist completed outcomes, not preparation or skipped work. A pending user question remains visible and is not silently treated as completed.

**Rationale**: Current bulk apply allows approximate path/line/author matching and any signed reply since run start. Reviewer actions need exact identity and activity-specific retry markers; author behavior stays compatible.

## R6: Enforcement in executable helpers

**Decision**: Carry reviewer role and evidence through bulk state and plans; enforce no prepared commit/push and exact fresh evidence in `bulk-apply.sh`. Recheck before each affected write and record posting separately from resolution.

**Rationale**: Prompt instructions alone cannot enforce no-push and stale-action constraints when a plan is replayed directly. Existing helpers already provide an appropriate enforcement boundary.

## R7: Incremental scope and compatibility

**Decision**: Add a narrow shared handled-activity guard to review's existing reconciliation. Do not replace its general absence heuristic, baseline policy or full-review pipeline here. Document those remaining choices as #09 follow-up.

**Rationale**: Both commands must avoid duplicating work already performed at the same activity version; broader review correctness belongs to the separate agreed brainstorm.
