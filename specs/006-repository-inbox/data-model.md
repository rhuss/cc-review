# Data Model: Repository Inbox

No application state is persisted. Collection is a snapshot, not an atomic transaction.

## Snapshot

schema_version=1; repository, repository_url, host, user, collected_at; scope; sources; items; warnings.

Scope contains ordered selected types, limit_per_type, explicit since, effective discussion_since, active PR/issue state, and detail bounds.

## Source Coverage

type; status (ok/partial/unavailable); discovered unique candidates; selected count; queries (reason, total count, incomplete flag); warnings.

One successful reason makes a source usable; failed aliases make it partial. At least one usable source is required. Successful zero matches is an empty source, not a failure.

## Item

id, type, number, title, url, author, state, updated_at, reasons (ordered unique), detail, context_complete, warnings. Deduplicate within repository/type. A failed detail retains identity and reasons; deleted authors are null.

## Detail

Bounded typed GraphQL data: body and linked activity with actors/timestamps. PRs add draft/head/review commits, requested reviewers, checks, resolution/outdated markers. Issues add assignees/comments. Discussions add answer status, answer, comments/replies.

All connections expose totalCount/pageInfo. Any hasPreviousPage/hasNextPage flag or shortened text adds a path-specific warning and clears context_complete. Remove raw display controls without executing repository content.

## Assessment

Produced by the harness: one group, relevance, concise situation, suggested next action or waiting state, evidence URLs, uncertainty.

Groups: Needs your attention; Waiting on others; No current action. Relevance alone never assigns an action. Incomplete decisive context forbids a confident no-action verdict.
