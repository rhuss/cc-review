# Research: Repository Inbox

## R-001: Contextual reasoning belongs in the command

Decision: deterministic Python standard-library collector plus a shared Markdown workflow. The host agent interprets conversations from collected evidence.

Rationale: involvement is a discoverable fact; responsibility depends on context. A second model client adds authentication and duplicates the harness. A metadata-only list would miss the chosen contextual behavior.

## R-002: Discover each relevance reason

Decision: query explicit author/assignee/mention/comment searches, plus separate manual-review and requested-review searches for PRs. Merge matches while preserving reasons. Requested-review search includes team requests using GitHub's documented semantics.

Sources: [issue and PR search](https://docs.github.com/en/search-github/searching-on-github/searching-issues-and-pull-requests), [review-request semantics](https://github.blog/news-insights/product-news/easily-filter-review-requests-by-team/).

## R-003: Discussions are a separate source

Decision: GraphQL DISCUSSION searches for author/commenter, then typed details with answers and nested replies. A live check on cli/cli showed `mentions:` returns 0 for DISCUSSION search and `involves:` matches exactly the commenter set, so mention-only Discussions cannot be discovered; this is disclosed as a known limit. `isAnswered` is null for categories that cannot be answered, so details also read `category { isAnswerable }`.

Rationale: Discussions are distinct from issues. Documented participation and date filters match the need. Live schema inspection confirmed closed, answer/isAnswered, and backward reply pagination.

Sources: [Discussions GraphQL guide](https://docs.github.com/en/graphql/guides/using-the-graphql-api-for-discussions), [Discussion search](https://docs.github.com/en/search-github/searching-on-github/searching-discussions).

## R-004: Bounded snapshots with visible gaps

Decision: bound search, selection, body text, activity and nested replies; record source and item coverage recursively.

Rationale: exhaustive crawling has unpredictable cost. Silent recent-page selection would misrepresent absence of actions. Search hits beyond limits remain explicitly undiscovered.

## R-005: Read-only host-consistent transport

Decision: gh argument arrays, canonical repository URL's host for identity and query calls, GraphQL query operations only, finite timeout, no retries or checkout operations.

Rationale: reuse authentication and avoid shell evaluation. Snapshot output can live temporarily outside the project.

## R-006: Existing test infrastructure

Decision: unittest integrated into tests/run.sh; mock only hosting I/O and also execute the real collector against a fake gh subprocess.

Rationale: meaningful runtime regression checks need no new framework. Contextual language judgments belong to the command walkthrough.

## R-007: Managed account identifiers

Decision: accept underscores in authenticated logins and repository owner namespaces while preserving the query-safe identifier character set and leading-character restrictions.

Rationale: GitHub's managed account format includes an underscore suffix. CodeRabbit identified the rejected-identifier case; regression tests reproduce and verify the correction.

Source: [GitHub username considerations for external authentication](https://docs.github.com/en/enterprise-cloud%40latest/admin/managing-iam/iam-configuration-reference/username-considerations-for-external-authentication).
