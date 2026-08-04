# Research: PR Review Comments

## R-001: GitHub Review Submission API

**Decision**: Use `gh api` to call `POST /repos/{owner}/{repo}/pulls/{pull_number}/reviews` with a JSON body containing the review `body`, `event` type, and `comments` array.

**Rationale**: The `gh` CLI is already a dependency of cc-review (used by both review and triage commands). The Reviews API supports posting multiple inline comments in a single request, which satisfies the single-notification requirement. The `event` field supports `REQUEST_CHANGES`, `COMMENT`, and `APPROVE`.

**Alternatives considered**:
- Direct `curl` calls to GitHub REST API: More verbose, requires manual auth token management. `gh api` handles authentication automatically.
- GitHub GraphQL API for review submission: More complex, no significant benefit over REST for this use case. GraphQL is used for thread resolution (`resolveReviewThread`) where REST has no equivalent.

**Key API details**:
- Endpoint: `POST /repos/{owner}/{repo}/pulls/{pull_number}/reviews`
- Body fields: `body` (string), `event` (string), `comments` (array of `{path, line, side, body}`)
- `side` should be `RIGHT` for changes in the new version
- `line` must reference a line within the PR diff hunks; lines outside diff hunks are rejected by the API
- Response includes `id` for the created review

## R-002: GitHub Review Thread Resolution

**Decision**: Use the `resolveReviewThread` GraphQL mutation (already implemented in `platform.sh`) to collapse resolved threads, combined with a brief reply via `post_reply` explaining the resolution reason.

**Rationale**: The `_github_resolve_thread` function in `platform.sh` already implements this mutation. The triage command already uses `post_reply` to respond to threads. Combining both (reply + resolve) provides clear audit trail.

**Alternatives considered**:
- Reply-only without resolving: Leaves threads expanded, cluttering the PR view.
- Resolve-only without reply: No audit trail for why the thread was resolved.

## R-003: Detecting Previous cc-review Runs

**Decision**: Embed a `<!-- cc-review:run-id:UUID -->` HTML comment marker in the review body. On re-run, scan all reviews on the PR for this marker pattern using `gh api` to list reviews.

**Rationale**: HTML comments are invisible in GitHub's rendered view but preserved in the raw body. UUID ensures uniqueness across runs. Scanning reviews is paginated but typically low volume (a PR rarely has more than 10-20 reviews).

**Detection algorithm**:
1. Fetch all reviews: `gh api repos/{owner}/{repo}/pulls/{pr}/reviews --paginate`
2. Filter for reviews where `body` contains `<!-- cc-review:run-id:`
3. Extract the run-id UUID from each matched review
4. For the most recent cc-review review, fetch its inline comments
5. Compare each previous inline comment's `path` and `line` against current findings
6. Match: same file and overlapping line range (within 3 lines tolerance for minor shifts)

## R-004: Inline Comment Line Constraints

**Decision**: Only post inline comments for findings whose `line_start` falls within a diff hunk. Findings on unchanged lines go into the summary body with a note.

**Rationale**: GitHub's review API rejects comments on lines outside the diff. Rather than failing the entire review submission, separate findings into "inlineable" and "summary-only" categories before constructing the API request.

**Implementation approach**:
1. Fetch the PR diff to extract changed line ranges per file: `gh pr diff $PR_NUMBER`
2. Parse diff hunks to build a map: `{file: [{start, end}]}` of changed line ranges
3. For each finding, check if `file` + `line_start` falls within a changed range
4. Partition findings into two lists: `inline_findings` and `summary_only_findings`

## R-005: Prose Plugin Detection

**Decision**: Check for the prose plugin at runtime by looking for the `prose:voice` skill or the prose voice directory. If present, load the `reviewer` voice profile. If absent, use a hardcoded template.

**Rationale**: The prose plugin is optional. The review command should work identically with or without it, differing only in tone/style of comment text.

**Detection approach**:
```bash
PROSE_AVAILABLE=false
if [ -d "$HOME/.claude/plugins/cc-prose" ] || [ -f ".claude/skills/prose-voice/SKILL.md" ]; then
  PROSE_AVAILABLE=true
fi
```

**Fallback template** (when prose is unavailable):
```markdown
**{severity}**: {description}

**Why this matters**: {rationale}

**Suggested fix**: {fix}

_Source: {source_agent}{also_reported_by}_
```

## R-006: "What Went Well" Generation

**Decision**: The goal-alignment agent (Agent 6) already analyzes the diff against declared goals. Extend its prompt to also identify positive patterns when running in PR mode. This avoids adding a 7th agent while leveraging the agent that already has diff context.

**Rationale**: Adding a dedicated 7th agent would increase review time and complexity. The goal-alignment agent already reads the full diff and PR context, making it the natural place to identify positive patterns. When no PR is available (goal-alignment is skipped), the "What Went Well" section is omitted from the summary.

**Alternatives considered**:
- Dedicated 7th agent: Higher cost, separate dispatch, but truly independent perspective.
- Post-processing step reading agent outputs: Would not have access to the diff, only findings. Can't identify positive patterns.

## R-007: Interactive Review UX

**Decision**: Use the harness's interactive choice mechanism for the local review flow. Critical/Important findings are presented one at a time. Minor/Notable are batched.

**Rationale**: cc-review is a prompt-based tool. The interactive review uses the same interaction patterns as the rest of the tool (structured output, choice prompts). No custom TUI needed.

**Interaction flow**:
1. Sort findings: Critical first, then Important, then Minor, then Notable
2. For each Critical/Important finding: present with accept/reject/edit options
3. For Minor findings batch: present list with accept-all/reject-all/cherry-pick
4. For Notable findings batch: same as Minor
5. Collect accepted findings into the submission buffer
