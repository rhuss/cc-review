# Data Model: Inbox PR Actions

## Canonical PR evidence

Identity is host + repository + PR number. Fields include authenticated user, author, open state, draft flag, head OID, update time, linked review requests, cc-review reviews and review threads. Discovery reasons are facts from searches, including direct/team requests and prior personal review. Coverage records which fields/connections are complete.

Thread evidence contains exact node ID, root comment node/database IDs, root author/body/original review commit and provenance, resolution state, latest replies with IDs/authors/body/edit timestamps, and coverage. A root alias must preserve ownership when a latest-reply window omits the first comment. Missing decisive evidence is represented explicitly.

## PR action assessment

Each PR has independent `review` and `triage` assessments: `eligible`, `role`, `reason`, linked `evidence`, `uncertain`, `complete`, and an optional `exclusion`. Triage role is author or reviewer. Assessment does not change review baselines or service content. Limits are applied deterministically after eligibility with existing bulk ordering.

Bulk seeds retain existing fields and add `triage_role` plus assessment evidence. Old seeds without that field infer author role only when authored by the authenticated user; never infer reviewer permissions from an untrusted plan.

## Handled reviewer activity

The cache has schema version, host, repository, user and records keyed by PR/thread ID. Each record stores exact root identity, head OID, deterministic conversation digest, outcome, completion time, optional reply ID and resolution completion.

Outcomes include confirmed-fixed, still-present, accepted-explanation, deferred and unclear. Pending user questions/decisions remain attention items; preparing or skipping them does not mark work completed. A finalized no-post verification can be recorded without a remote bookkeeping comment.

The conversation digest includes stable identities, actors, full body hashes and edit timestamps from sufficient inspected history. Recognized activity-marker replies authored by the authenticated user are excluded to avoid self-reactivation. A changed head or digest invalidates a prior handled snapshot. Missing coverage cannot be treated as a matching fingerprint.

## Prepared reviewer action

A reviewer plan identifies role, PR/head and exact thread/root identity for every verified outcome. It includes the conversation digest/activity key, intended reply/resolution or user question, and a null prepared commit. The activity key also scopes retry markers on actual posted replies.

States: eligible → prepared (no writes) → approved → freshness checked → reply posted (if any) → resolution applied (if any) → handled. A stale, missing or closed target withholds the affected action. A crash between steps resumes from exact recorded/remote evidence; it does not repeat a completed post. Author plans retain their existing schema and behavior.
