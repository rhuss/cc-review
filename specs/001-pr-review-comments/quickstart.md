# Quickstart: PR Review Comments

## Prerequisites

- `gh` CLI installed and authenticated (`gh auth status`)
- A GitHub repository with an open PR containing code changes
- cc-review plugin installed

## Validation Scenario 1: Basic PR Review Posting

**Goal**: Verify findings are posted as inline PR review comments.

1. Create or identify a PR with at least one file changed
2. Run the review command with `--pr`:
   ```bash
   /cc-review:review --pr <number>
   ```
3. During interactive review, accept at least one finding
4. Verify on GitHub:
   - A single review appears on the PR
   - Inline comments are at the correct file/line locations
   - Each comment has the structured format (what/why/fix + source footer)
   - The review body contains the "What Went Well" section, findings table, and run-id marker

**Expected outcome**: One GitHub review submission with inline comments and summary body.

## Validation Scenario 2: Source Attribution

**Goal**: Verify all finding sources (internal agents + external tools) have correct attribution.

1. Run the review on a PR where CodeRabbit or another external tool also has findings:
   ```bash
   /cc-review:review --pr <number>
   ```
2. Accept findings from different sources
3. Verify on GitHub:
   - Internal agent findings show `_Source: <agent-name> agent_`
   - External tool findings show `_Source: <tool-name>_`
   - Deduped findings show `_Source: <primary> (also flagged by: <others>)_`
   - Summary body lists all participating agents/tools

## Validation Scenario 3: Review Event Type

**Goal**: Verify REQUEST_CHANGES vs COMMENT is set correctly.

1. Run review on a PR with Critical or Important findings, accept at least one:
   - The review should appear as "Changes requested"
2. Run review on a PR with only Minor/Notable findings, accept some:
   - The review should appear as "Commented" (not "Changes requested")

## Validation Scenario 4: Re-run Lifecycle

**Goal**: Verify re-run detects and resolves previous findings.

1. Run the review with `--pr` on a PR, accept findings, post the review
2. Fix one of the reported issues in a new commit
3. Re-run `--pr` on the same PR
4. Verify:
   - The fixed finding's thread is resolved on GitHub
   - New findings (if any) appear as new inline comments
   - Previously posted, still-relevant findings are not duplicated

## Validation Scenario 5: Triage Integration

**Goal**: Verify triage recognizes and manages cc-review threads.

1. After a cc-review review is posted, reply to one inline comment with "fixed"
2. Reply to another with "won't fix, this is intentional"
3. Run triage:
   ```bash
   /cc-review:triage --pr <number>
   ```
4. Verify:
   - The "fixed" thread is resolved (if the code confirms the fix)
   - The "won't fix" thread is resolved with an acknowledgment
   - Threads without replies remain open

## Validation Scenario 6: Reject All (No Post)

**Goal**: Verify that rejecting all findings does not post a review.

1. Run review with `--pr`
2. Reject every finding during interactive review
3. Verify:
   - No new review appears on the PR
   - The local `review-findings.md` is still written
