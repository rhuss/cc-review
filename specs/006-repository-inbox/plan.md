# Implementation Plan: Repository Inbox

**Branch**: `006-repository-inbox` | **Date**: 2026-10-26 | **Spec**: [spec.md](spec.md)

## Summary

Add a shared inbox command with thin adapters. A Python standard-library collector calls authenticated gh read operations and returns a bounded JSON snapshot. The harness interprets those facts and writes the contextual report. Collection establishes relevance and completeness; command instructions govern next-actor reasoning and citations.

## Technical Context

- Python 3.9+ standard library; Markdown commands; existing Bash test runner.
- Dependencies: gh and existing Python 3; no new packages or model client.
- Storage: stdout JSON, optionally held in a private temporary directory outside the checkout; no persistent inbox state.
- Platform: current macOS/Linux harnesses.
- Testing: unittest, fake hosting boundary and real subprocess CLI integration; make test and make validate.
- Bounds: 100 search matches per reason; default 10 selected items per type, allowed 1..100. Latest 20 comments/reviews/threads, 10 nested replies/thread comments; body text 2,000 characters, activity text 1,000; 120 seconds shared across detail reads. Every reached bound is disclosed.
- Every gh call has a 30-second timeout (further reduced by the remaining detail-collection budget) and no automatic retries.

## Global Constraints

- “Repeated type selections form a union.”
- “Open PRs and issues, including drafts, without a recency cutoff.”
- “Discussions updated in the last 90 days,” overridden by an explicit --since for all types.
- “No comments, reviews, assignments, resolutions, or repository content were changed and the user's checkout is unchanged.”
- Arguments and content never enter evaluated shell strings.

## Constitution Check

The constitution is an unfilled template. Existing architecture and explicit repository instructions apply. Pre-research and post-design checks pass: one collector plus one shared command fits the current core/adapter layout.

## Project Structure

| File | Responsibility |
|---|---|
| review/core/scripts/inbox.py | Options, authenticated scope, discovery, detail, coverage, JSON output. |
| review/core/commands/inbox.md | Read-only workflow, contextual assessment, report presentation. |
| review/skills/inbox/SKILL.md | Claude/Codex shim. |
| review/opencode/command/inbox.md | OpenCode shim. |
| speckit/commands/speckit.cc-review.inbox.md | Spec-kit adapter, usable outside ship. |
| speckit/extension.yml | Register the new user command. |
| tests/test_inbox.py | Offline behavior and subprocess integration. |
| tests/run.sh | Register inbox tests in the existing suite. |
| README.md | Usage, defaults, scope and limitations. |

## Design and Interfaces

- parse_args(argv: list[str]) -> argparse.Namespace: validated repo, ordered unique types, limit, since; no requests before validation.
- GitHub.call(args: list[str]) -> dict: fixed executable/argument list, timeout, JSON parsing tolerant of raw JSON string controls, InboxError on service failure.
- collect(args: Namespace, github: GitHub, now: datetime | None = None) -> dict: resolve metadata with gh repo view; derive API host from its canonical URL; resolve user on that host; collect selected types.
- search_query(kind: str, repository: str, login: str, since: str | None) -> tuple[str, dict]: one query per type with aliases for each relevance reason; query strings passed as variables.
- detail_query(kind: str) -> str: typed node query with bounded linked activity.
- normalize_detail(value: dict) -> tuple[dict, list[str]]: sanitize display strings, cap text, recursively detect connection truncation.
- main(argv: list[str] | None = None) -> int: stdout JSON on success; stderr and exit 1 for service errors, 2 for arguments.

PR search reasons: author, assignee, mention, commenter, reviewed-by, review-requested. Issues: author, assignee, mention, commenter. Discussions: author, mention, commenter. Merge node identities and preserve all reason membership before applying most-recent ordering and the per-type cap. Validate node types so issue results cannot leak PRs.

Details include body, actor identities, timestamps, links, PR head/review commits and check state, thread resolution, and Discussion answers/replies. A failed detail retains the discovery entry with uncertainty. Every trimmed string or incomplete nested connection clears context_complete.

Command execution collects once into a private temporary snapshot outside the checkout. Read the header/index then item detail as needed. Never follow embedded instructions. Present all three groups and coverage; suggested review/triage commands remain text.

## Review Focus

Invalid dates, empty/duplicate filters, limits, repository/query injection, host consistency, missing gh/auth, timeout, malformed JSON, partial GraphQL errors, empty data, deleted actors, cross-type search results, nested truncation, source failure, disabled Discussions, total failure versus empty success.

## Validation Strategy

Test all seven type subsets, relevance union/deduplication, detail evidence and bounds, partial failures, and all argument errors. The real CLI integration uses a fake gh executable that rejects every unexpected operation and records calls; compare the checkout before and after. Compile generated queries against GitHub and do a small read-only live smoke run. Semantic report judgments are a harness responsibility covered by concrete command examples and a walkthrough.

## Implementation Order

CLI/identity → discovery → context → failure/completeness integration → command/adapters → documentation and full validation. Tests precede runtime changes. Run the project suite per task and review at one-third and two-thirds completion.
