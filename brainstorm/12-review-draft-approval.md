# Brainstorm: Review Draft Approval

**Date:** 2026-11-02
**Status:** active
**Issue:** https://github.com/rhuss/cc-review/issues/13

## Problem Framing

Posted reviews go out under the user's GitHub name, but the user never sees the final text. In deferred bulk review the decision step records `post`, and the posting worker (`review.md` Worker Mode (g)) runs Step 7.5 non-interactively and submits right away. Single-PR interactive review has the same gap: 7.5g approves findings, then 7.5i to 7.5l rewrite, assemble and post without a preview.

The posted text is not a mechanical copy of the findings. The 7.5i prose rewrite and summary assembly add sentences of their own. The 7.5k summary template contains no attribution sentence at all, so lines like "I ran cc-review with several reviewer agents and curated what they found" are invented by the rewrite. In run `20261102-145811-review` (five PRs) the drafts:

- claimed curation on four PRs where the user chose "Post review" without the "Review findings" drill-down
- stated a `go test -race` result as verified, although nothing in the run recorded it
- contained typography defects (a missing space between sentences)
- lost the labeled comment structure (`**Why this matters**:`, `**Suggested fix**:`), because the humanizer smoothed "label: text" patterns into flowing prose and nothing checked the structure

**Success:** nothing reaches GitHub that the user has not read in full, the posted payload is byte-identical to the approved one (apart from the user's own edits), and nothing in it claims something about the user that the run cannot back.

**Anti-goals:** a preview the user has to click through for every PR without useful content; an "approved" payload that a later LLM step can still change; prompting in unattended or non-interactive runs.

## Approaches Considered

### A: Split Step 7.5 into draft and post, script-backed publishing (chosen)

Step 7.5 becomes two halves used by single-PR and bulk alike. The draft half runs 7.5a to 7.5k2, adds a fact-based attribution sentence, assembles comments from the fixed template, runs a lint script, and writes `review-payload.json` plus `preview.md`. The post half is a script: head, duplicate and conversation checks, then POST of the approved file unchanged (verified against the hash recorded at approval). Bulk worker (g) becomes a drafting worker.

- Pros: one code path for both modes; byte-identical posting enforced by a script, not a prompt promise; lint and post checks testable in `tests/run.sh`.
- Cons: larger restructuring of 7.5 and bulk apply; the 7.5l/7.5m recovery logic moves into a script.

### B: Draft-only flag on the existing posting worker

Worker (g) gets a draft-only flag and is called twice by bulk (draft, then post the approved payload); single-PR gets a preview step inserted before 7.5l; lint lives in prompt instructions.

- Pros: much smaller change.
- Cons: posting stays an LLM step, so "unchanged" is a request, not a guarantee; a prompt-based lint misses exactly the small defects it exists for; single-PR and bulk paths drift apart.

### Dropped: keep the prose rewrite out of the summary body

Removes invented claims from the summary, but adds no preview and does not protect inline comments. Does not meet the core requirement.

## Decision

Approach A. Publishing becomes a deterministic script step that posts only the approved payload, after fresh checks. The template structure is enforced by construction (the rewrite never sees the labels) and verified by the lint before the user sees the draft.

## Key Requirements

**Where the preview applies**
- Single-PR interactive review: after the 7.5g findings decision, draft, lint, preview, approve (or edit, or skip), then post.
- Deferred bulk review: per-PR preview and approval during apply (drafting must follow the fix rounds, since `["fix","post"]` posts what the rounds left).
- Unattended bulk and single-PR with `interactive: false` post directly, as today, but use the same draft, template assembly and lint. *(Claude's call: nobody is present to approve in non-interactive single-PR mode, so it is treated like unattended.)*

**Preview content**
- Review event (plain comment or request for changes), full summary body, every inline comment with path and line, summary-only findings with the reason they are not inline, and any remaining lint findings.

**Bulk apply in three passes** (user chose "all previews together" over one PR at a time)
1. Prepare: fix rounds and push for every PR with `fix`; then a drafting worker per PR with `post` writes `review-payload.json` and `preview.md`, with no write API calls.
2. Approve: show every preview in full, in state order; per PR ask approve, edit or skip. Record each approval immediately with a hash of the approved payload, so a resume does not ask again unless the payload changed.
3. Post: per approved PR, run head check, run-marker duplicate check (7.5m) and live conversation check (review threads and comment counts against the analyzed `threads.json` and `comments.json`), then POST the approved payload unchanged and record `review_id`. A moved head marks the PR stale as today. *(Claude's call: new threads or comments since analysis ask "post anyway, skip, or re-run later" for that PR.)*

**Edits** *(Claude's call)*: the user says in plain words what to change; the change is applied to the payload file with the file-write tool (never a shell literal), the lint re-runs, and the preview is shown again before the approval question.

**Attribution owned by core (Step 7.5k)**
- One fixed sentence built from a facts file, not written by the rewrite.
- `CURATED`: true only when the user went through findings one by one (bulk: `accepted.json` exists; single-PR: per-finding review in 7.5g). Only then may the text say the user curated or selected findings.
- `EXECUTED`: commands the run itself executed with their recorded outcome. Today that is only fix-round test runs; commands a reviewer agent reports running are not recorded and must be dropped or labeled as reported by an agent and not verified.
- A fixed statement that repro scenarios were derived from reading the code and not executed, unless they were.
- The 7.5i rewrite keeps this sentence verbatim (like the run marker) and adds no other first-person claims.

**Template structure kept by construction**
- Inline comments are assembled by script from the fallback template in `core/templates/reviewer-voice.md`: `**{severity}**: {what}`, `**Why this matters**: {why}`, `**Suggested fix**: {fix}`, `_Source: ..._`.
- The prose rewrite (humanizer, reviewer voice) receives only the text inside each slot, never the labels.
- The summary body is assembled from its fixed headings (`## cc-review Summary`, `### What Went Well`, `### Findings` with the table, `### Review Details`, marker lines); the rewrite touches only prose inside sections.
- Fix the contradiction in `reviewer-voice.md`: the examples use a title as the bold label (`**Null pointer dereference on line 42**:`). Change them to start with the severity label (`**Critical**:`, `**Minor**:`) so the examples match the fallback template, which becomes the single format contract.

**Lint (script) before the preview**
- Every inline comment has the three labels in order plus the source footer; the summary has its headings in order.
- Run-id marker present; `commit_id` equals the expected head.
- No em or en dashes.
- No first-person verification claims ("I ran", "I tested", "I verified", "I curated") that the facts file does not back.
- Basic typography (a sentence directly followed by another without a space).
- Failures go back to the drafting step once; anything left is shown next to the preview.

**Out of scope**
- Recording commands that reviewer agents run.
- Triage posting (replies, resolutions).
- Changing unattended behavior beyond using the shared draft, assembly and lint path.

## Open Questions

- Exact wording of the attribution sentence for each combination of `CURATED` and `EXECUTED`.
- Schema of the facts file (location under the scope or PR directory, fields, how fix-round test outcomes are recorded).
- How the conversation check compares threads and comments: counts only, or IDs, and which changes count as material.
- Where the hash of an approved payload is stored in single-PR mode, and whether a single-PR draft survives an interrupted session.
- Whether the post script replaces `post_review` in the platform layer or wraps it, and how 7.5m recovery maps onto it.
- How the severity title in the `reviewer-voice.md` examples is kept: drop it, or move it into the first sentence after the severity label.
