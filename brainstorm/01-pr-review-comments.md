# Brainstorm: PR Review Comments

**Date:** 2026-08-03
**Status:** active

## Problem Framing

The cc-review engine produces findings locally (`review-findings.md`) but never posts them back to the PR. The triage command consumes PR comments from external bots (CodeRabbit, Copilot) and humans, but the review engine itself is invisible on the PR. This creates a one-way gap: cc-review reads from PRs but doesn't write back.

The goal is to close this loop so that cc-review posts its findings as inline PR review comments (like CodeRabbit does), with structured reasoning, and manages the lifecycle of those comment threads.

## Approaches Considered

### A: Post-Review Step with Individual Comments

Add a new step after findings are written. Post each accepted finding as an individual PR review comment via `gh api`. Summary posted as a separate issue comment.

- Pros: Simple API usage, real-time posting as findings are accepted
- Cons: Each comment triggers a separate notification, no formal GitHub "review" event

### B: GitHub Review Submission with Interactive Gate

Buffer all accepted findings after interactive local review, then post as a single GitHub review submission. One API call, one notification, formal review event.

- Pros: Single notification, proper GitHub review (shows as "changes requested" or "commented"), cleaner UX, maps to cc-review's gate concept
- Cons: All-or-nothing posting (entire batch at once), slightly more complex API usage

### C: Hybrid (Inline as-you-go + Final Review)

Post inline comments immediately on accept, then submit a formal review with summary body (no inline comments) at the end.

- Pros: Real-time feedback plus formal review structure
- Cons: Most complex, two API call types, inline comments aren't formally part of the review

## Decision

**Chosen: Approach B (GitHub Review Submission with Interactive Gate)**

The single-notification model respects the PR author's attention. CodeRabbit uses this pattern for good reason. The interactive local gate gives the reviewer control without polluting the PR with incremental posts. The review submission API naturally supports "REQUEST_CHANGES" vs "COMMENT" review types, which maps directly to cc-review's gate concept (Critical/Important findings = request changes, otherwise = comment).

## Key Requirements

### Trigger and Scope

- PR comments are only posted when `--pr <number>` is explicitly provided (opt-in)
- All findings go through the same pipeline, regardless of source (internal agents, CodeRabbit, Copilot, Codex)
- The existing local findings report (`review-findings.md`) is still written as before

### Interactive Local Review

- After the review agents complete and findings are merged/deduped, present findings locally before posting anything
- Critical and Important findings are presented one at a time: accept, reject, or edit each
- Minor and Notable findings are presented in batch: accept all, reject all, or cherry-pick
- Only accepted findings are posted to the PR

### Comment Structure

Every posted inline comment must include:
1. **What is wrong** (specific, referencing the code)
2. **Why this matters** (severity and impact)
3. **Proposed mitigation** (concrete fix suggestion)
4. **Source footer**: e.g., `_Source: correctness agent_` or `_Source: coderabbit (also flagged by: security agent)_`

### Prose Integration

- Detect the prose plugin at runtime
- If present, use a dedicated `reviewer` voice profile to shape comment text (concise, direct, explains reasoning without being preachy)
- If absent, fall back to a hardcoded template with the same structure (why / severity / mitigation)
- The voice profile is built into cc-review, not inherited from the project's prose config

### Review Submission

- One `gh api` call to `POST /repos/{owner}/{repo}/pulls/{pull_number}/reviews`
- Review body contains: agent-generated "what went well" highlights, table of accepted findings with file/line links, rejected count, gate outcome
- Review body lists all participating agents/tools: "Review by cc-review: correctness, architecture, security, production, test-quality, goal-alignment, coderabbit, codex"
- Review event type: `REQUEST_CHANGES` if any Critical/Important findings are accepted, `COMMENT` otherwise
- Run ID marker in body: `<!-- cc-review:run-id:UUID -->` for re-run detection
- Summary table includes a "Source" column showing which agent/tool produced each finding

### What Went Well (Summary Section)

- Agent-generated: a lightweight analysis pass identifies genuinely good patterns in the diff (solid error handling, good test coverage, clean abstractions)
- Listed in the review summary body before the findings table

### Re-run Lifecycle

- On re-review with `--pr`, scan for previous cc-review reviews (identified by `<!-- cc-review:run-id:... -->` marker)
- Resolve threads where the underlying code change fixes the finding
- Update threads that are still open with new context
- Post new findings that weren't in the previous run

### Triage Extension

- Extend the existing triage command to recognize cc-review's own threads (by marker or source attribution)
- When someone replies to a cc-review comment (e.g., "fixed in abc123" or "won't fix, this is intentional"), triage assesses the reply against the original finding
- If the reply indicates a fix was applied and the code confirms it: resolve the thread
- If the reply is a reasoned rejection and the assessment agrees: resolve the thread
- If the reply is unclear or the fix doesn't address the finding: leave open and optionally add a follow-up comment

### Source Attribution

- Every inline comment footer shows the source: `_Source: <agent-name>_`
- If multiple agents reported the same finding (after dedup): `_Source: <primary> (also flagged by: <others>)_`
- The review summary body lists all agents/tools that participated in the review

## Out of Scope

- GitLab support (GitHub-only via `gh` API for now)
- Parallel comment posting
- Auto-fix loop posting intermediate results to PR
- Fully autonomous posting without local interactive review
- Editing already-posted comments (only resolve/new, no in-place edits of comment text)

## Open Questions

- How should the "what went well" agent interact with the existing 6 review agents? Is it a 7th agent, or a post-processing step that reads the diff independently?
- Should the `reviewer` voice profile be shipped as a file in the cc-review plugin, or generated on first use via `prose:voice`?
- What happens when the PR diff is too large for the GitHub review API's comment limit? Truncation strategy or split into multiple reviews?
- Should the interactive local review support an "edit" action where the user can rewrite the comment text before posting?
