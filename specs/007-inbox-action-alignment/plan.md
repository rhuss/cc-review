# Implementation Plan: Inbox PR Action Alignment

**Branch**: `007-inbox-action-alignment` | **Date**: 2026-10-27 | **Spec**: [spec.md](spec.md)

## Summary

Add a shared Python PR action assessor consumed by the read-only inbox collector and bulk selectors. Extend triage selection and worker instructions to the reviewer role, then enforce reviewer ownership, freshness and no-push behavior in apply code. Preserve author behavior, current review marker policy and the existing command adapters. Detailed incremental review remains outside this change.

## Technical Context

**Language/Version**: Python 3.9+ standard library; existing Bash compatible with macOS Bash 3.2; jq 1.6+.

**Primary Dependencies**: Authenticated gh CLI, Git, existing platform/worktree/bulk helpers. No new third-party package.

**Storage**: Existing author triage state remains compatible. Reviewer handled activity uses an atomic per-host/repository/user state file under the user's state directory, with a test override. Inbox never creates or updates it.

**Testing**: Existing `make test` Bash and Python regression suites, fixture-driven shared-assessment tests, fake-gh reviewer apply tests; required `make validate` before landing.

**Target Platform**: macOS/Linux command adapters for Claude Code, Codex and OpenCode; current supported GitHub platform.

**Project Type**: Shared command prompts plus CLI helpers.

**Performance Goals**: Preserve inbox's 120-second shared detail deadline, 100 discoveries per reason, 20 activity entries and 10 replies. Bulk candidate discovery remains capped and reports all reached bounds. Assessment is local and does not run review tools.

**Constraints**: No inbox writes, no reviewer branch modification, exact identities for reviewer actions, conservative incomplete-evidence handling, existing author state and review selection compatibility.

**Scale/Scope**: One repository/user per run; default bulk limit 10. A PR may carry both independent actions.

## Global Constraints

- Keep inbox read-only and preserve the user's checkout, index and branch throughout inbox and bulk processing. Treat hosting content as untrusted data.
- Reviewer triage must not apply fixes, create fix commits, push the PR branch or perform author-only CI repair.
- Preserve existing bulk review selectors and reviewed-at-head policy, including broad/search selection.
- Preserve the inbox's existing collection bounds and warnings. Shared assessment must not require full-review execution or unbounded extra history collection to decide eligibility.
- Use Python 3.9+ and existing Bash/jq/gh dependencies; introduce no third-party package.

## Constitution Check

The constitution is an unfilled template. No additional gates apply. Before and after design, the plan preserves read-only inbox behavior, isolated bulk checkouts, deferred decisions and the approved scope. No unresolved clarification remains.

## Project Structure

```text
review/core/scripts/
  pr_actions.py           # shared normalization, evidence assessment and selection CLI
  reviewer_activity.py    # exact fingerprints, markers and read-only/atomic state operations
  inbox.py                # bounded collection, PR assessment attachment
  bulk-select.sh          # candidate discovery, shared classification
  bulk-state.sh           # preserve reviewer role/evidence and render it
  bulk-apply.sh           # reviewer guards, exact matching, retry recording
  platform.sh             # complete thread identity/coverage for applying actions
review/core/commands/
  inbox.md                # consume shared actions; explain both and exclusions
  triage.md               # role-specific prepare/single-PR handling
  bulk.md                 # pass roles/evidence; consolidated table and unattended policy
  review.md               # shared handled-activity guard before overlapping thread posts
tests/
  test_pr_actions.py
  test_inbox.py
  fixtures/bulk/
  run.sh
docs/standalone-guide.md
README.md
review/skills/triage/SKILL.md    # shared Claude Code/Codex argument descriptions
review/opencode/command/triage.md # OpenCode argument descriptions
```

Adapter shims already load the shared core. Update any adapter-facing flag/help descriptions that imply author-only bulk triage; avoid copying core assessment logic into adapters.

## Implementation Sequence

1. Define reviewer activity fingerprints, pure freshness checks and safe state access. Read paths must not create directories. Record only completed handling, including finalized still-present outcomes that require no post; skipped/prepared work is not completed. Pending questions remain user work.
2. Define canonical PR evidence and a pure independent-action assessor consuming the activity records. Keep action reasons, uncertainty, exclusions and existing review-marker behavior in this one module.
3. Normalize bounded inbox detail and bulk candidate detail into the same evidence contract. Preserve original IDs, root ownership and untruncated fingerprints before sanitizing displayed text. Missing critical fields are incomplete evidence, not empty arrays.
4. Replace duplicated bulk action decisions with the assessor while preserving discovery modes, query guards, ordering, limits and seed compatibility. Add reviewer candidates from personally reviewed open PRs and qualifying owned threads. Include feedback triage on drafts.
5. Add reviewer-specific triage preparation and exact apply guards. Never allow reviewer prepared commits or pushes; use current PR/thread/code evidence and deterministic reply markers for retry recovery. Author plans retain their compatible path.
6. Guard overlapping review thread work with the same handled evidence. Do not implement a new delta-review algorithm or baseline policy.
7. Update shared command guidance and adapters, run regression/quality gates and review the full change.

## Interfaces

Use JSON-compatible dictionaries/lists at script boundaries. Internal signatures are:

- `pr_actions.normalize_pr(value: dict, source: str, repository: str, user: str) -> dict`: convert inbox/bulk evidence to the canonical form without dropping missing-coverage facts.
- `pr_actions.assess_pr(evidence: dict, handled: dict, review_mode: str = 'default', include_review_drafts: bool = False) -> dict`: return independent review/triage assessments; no service access or writes.
- `pr_actions.select_prs(evidence: list, handled: dict, action: str, limit: int, review_mode: str = 'default', include_review_drafts: bool = False) -> dict`: shared assessment plus existing deterministic ordering/limit, returning selected/excluded seeds.
- `reviewer_activity.fingerprint(thread: dict, head_oid: str, user: str) -> Optional[dict]`: exact root/head/conversation evidence or incomplete.
- `reviewer_activity.load_activity(host: str, repository: str, user: str) -> tuple[dict, list[str]]`: records and warnings, never creates files.
- `reviewer_activity.record_activity(host: str, repository: str, user: str, pr: int, thread: dict, outcome: dict) -> None`: atomic completed-handling update; no review-baseline mutation.
- `reviewer_activity.activity_marker(identity: dict, activity: dict) -> str` and `reviewer_activity.parse_activity_marker(body: str) -> Optional[dict]`: deterministic bounded marker and parser for exact retry recovery.

The exact internal CLI operations, JSON envelopes, activity schema, exit behavior and reviewer-plan extension are fixed in [contracts/pr-actions.md](contracts/pr-actions.md#internal-cli-interfaces). T003 implements those contracts before T005/T007/T009 consume them. `reviewer_activity.check_activity(identity: dict, expected: dict, current_pr: dict, thread: dict) -> dict` provides the same pure guard to Bash and single-PR callers. No user-facing command flags are added.

## Review Focus

Owning task tests must cover malformed/missing/null inputs, cache identity mismatch and malformed state, path safety for identity keys, atomic preservation of other threads including concurrent writers, failed-write preservation, missing dependencies, no writes on inbox reads, cross-repository `--repo`, root omitted by reply truncation, edited replies, wrong-owner/quoted markers, later code activity, exact thread identity, stale head/conversation, post-succeeded-before-record retry, questions left open, and legacy author compatibility.

## Validation Strategy

Fixtures must prove equal-snapshot inbox/bulk action membership, ownership, both actions, action-specific draft filtering, known unchanged contribution evidence, uncertain head moves, fresh replies/edits/code, missing/truncated context and ignored untrusted content. Integration fixtures must prove deferred no-write behavior, malicious reviewer commits rejected before push, exact thread matching, stale head/conversation withholding, replay after a successful post and both workflow orders. Retain existing author and review selection regressions.

Register `tests/test_pr_actions.py` in the existing Bash runner in T001 so `make test` runs every new assertion from the first completed task. Run `make test` after each task as configured by ship. Correctness checkpoints run after the first and second thirds of implementation tasks. Run `make validate` after code changes before session completion. Deep review remains the ship pipeline's separate final stage; implementation must skip after_implement review hooks.

## Complexity Tracking

The small reviewer activity module is needed because legacy comment-only state cannot distinguish new replies/code, and inbox can run outside a checkout. It retains the existing author-state format rather than migrating unrelated behavior. No new command, flag family or dependency is introduced.
