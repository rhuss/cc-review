# Research: Inbox Streamlined Report, Guided Tour, Fan-Out

All decisions below resolve the spec's "Planning inputs (from spec review)" and the Stage-2 review findings. No `NEEDS CLARIFICATION` remain.

## R-001: Delegation / call-return model (central risk)

**Decision**: `inbox` fans out by invoking the matching existing command and then continuing its own tour loop. It never holds the delegated command's context. Single items use `review --pr N`, `triage --pr N`, or `issue`; several PRs use `review --bulk --prs <list>` and/or `triage --bulk --prs <list>`.

**Rationale**: The delegated commands already run as self-contained flows with their own fresh context, worktrees, and subagents (confirmed in `review.md` worker mode and `bulk.md`). `inbox` only needs to launch one and resume afterward, so "resume the tour" is just the inbox loop continuing. Nothing in `review`/`triage`/`bulk`/`issue` has to change to support resume. This keeps `inbox` a thin orchestrator (FR-015) and stays within each harness's existing ability to invoke a command.

**Alternatives considered**: (a) `inbox` keeps the delegated command inline in its own context: rejected, it would blow up context and couple inbox to each command's internals. (b) `inbox` reimplements a lightweight action path: rejected by FR-015 and by the #08 anti-drift goal.

## R-002: Cross-harness degradation of tour and fan-out

**Decision**: The streamlined report ships on all three harnesses. The tour and fan-out use interactive prompts and (for per-item context) subagents where available. Where a harness cannot chain command invocations in one session, fan-out degrades to printing the exact command(s) as a text handoff; where subagents are unavailable, the tour presents items inline in sequence.

**Rationale**: FR-019 requires graceful degradation rather than failure. The report is pure rendering and works everywhere. The richest experience (subagent per item, in-session delegation) is a Claude Code strength; Codex/OpenCode still get the report and a usable text handoff.

**Alternatives considered**: Requiring identical behavior across harnesses: rejected, it would force dropping subagent isolation and in-session delegation entirely.

## R-003: Bulk explicit pull-request list (FR-017)

**Decision**: Add an explicit-list selector to `bulk-select.sh` (a `--prs <n,...>` mode) that resolves the given PRs through the existing shared assessor (`pr_actions.py select`) and returns the same `{selected, excluded}` contract with bulk's own eligibility. Thread the list through `review.md`/`triage.md` bulk handoff into `bulk.md` as a new selector kind `explicit`.

**Rationale**: `bulk-select.sh` today offers only `default`, `all-open`, and `search` modes and `bulk.md` rejects `--pr`. Reusing the shared assessor (the same one #08 established for inbox/bulk alignment) means `inbox` and `bulk` keep one eligibility authority (FR-018, SC-004). Adding a selector kind is the smallest change that fits the existing selection/state machinery.

**Alternatives considered**: (a) `inbox` pre-filters PRs and calls bulk per-PR: rejected, it duplicates selection logic and loses bulk's batch machinery. (b) A brand-new command: rejected, bulk already is the batch orchestrator.

## R-004: Snapshot lifecycle vs tour lifetime (Planning input 2)

**Decision**: Move the `$INBOX_TMP` snapshot cleanup from immediately-after-report (current `inbox.md` Section 5) to the end of the whole command: after the user declines the tour, or after the tour/fan-out finishes. Keep cleanup scoped to the private temp dir only.

**Rationale**: The tour and any per-item subagents read the already-collected `snapshot.json` (FR-011, FR-009); deleting it right after rendering would break them. Delegated commands collect their own data and never read the snapshot, so their lifetime is independent.

**Alternatives considered**: Re-collecting for the tour: rejected by FR-011 and the collector's "collect once, read-only" boundary.

## R-005: Report structure (FR-001..005)

**Decision**: "Needs your attention" renders as a Markdown table (item+link, what, why you, certainty, next step), ordered explicit-before-uncertain then recency. A detailed section below gives one short block per attention item (situation, labeled recommendation, evidence link). "Waiting on others" and "No current action" are two-column lists. Scope and coverage are kept but compressed.

**Rationale**: Directly implements the agreed readability design: scan the table, read detail where it matters, keep the explanation that makes the report useful. Markdown tables render in all three harness terminals.

**Alternatives considered**: Pure table (rejected, loses explanation); detail only inside the tour (rejected, the user wants detail in the default report).

## R-006: Recommendation labeling and the obligation boundary (FR-003)

**Decision**: The per-item recommendation is rendered under an explicit "my take" label, separate from the factual situation line, and may say a reply is not worthwhile. The existing explicit/inferred/uncertain markers stay on the factual assessment.

**Rationale**: Keeps the assistant's opinion clearly distinguishable from the evidence-based assessment, preserving the #07/#08 discipline that an inference is never presented as an obligation while still giving the user the opinionated steer they asked for.

**Alternatives considered**: Folding the recommendation into the situation text: rejected, it blurs fact and opinion.

## R-007: Testing approach

**Decision**: Extend the existing shell/Python test pattern. Collector output is unchanged, so report-structure tests assert the rendered sections/columns from a fixed snapshot fixture; selection tests assert `bulk-select.sh --prs` returns the shared-assessor `{selected, excluded}` shape and rejects conflicting selectors. Prompt-flow behaviors (prompt offered only when attention items exist, read-only default, degradation) are covered by quickstart scenarios.

**Rationale**: Matches `tests/test_inbox.py` conventions; keeps deterministic checks on the parts that are scriptable and reserves scenario validation for the prompt-driven flow.
