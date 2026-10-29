# Research: Issue Assessment

## R1: Shared command and thin adapters
Existing inbox shims resolve core then delegate. Add assess through the same paths and register the spec-kit command. The native plugin manifests discover skill directories automatically; no version bump or duplicate command engine is needed.

## R2: Bounded collector
Reuse inbox.GitHub.call for timeout, dependency, and JSON failures; use a static issueOrPullRequest query so numeric PR targets are rejected correctly. Pass number through gh -F to preserve its integer type. Do not reuse inbox discovery, because this workflow selects exactly one explicit issue.

## R3: Evidence and limits
Collect opening body and latest 50 comments in one query. Keep source metadata and total/page information. Limit display text and mark shortening, malformed comments, and partial GraphQL responses explicitly. The agent must inspect all collected decisive context before judging absence.

## R4: Local project provenance
Capture matching origin and checkout root with bounded read-only git commands; compare repository identity, not the current directory name. A foreign or absent checkout is a visible limitation. Do not clone, switch branches, or borrow this plugin repository's policy when assessing a different project.

## R5: Reply composition
Existing review detects prose through harness-exposed humanizer skills. Use that mechanism with a separate maintainer voice; inline invocation respects repository restrictions on subagents. If prose is absent, use bundled wording guidance. Prose changes wording, never evidence, decision, or uncertainty.

## R6: Scope and authorization
Initial command never posts or mutates. A later explicit posting request is a separate workflow, not an assessment option. No bulk mode, persistent scoring, or automatic inbox invocation.
