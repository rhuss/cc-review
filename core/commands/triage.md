---
name: triage
description: PR comment triage - classify and handle bot review comments, interactively review human comments
argument-hint: "[--pr <number>] [--spec <path>] [--no-coverage-fix] [--idea-inbox <path>]"
---

# PR Comment Triage

## Prerequisites

```bash
source "$(dirname "$0")/../scripts/resolve-config.sh"
TRIAGE_STATE="$(dirname "$0")/../scripts/triage-state.sh"
SANITIZE_JSON="$(dirname "$0")/../scripts/sanitize-gh-json.py"
```

## Step 1: Resolve PR Context

Determine the PR number from `--pr` flag or current branch:

```bash
BRANCH=$(git branch --show-current)
if [ -z "$PR_NUMBER" ]; then
  PR_NUM=$(gh pr view "$BRANCH" --json number --jq '.number' 2>/dev/null)
else
  PR_NUM="$PR_NUMBER"
fi
```

If no PR found, report "No open PR found for branch `$BRANCH`" and stop.

Extract owner and repo from git remote:
```bash
REMOTE_URL=$(git remote get-url origin 2>/dev/null)
OWNER=$(echo "$REMOTE_URL" | sed -n 's|.*github.com[:/]\([^/]*\)/.*|\1|p')
REPO=$(echo "$REMOTE_URL" | sed -n 's|.*github.com[:/][^/]*/\(.*\)\.git$|\1|p; s|.*github.com[:/][^/]*/\(.*\)$|\1|p')
```

Validate: if `OWNER` or `REPO` is empty, report error and stop.

## Step 2: Initialize State

```bash
"$TRIAGE_STATE" init "$PR_NUM"
```

## Step 3: Fetch Review Threads

Use paginated GraphQL query (100 per page). Pipe ALL API output through `python3 "$SANITIZE_JSON"` before any `jq` call. Run the entire pagination loop in a single Bash call.

```bash
ALL_THREADS="[]"
CURSOR=""
PAGE=1

while true; do
  CURSOR_ARG=""
  [ -n "$CURSOR" ] && CURSOR_ARG="-f cursor=$CURSOR"

  PAGE_JSON=$(gh api graphql -f query='
    query($owner: String!, $repo: String!, $number: Int!, $cursor: String) {
      repository(owner: $owner, name: $repo) {
        pullRequest(number: $number) {
          reviewThreads(first: 100, after: $cursor) {
            totalCount
            pageInfo { hasNextPage endCursor }
            nodes {
              id isResolved path line
              comments(first: 50) {
                nodes {
                  id databaseId
                  author { login ... on Bot { id } }
                  body createdAt
                }
              }
            }
          }
        }
      }
    }
  ' -f owner="$OWNER" -f repo="$REPO" -F number="$PR_NUM" $CURSOR_ARG \
    | python3 "$SANITIZE_JSON")

  PAGE_THREADS=$(printf '%s' "$PAGE_JSON" | jq '.data.repository.pullRequest.reviewThreads.nodes')
  ALL_THREADS=$(printf '%s\n%s' "$ALL_THREADS" "$PAGE_THREADS" | jq -s '.[0] + .[1]')

  HAS_NEXT=$(printf '%s' "$PAGE_JSON" | jq -r '.data.repository.pullRequest.reviewThreads.pageInfo.hasNextPage')
  [ "$HAS_NEXT" != "true" ] && break

  CURSOR=$(printf '%s' "$PAGE_JSON" | jq -r '.data.repository.pullRequest.reviewThreads.pageInfo.endCursor')
  PAGE=$((PAGE + 1))
done

TOTAL_COUNT=$(printf '%s' "$PAGE_JSON" | jq -r '.data.repository.pullRequest.reviewThreads.totalCount')
FETCHED_COUNT=$(printf '%s' "$ALL_THREADS" | jq 'length')
```

Verify: if `FETCHED_COUNT < TOTAL_COUNT`, stop with mismatch error.

### Step 3c: CodeRabbit Rate Limit Detection

Check issue comments for "Review limit reached" from `coderabbitai[bot]`. If rate-limited and `coderabbit` CLI is available, run `coderabbit review` as local fallback, then re-fetch threads once.

### Step 3d: Fetch Issue Comments and Status Bots

```bash
ISSUE_COMMENTS=$(gh api "repos/$OWNER/$REPO/issues/$PR_NUM/comments" 2>/dev/null || echo "[]")
```

Detect status bots (Codecov, Coveralls, Dependabot, Renovate, etc.). For Codecov, deep-parse per-file patch coverage table from the comment body. Check patch coverage against threshold from config:

```bash
PATCH_THRESHOLD=$(resolve_config "triage.codecov.patch_threshold" "80")
```

## Step 4: Partition Threads

For each unresolved thread:
1. Skip if `isResolved` is true
2. Check state by `databaseId`: `"$TRIAGE_STATE" get "$PR_NUM" "$COMMENT_DB_ID"`
3. Determine author type: GraphQL `Bot` type takes priority, `[bot]` suffix as fallback

Split into bot threads and human threads.

## Step 5: Bot Profile Matching

Hardcoded profiles:

| Bot | selfResolves | autoResolve |
|-----|-------------|-------------|
| `coderabbitai[bot]` | true | false |
| `copilot[bot]` | false | true |
| `devin-ai-integration[bot]` | false | true |

Config overrides from `.cc-review/config.yml` via `resolve_config "triage.bot_profiles"`.

### Step 5b: Bot Discovery Log

```
Found bot threads:
- copilot[bot]: N threads
- coderabbitai[bot]: N threads
Total: N bot threads to process
```

Every listed bot thread MUST be individually assessed.

## Step 6: Assess and Apply Bot Fixes

For each unresolved bot thread:

### 6a: Read Context
Read the comment body, the referenced file at relevant lines, and Codecov data for the file if available.

### 6b: Assess Validity
Code correctness is the primary concern. Verify the bot's specific claim against actual code.
- **Valid**: Real issue identified, fix can be applied
- **Invalid**: Code is correct, rejection MUST cite specific evidence
- **Deferred**: Merit but out of scope for this PR

### 6c: Apply, Skip, or Defer
- Valid: Apply fix with Edit tool, track for commit
- Invalid: Prepare rejection reply with evidence
- Deferred: Prepare deferral reply

### 6d-6f: Edge Cases
Check for conflicting fixes on same file/lines, deleted files, summary comments (no file/line).

## Step 7: Batch Commit and Push

If fixes were applied:
```bash
git add -u
git commit -m "fix: apply bot review suggestions (#$PR_NUM)

Assisted-By: 🤖 Claude Code"
git push
```

### Step 7b: Check CI After Push
Poll CI up to 3 times (30s apart). If failing, attempt 1 fix scoped to triage-changed files.

### Step 7c: Re-fetch Comment IDs
For bots with `selfResolves=false`, re-fetch threads and match by path+line+author to get updated IDs.

## Step 8: Post Replies

For each processed comment, post via REST API:

```bash
gh api "repos/$OWNER/$REPO/pulls/$PR_NUM/comments/$COMMENT_DB_ID/replies" \
  -f body="$REPLY_BODY"
```

Reply formats:
- **Accepted**: Assessment + "Applied in <SHA>." + `<!-- spex-triage -->`
- **Rejected**: Evidence-based justification + `<!-- spex-triage -->`
- **Deferred**: "Valid point, out of scope" + `<!-- spex-triage:deferred -->`
- **Fix failure**: "Could not apply automatically" + `<!-- spex-triage -->`

Update state after each reply: `"$TRIAGE_STATE" set "$PR_NUM" "$DB_ID" "<action>" "$REPLY_ID"`

## Step 9: Resolve Threads

| Verdict | selfResolves=true | selfResolves=false |
|---------|-------------------|--------------------|
| Rejected | Resolve | Resolve |
| Deferred | Resolve | Resolve |
| Accepted | Leave open | Resolve |

Resolve via GraphQL `resolveReviewThread` mutation. Never resolve without a posted reply.

## Step 10: Re-evaluation

For already-handled comments: check if new thread comments appeared after `handledAt`. If yes, re-process.

## Step 11: Spec-Aware Assessment

When `--spec` is provided, read the spec and use it as additional context in Step 6b. Reference specific requirement IDs in rejection replies.

## Step 12: Human Comment Review

For each unresolved human thread:
1. Present the comment with file/line context
2. Provide validity assessment (Agree/Disagree/Partial)
3. Draft a reply
4. Present options: Approve / Edit / Skip
5. Update state after posting

### Step 12b: Coverage Cross-Reference

Cross-reference Codecov per-file data with bot findings by file path. Format coverage table for summary.

### Step 12c: Coverage Remediation

When Codecov CI is failing or patch coverage below threshold:
1. Identify files needing coverage
2. Write tests for uncovered code paths
3. Validate tests pass
4. Commit and push

Skip if `--no-coverage-fix` is passed or `auto_remediate` is false in config.

## Step 13: Summary

```
## Triage Summary for PR #<N>

**Bot comments** (by author):
| Bot | Accepted | Rejected | Deferred | Skipped | Already Handled |
|-----|----------|----------|----------|---------|-----------------|

**Bot totals**: Accepted N, Rejected N, Deferred N, Skipped N, Already handled N

**Human comments**: Approved N, Edited N, Skipped N, Pending N

**Coverage** (from Codecov, if detected):
| File | Patch % | Missing | Overlaps with bot findings |
|------|---------|---------|---------------------------|

**Commit**: <SHA>
**CI status**: passing|failing|pending|not checked
**Open bot comments remaining**: N
```

### Idea Inbox Capture

When `--idea-inbox <path>` is provided and deferred/rejected count > 0:
1. Group deferred + rejected items by theme (2+ findings per theme)
2. Present qualifying themes with multi-select
3. Write selected themes to the idea inbox file
