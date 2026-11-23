# Research: Bulk Issue Assessment

## R-001 Selection query and paging

- **Decision**: GraphQL `search(type: ISSUE, first: 20, after: $cursor, query: "repo:<r> is:issue is:open sort:created-desc <user query>")` with per-node detail in the same request, using real connection shapes (`nodes { ... }` plus `totalCount` and `pageInfo { hasPreviousPage }`): `author { login __typename }`, `authorAssociation`, `createdAt`, `comments(last: 100) { totalCount nodes { author { login __typename } authorAssociation body } }`, `timelineItems(itemTypes: [CROSS_REFERENCED_EVENT, CONNECTED_EVENT, DISCONNECTED_EVENT], last: 50) { totalCount nodes { __typename ... on CrossReferencedEvent { source { ... PR } } ... on ConnectedEvent { source { ... PR } subject { ... PR } } ... on DisconnectedEvent { source { ... PR } subject { ... PR } } } }` (the pull request side is whichever of `source` and `subject` is a PullRequest other than this issue) where `PR` selects `number url state merged author { login __typename } authorAssociation baseRepository { nameWithOwner } reviews(last: 50) { totalCount nodes { authorAssociation author { login __typename } } } comments(last: 50) { totalCount nodes { authorAssociation author { login __typename } } }`. Paging stops at the batch limit, `hasNextPage == false`, or the scan ceiling. Issues seen on an earlier page are deduplicated by number.
- **Truncation**: when any `last:` connection reports `pageInfo.hasPreviousPage` true (`totalCount` is informational only, since `timelineItems.totalCount` may count unfiltered events), the issue is skipped with reason `history_too_long` (spec FR-011b).
- **Rationale**: One request per page keeps 100 candidates within 5 calls. The user query is appended after the fixed qualifiers and validated first, so it cannot widen scope or reorder (FR-002, FR-004).
- **Alternatives considered**: REST `issues?state=open` plus per-issue calls (N+1 calls, no keyword search); `gh issue list --search` (no author association or timeline fields); paging truncated histories (more calls for a rare case).



## R-002 Maintainer and bot detection

- **Decision**: Maintainer means `authorAssociation` in `OWNER`, `MEMBER`, `COLLABORATOR`. An actor whose `author.__typename` is `Bot` (or login ends with `[bot]`) is never a maintainer. Comments by the issue author never count as answers (FR-006).
- **Rationale**: GitHub records the association on every comment, review and pull request, so the rule is deterministic and fixture-testable.
- **Alternatives considered**: Collaborator permission API per user (extra calls, needs push scope).



## R-003 Linked pull requests

- **Decision**: A pull request references an issue when the issue timeline has a `CrossReferencedEvent` or `ConnectedEvent` whose source/subject is a `PullRequest` with `baseRepository.nameWithOwner` equal to the target repository (case-insensitive), and no later `DisconnectedEvent` for the same pull request that is not followed by a cross-reference. Pull requests based on other repositories are ignored, because their `authorAssociation` is relative to that other repository. Skip (FR-007) when such a PR is `OPEN` or merged and (opened by a maintainer, or has a maintainer review or comment). PRs closed without merging never cause a skip (FR-008). Open non-maintainer PRs without maintainer activity are recorded for the "review linked PRs" choice.
- **Rationale**: Covers closing keywords and plain mentions as decided in review, with correct maintainer semantics.
- **Alternatives considered**: `closingIssuesReferences` only (misses plain mentions).



## R-004 Assessment marker and run marker

- **Decision**: "Already assessed" means any comment body containing `<!-- cc-review:assessment ` (the existing `HIDDEN_PREFIX`). Bulk posts append one extra line `<!-- cc-review:issue-bulk run=<run-id> -->`, rendered by `assessment.render` through a new optional `run_id` argument. On resume, a comment by the posting login with this run marker counts as posted (FR-020a).
- **Rationale**: Reuses the CI-compatible marker so CI and bulk runs see each other's work; the run marker makes resume idempotent without trusting local state alone.
- **Alternatives considered**: Recording only the local comment id (lost if the session dies between API success and the state write).



## R-005 Run state

- **Decision**: New `run_state.py` with JSON `state.json` per run (`schema_version`, `kind`, `run_id`, `status`, `options`, `repository`, `user`, `created_at`, `updated_at`, `items` keyed by string id, `extra` for kind-specific run fields). Writes go through a temp file plus `os.replace`. `init` writes `<root>/.gitignore` containing `*`, as `bulk-state.sh` does, so run state and nested worktrees never appear as untracked files in the maintainer's checkout. Run ids `YYYYMMDD-HHMMSS-issue[-N]`.
- **Rationale**: FR-029 and FR-031; atomic writes prevent half-written state on interruption.
- **Alternatives considered**: Extending `bulk-state.sh` (PR-shaped, see plan Complexity Tracking).



## R-006 Fix worktrees and branches

- **Decision**: `git fetch origin <default>` then `git -c core.hooksPath=<empty private dir> worktree add -b cc-review/fix-issue-<n> <run>/worktrees/<n> origin/<default>` (no checkout hook runs). Before that, refuse when the branch exists locally (`git rev-parse --verify refs/heads/...`) or remotely (`git ls-remote --heads origin ...`) and is not recorded in the run. Cleanup: `git worktree remove --force` and `git branch -D`.
- **Rationale**: Starts each fix from the current default tip (edge case), leaves the maintainer's checkout and branch list unchanged after cleanup (SC-006).
- **Alternatives considered**: `pr-worktree.sh` (detached PR heads, push to PR branches; different semantics).



## R-007 Measuring the small bound

- **Decision**: After the worker stops, `git add -A` in the worktree and `git diff --cached --numstat origin/<default>`; classify paths with fixed test patterns (`test/`, `tests/`, `spec/`, `__tests__/` directory segments; basenames `*_test.*`, `test_*.*`, `*.test.*`, `*.spec.*`). Bound: non-test files at most 3, non-test lines at most 100, test lines at most 300; binary files (`-` in numstat) count as a non-test file with 100 lines (abandon). Zero changed files means "no fix produced".
- **Rationale**: Deterministic and testable (FR-023, FR-030).



## R-008 No local test runs

- **Decision**: Fixes never run project tests, builds or hooks locally. The draft pull request body states: "Tests were not run locally; the repository's checks on this pull request run them." There is no test command detection or confirmation.
- **Rationale**: Plan review found that a fix worker influenced by untrusted issue text could change test code or the test runner, and a confirmation given before the code exists cannot cover that. Draft pull request checks run in the hosting service's sandbox.
- **Alternatives considered**: per-batch confirmation of a detected command (unsafe, see above); per-fix diff review before running tests (adds a prompt per fix and still executes model-edited code locally).



## R-009 Draft pull request creation

- **Decision**: `fix-measure` records the staged tree id (`git write-tree`). `fix-publish` performs recorded steps: commit with `git -c core.hooksPath=<empty private dir> commit --no-verify` only when `git write-tree` still equals the recorded tree (no re-add), message `<type>: <sanitized issue title, max 72 chars> (#<n>)` with `type` `fix` for bugs, `feat` for features, `chore` otherwise; push `git -c core.hooksPath=<empty private dir> push --no-verify origin cc-review/fix-issue-<n>`; `gh pr create --repo <r> --draft --head <branch> --base <default> --title <subject> --body-file pr-body.md`. The body contains the sanitized worker summary (closing keywords before any other issue reference neutralized for `#<m>`, `owner/repo#<m>` and issue URLs; `@` escaped by its own rule; `<`/`>` escaped via `assessment._safe`; at most 1,500 characters), `Fixes #<n>`, and the R-008 note. Commit failure abandons with "commit failed". A failed PR creation keeps `pushed` true and `pr_opened` false (status "PR pending") so resume retries; before creating, `gh pr list --repo <r> --head <branch> --state open --json url` adopts an existing PR (FR-025a).
- **Rationale**: Separates side effects so a crash between them is recoverable, pins the measured tree, and keeps model text from triggering closes or mentions.



## R-010 Prompt structure and harness degradation

- **Decision**: `commands/issue-bulk.md` mirrors `bulk.md`'s worker pattern: one assessment worker per issue and one fix worker per fix, each given only file paths and the untrusted-data boundary. Without subagents, the orchestrator processes items inline in sequence and states the context-accumulation warning (FR-032). The approval prompt is one question-tool call with two questions, Reply (Post, Edit, Skip) and Follow-up (Fix it or Review linked PRs, Leave it; omitted when neither applies), counted as one decision step. It uses the harness question tool with the full rendered text in the reply and in the Post option preview, per the "Showing Text to the User" rules already in `issue.md`.
- **Rationale**: Consistent with existing commands and the user's draft-approval rules.



## R-011 Labels and configuration

- **Decision**: Label names come from `ci.load_config(<checkout>/.cc-review/ci.yml)['labels']` when that file exists (YAML through `yq`, partial maps merged with defaults), else from the bundled `review/config/ci.yml`. Before adding, `gh api repos/<r>/labels/<url-encoded name>` checks existence; a 404 records `label: missing` and nothing is created (the add-labels REST endpoint would create missing labels).
- **Rationale**: FR-018 and FR-020; matches CI's configuration semantics.



## R-012 Fix worker containment

- **Decision**: Before dispatching a fix worker, `fix-prepare` records a checkout snapshot: maintainer `HEAD`, a hash of `git ls-files --stage -z` (works with unmerged entries), a hash of `git status --porcelain -z`, the local branch list, and a sha256 of a canonical `state.json` copy without the run's `updated_at` and the item's `fix` object. `fix-measure` recomputes them and abandons the fix ("worker touched files outside its worktree") on any difference. Where the harness supports tool restriction, fix workers receive only file read, edit and write tools.
- **Rationale**: Prompt instructions alone do not enforce FR-022a.
