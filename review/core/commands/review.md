---
name: review
description: Multi-agent code review with autonomous fix loop. Dispatches 6 specialized review agents, merges findings, auto-fixes Critical/Important issues.
argument-hint: "[--pr <number>] [--spec <path>] [--hints <path>] [--output <path>] [--config <path>] [--profile <name>] [--no-fix] [--max-rounds <n>] [--no-external] [--no-coderabbit] [--no-copilot] [--no-codex] [--sequential]"
---

# Code Review

## Prerequisites

### Config Resolution

```bash
source "$(dirname "$0")/../scripts/resolve-config.sh"
```

Initialize the merged config from all layers. `--config` and `--profile` are parsed from command arguments:

```bash
if ! resolve_config_init ${CONFIG_FLAG:+--config "$CONFIG_FLAG"} ${PROFILE_FLAG:+--profile "$PROFILE_FLAG"}; then
  exit 1
fi
```

Apply CLI flag overrides on top of the merged config:

```bash
CLI_OVERRIDES=()
[ "$NO_CODERABBIT" = "true" ] && CLI_OVERRIDES+=("external_tools.coderabbit=false")
[ "$NO_COPILOT" = "true" ] && CLI_OVERRIDES+=("external_tools.copilot=false")
[ "$NO_CODEX" = "true" ] && CLI_OVERRIDES+=("external_tools.codex=false")
[ "$NO_EXTERNAL" = "true" ] && CLI_OVERRIDES+=("external_tools.coderabbit=false" "external_tools.copilot=false" "external_tools.codex=false")
[ "$USE_EXTERNAL" = "true" ] && CLI_OVERRIDES+=("external_tools.coderabbit=true" "external_tools.copilot=true" "external_tools.codex=true")
[ -n "$MAX_ROUNDS_FLAG" ] && CLI_OVERRIDES+=("max_fix_rounds=$MAX_ROUNDS_FLAG")
[ ${#CLI_OVERRIDES[@]} -gt 0 ] && resolve_config_apply_cli_overrides "${CLI_OVERRIDES[@]}"
```

Validate config types after merge and overrides:

```bash
resolve_config_validate_types
```

### Review Hints

```bash
REVIEW_HINTS_FILE=".cc-review/review-hints.md"
if [ -n "$HINTS_FLAG" ]; then
  REVIEW_HINTS_FILE="$HINTS_FLAG"
fi
REVIEW_HINTS=""
if [ -f "$REVIEW_HINTS_FILE" ] && [ -s "$REVIEW_HINTS_FILE" ]; then
  REVIEW_HINTS=$(cat "$REVIEW_HINTS_FILE")
fi
```

### External Tool Settings

Read config defaults, then apply CLI flag overrides:

```bash
CODERABBIT=$(resolve_config "external_tools.coderabbit" "true")
COPILOT=$(resolve_config "external_tools.copilot" "false")
CODEX=$(resolve_config "external_tools.codex" "true")
```

CLI overrides (applied only if explicitly passed):
- `--external` sets all to true
- `--no-external` sets all to false
- `--no-coderabbit` / `--no-copilot` / `--no-codex` disable individual tools

### Output Settings

```bash
OUTPUT_DIR=$(resolve_config "output.dir" ".")
FINDINGS_FILENAME=$(resolve_config "output.findings_filename" "review-findings.md")
VERBOSITY=$(resolve_config "output.verbosity" "normal")
OUTPUT_PATH="${OUTPUT_FLAG:-$OUTPUT_DIR/$FINDINGS_FILENAME}"
```

Verbosity controls agent progress reporting:
- `quiet`: Only final summary and errors
- `normal`: Agent completion status and finding counts
- `verbose`: Agent progress, timing, intermediate results, and debug info

## Step 1: Determine Changed Files

```bash
MAIN_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@' || echo "main")
```

### Auto-Detect PR

When no `--pr` flag is provided, check config for auto-detection:

```bash
AUTO_DETECT_PR=$(resolve_config "pr_posting.auto_detect_pr" "false")
if [ -z "$PR_NUMBER" ] && [ "$AUTO_DETECT_PR" = "true" ]; then
  CURRENT_BRANCH=$(git branch --show-current)
  PR_NUMBER=$(gh pr view "$CURRENT_BRANCH" --json number --jq '.number' 2>/dev/null || echo "")
fi
```

When `--pr <number>` is provided, use the PR's diff against its base branch:
```bash
gh pr diff "$PR_NUMBER" --name-only 2>/dev/null
```

Otherwise use the branch diff:
```bash
git diff --name-only "${MAIN_BRANCH}...HEAD" 2>/dev/null
git diff --name-only HEAD 2>/dev/null
git diff --name-only --cached 2>/dev/null
```

Combine into a deduplicated list. Filter to source code files (exclude binary, images, lock files). Exclude files under `specs/` and `brainstorm/`.

For re-review rounds (fix loop): narrow scope to only files modified by the most recent fix round.

## Step 2: Detect External Tools

Check for external review CLIs, respecting config settings:

```bash
# CodeRabbit (enabled by default)
[ "$CODERABBIT" = "true" ] && command -v coderabbit >/dev/null 2>&1 && CODERABBIT_AVAILABLE=true

# Copilot CLI
[ "$COPILOT" = "true" ] && command -v copilot >/dev/null 2>&1 && COPILOT_AVAILABLE=true

# Codex CLI
[ "$CODEX" = "true" ] && command -v codex >/dev/null 2>&1 && CODEX_AVAILABLE=true
```

### Test Command Auto-Detection

```bash
TEST_CMD=$(resolve_config "test.command" "")
TEST_TIMEOUT=$(resolve_config "test.timeout_seconds" "300")

[ -z "$TEST_CMD" ] && grep -q '^test:' Makefile 2>/dev/null && TEST_CMD="make test"
[ -z "$TEST_CMD" ] && [ -f go.mod ] && TEST_CMD="go test ./..."
[ -z "$TEST_CMD" ] && [ -f package.json ] && jq -e '.scripts.test' package.json >/dev/null 2>&1 && TEST_CMD="npm test"
[ -z "$TEST_CMD" ] && ([ -f pyproject.toml ] || [ -f setup.py ]) && TEST_CMD="pytest"
```

### PR Metadata and Goal Extraction (for Goal Alignment agent)

```bash
GOALS_AVAILABLE=false

if [ -n "$PR_NUMBER" ]; then
  PR_BODY=$(gh pr view "$PR_NUMBER" --json body -q '.body' 2>/dev/null || echo "")
else
  PR_BODY=$(gh pr view --json body -q '.body' 2>/dev/null || echo "")
fi

if [ -n "$PR_BODY" ]; then
  GOALS_AVAILABLE=true
  PR_ISSUES=$(echo "$PR_BODY" | grep -oE '(Fixes|Closes|Resolves)\s+#[0-9]+' | grep -oE '[0-9]+' || echo "")
fi
```

For each linked issue, fetch title and body. Build a `DECLARED_GOALS` block from:
1. Spec requirements (if `--spec` provided): extract FR-NNN items from spec.md
2. PR description: extract goals from PR body text
3. Linked issues: issue titles and key points

If no PR is found: log "Goal alignment: skipped (no PR found)" and skip Agent 6.

## Step 3: Dispatch Review Agents and External Tools

**Critical: use subagents, not inline execution.** Each internal review agent MUST be dispatched as a separate subagent using the Agent tool (or equivalent in the executing harness). This ensures:
1. Each agent runs with a **fresh context**, not polluted by other agents' findings or the orchestrator's state.
2. Agents run **in parallel** by default (dispatch all Agent tool calls in a single response). Only use sequential dispatch if `--sequential` is explicitly passed.
3. The orchestrator's context stays small, containing only the merged findings, not the full file contents each agent read.

Each subagent prompt must include:
- The Common Preamble from `core/agents/preamble.md`
- Its specific prompt from `core/agents/<name>.md`
- The list of changed files (paths only; the subagent reads file contents itself)
- The spec text (if `--spec` provided)
- Review hints (if detected)
- For Agent 6 only: the DECLARED_GOALS block
- Instruction to call `ReportFindings` with its results (this is how findings are returned to the orchestrator)

The subagent's final text output is its summary. The structured findings come back via the `ReportFindings` tool call. The orchestrator collects findings from all completed agents before proceeding to Step 4.

If `REVIEW_HINTS` is non-empty, include item 11 in the preamble with the contents of the review hints file between the delimiters. If empty, omit item 11.

### Agent Selection

Read agent toggles from config. Disabled agents are skipped entirely:

```bash
AGENT_CORRECTNESS=$(resolve_config "agents.correctness" "true")
AGENT_ARCHITECTURE=$(resolve_config "agents.architecture" "true")
AGENT_SECURITY=$(resolve_config "agents.security" "true")
AGENT_PRODUCTION=$(resolve_config "agents.production" "true")
AGENT_TEST_QUALITY=$(resolve_config "agents.test_quality" "true")
AGENT_GOAL_ALIGNMENT=$(resolve_config "agents.goal_alignment" "true")
```

### Dispatch

Build the list of enabled agents, then dispatch ALL of them in a **single response** (one Agent tool call per agent). Do NOT dispatch one, wait for it, then dispatch the next. Do NOT merge agents or invent ad-hoc scope splits. Each agent below is a separate Agent tool call with its own fresh context.

**Internal agents** (each one = one Agent tool call):
1. Correctness (`core/agents/correctness.md`) - skip if `AGENT_CORRECTNESS` is "false"
2. Architecture & Idioms (`core/agents/architecture.md`) - skip if `AGENT_ARCHITECTURE` is "false"
3. Security (`core/agents/security.md`) - skip if `AGENT_SECURITY` is "false"
4. Production Readiness (`core/agents/production.md`) - skip if `AGENT_PRODUCTION` is "false"
5. Test Quality (`core/agents/test-quality.md`) - skip if `AGENT_TEST_QUALITY` is "false"
6. Goal Alignment (`core/agents/goal-alignment.md`) - skip if `AGENT_GOAL_ALIGNMENT` is "false" OR `GOALS_AVAILABLE` is false

**External tools** (dispatch as subagents or inline Bash, depending on the tool):
7. CodeRabbit (external) - skip if not `CODERABBIT_AVAILABLE`
8. Copilot CLI (external) - skip if not `COPILOT_AVAILABLE`
9. Codex CLI (external) - skip if not `CODEX_AVAILABLE`

### Prompt Construction

Before dispatching, read the preamble and each agent's prompt file. Then construct each subagent prompt by concatenating them.

For each enabled internal agent, read these files:
```bash
PREAMBLE=$(cat core/agents/preamble.md)
AGENT_PROMPT=$(cat core/agents/<name>.md)   # e.g., correctness.md, security.md
```

Then dispatch one Agent tool call per agent. The prompt for each subagent is:

```
{PREAMBLE}

{AGENT_PROMPT}

## Review Target

You are reviewing a PR/diff with the following changed files:
{LIST_OF_CHANGED_FILES}

For each file, read the file contents yourself using the Read tool. Focus on the changed regions but read enough surrounding context to understand the code.

{IF SPEC: "## Spec\n" + SPEC_TEXT}
{IF REVIEW_HINTS: "## Review Hints\n" + HINTS_TEXT}
{IF GOAL ALIGNMENT AGENT: "## Declared Goals\n" + DECLARED_GOALS}

## Output

Report your findings using the ReportFindings tool. Each finding must include:
- file: relative path
- line: line number
- summary: one-sentence description
- failure_scenario: concrete inputs/state that trigger the issue
- category: your agent category (e.g., "correctness", "security")
- short_summary: under 60 chars

If you find zero issues, call ReportFindings with an empty findings array.
```

**Hard rule**: You MUST dispatch exactly the agents listed above (minus disabled ones). Do NOT substitute Explore agents, fork agents, or any other agent type. Do NOT combine multiple agent roles into one agent. Do NOT split one agent's role across multiple agents. The agent prompts in `core/agents/` define the scope for each agent.

If `--sequential` is passed, dispatch agents one at a time, waiting for each to complete before starting the next. This is slower but useful for debugging.

Report progress as agents complete:
```
Agent 1/N: Correctness... done, N findings
Agent 2/N: Architecture & Idioms... done, N findings
...
Agent 7/N: CodeRabbit (external)... done, N findings
```

Wait for ALL dispatched agents to complete before proceeding to Step 4.

### External Tool Invocations

**CodeRabbit** (if `CODERABBIT_AVAILABLE`):
```bash
coderabbit review --agent --base "${MAIN_BRANCH}" --committed 2>&1
```

Parse output: split on `=============` delimiters, extract file/line/severity/description/rationale. Map severity (critical->Critical, major->Important, minor->Minor). Set category="external", source_agent="coderabbit", confidence=75.

**Copilot CLI** (if `COPILOT_AVAILABLE`):
```bash
copilot -s -p "Review the following git diff for bugs, security issues, and code quality problems..." 2>&1
```

Parse output: split on "### FINDING" markers. Discard findings for files under `specs/`. Set category="external", source_agent="copilot", confidence=75.

**Codex CLI** (if `CODEX_AVAILABLE`):
```bash
codex review --base "${MAIN_BRANCH}" 2>&1
```

Parse output: extract file/line/severity/description/rationale. Set category="external", source_agent="codex", confidence=75.

**Error handling**: If a tool times out, crashes, or errors, log the failure and continue. External tool failures do not block the review.

### Severity Filtering

Read severity settings from config and filter findings:

```bash
MIN_CONFIDENCE=$(resolve_config "severity.min_confidence" "70")
REQUEST_CHANGES_SEVERITIES=$(resolve_config "severity.request_changes_severities" "Critical,Important")
AUTO_FIX=$(resolve_config "severity.auto_fix" "true")
```

After each agent completes, filter findings where `confidence < MIN_CONFIDENCE`. These filtered findings are excluded from the report entirely.

## Step 4: Merge and Deduplicate Findings

1. Collect all findings from internal agents and external tools
2. Normalize to the Finding schema (see `core/schemas/finding.schema.json`)
3. Sort by file path, then line number
4. Deduplicate: for findings with same file, overlapping line range, and same category, keep the one with the longer description. Add the other's source_agent to `also_reported_by`. Use higher severity and confidence.
5. Exception: `goal-alignment` findings do NOT dedup against other categories
6. Assign sequential IDs (FINDING-1, FINDING-2, ...)

## Step 5: Gate Check

Use `REQUEST_CHANGES_SEVERITIES` from config to determine which severities trigger a gate failure:

- Count findings whose severity is in `REQUEST_CHANGES_SEVERITIES` (default: Critical, Important)
- If count = 0: **GATE PASS**
- If count > 0: proceed to fix loop (or fail if `--no-fix`, `AUTO_FIX` is "false", or max rounds reached)
- Notable findings are excluded from the gate check

### Step 5b: Action Selection (PR mode)

When `PR_NUMBER` is set (explicitly via `--pr` or auto-detected) AND gate-failing findings exist, present the user with a choice before proceeding:

> **Found N Critical/Important findings. How would you like to handle them?**
>
> 1. **Fix locally** - apply fixes in the working tree (default)
> 2. **Comment on PR** - post findings as review comments on the PR, skip local fixes
> 3. **Both** - fix locally first, then post remaining unresolved findings as PR comments

Map the selection:
- **Fix locally**: set `ACTION="fix"`. Run Step 6 (fix loop). Skip Step 7.5 (PR posting).
- **Comment on PR**: set `ACTION="comment"`. Skip Step 6. Run Step 7.5.
- **Both**: set `ACTION="both"`. Run Step 6, then run Step 7.5 for any findings that remain after the fix loop.

When `--no-fix` is passed, skip this prompt and default to `ACTION="comment"` (PR posting only).

When no `PR_NUMBER` is set, skip this prompt entirely and default to `ACTION="fix"` (local fix loop only, no PR posting possible).

When gate check passes (zero Critical/Important findings), skip this prompt. Step 7.5 still runs if `PR_NUMBER` is set (to post Minor/Notable observations).

## Step 6: Autonomous Fix Loop

```bash
MAX_FIX_ROUNDS=$(resolve_config "max_fix_rounds" "3")
```

Maximum rounds from config (default 3). Skip if `--no-fix` is passed, `AUTO_FIX` is "false", or `ACTION="comment"`.

For each round:
1. Collect all Critical and Important findings, sorted by file
2. For each file, sort findings by line number descending (prevent line shifts)
3. Apply each fix suggestion
4. Stage changes
5. Run test suite (if detected):
   - If tests pass: proceed
   - If tests fail: convert failures to Critical findings with category="regression"
6. Re-dispatch review agents on modified files only
7. Merge new findings with existing Minor findings
8. Gate check: if Critical + Important = 0, GATE PASS and exit loop

### Step 6b: Post-Fix Spec Compliance Check

After fix loop completes, if code was removed AND `--spec` was provided:
1. Read spec functional requirements
2. Verify each FR is still implemented
3. Add Critical findings for dropped requirements
4. Re-run fix loop if rounds remain

## Step 7: Write Findings Report

Write `review-findings.md` at the output path:

```markdown
# Review Findings

**Date:** YYYY-MM-DD
**Branch:** branch-name
**Rounds:** N
**Gate Outcome:** PASS|FAIL
**Invocation:** standalone|speckit|manual

## Summary

| Severity | Found | Fixed | Remaining |
|----------|-------|-------|-----------|
| Critical | N | N | N |
| Important | N | N | N |
| Minor | N | - | N |
| Notable | N | - | N |
| **Total** | **N** | **N** | **N** |

**Agents completed:** N/6 (+ N external tools)
**Agents failed:** [list if any]

## Findings

### FINDING-N
- **Severity:** Critical|Important|Minor|Notable
- **Confidence:** 0-100
- **File:** path/to/file:start-end
- **Category:** <category>
- **Source:** <agent-name> (also reported by: <others>)
- **Round found:** N
- **Resolution:** fixed (round N)|pending|unresolved (after N rounds)|informational (Notable)

**What is wrong:**
[Description]

**Why this matters:**
[Rationale]

**How it was resolved:**
[Resolution or what needs to happen]

## Notable Observations
[Simplified format for Notable findings, if any]

## Goal Alignment
[Goal delivery table + undeclared changes, if goal agent ran]

## Test Suite Results
[Per-round test results, if tests ran]

## Remaining Findings
[Unresolved Critical/Important findings, if gate failed]
```

## Step 7.5: PR Review Posting

This step runs when `PR_NUMBER` is set AND `ACTION` is `"comment"` or `"both"`. Skip this entire step if no `PR_NUMBER` is set or `ACTION="fix"`.

### 7.5a: Extract PR Context

```bash
REMOTE_URL=$(git remote get-url origin 2>/dev/null)
OWNER=$(echo "$REMOTE_URL" | sed -n 's|.*github.com[:/]\([^/]*\)/.*|\1|p')
REPO=$(echo "$REMOTE_URL" | sed -n 's|.*github.com[:/][^/]*/\(.*\)\.git$|\1|p; s|.*github.com[:/][^/]*/\(.*\)$|\1|p')
```

**Validate extracted values**: If `OWNER` or `REPO` is empty, report "Could not extract owner/repo from origin URL. Ensure the remote points to a GitHub repository." and skip PR posting. The local findings report is still written in Step 7.

Source platform functions:

```bash
source "$(dirname "$0")/../scripts/platform.sh"
```

Generate a unique run ID:

```bash
RUN_ID=$(uuidgen 2>/dev/null || cat /proc/sys/kernel/random/uuid 2>/dev/null || python3 -c "import uuid; print(uuid.uuid4())")
```

### 7.5b: Build Diff Hunk Map

Call the platform function to get the file/line map of changed lines in the PR:

```bash
DIFF_HUNKS=$(parse_diff_hunks "$PR_NUMBER")
```

### 7.5c: Partition Findings

Partition all deduplicated findings into two lists based on whether they fall within diff hunks:

- **inline_findings**: Finding's `file` exists in `DIFF_HUNKS` AND `line_start` falls within one of that file's `{start, end}` ranges
- **summary_only_findings**: Finding's file is not in the diff, or `line_start` is outside all hunk ranges for that file, or the file no longer exists

For each finding, check the file status before partitioning:

1. **File deleted**: If the finding's `file` does not exist in the PR's head commit (check against the changed files list from Step 1 and `git ls-files`), move to `summary_only_findings` with note: "File no longer exists in this PR."
2. **File exists but outside diff**: If the finding's `file` exists but `line_start` is outside all hunk ranges, move to `summary_only_findings` with note: "Location is outside the PR diff (line {line_start})."
3. **File and line within diff**: Add to `inline_findings`.

### 7.5d: Detect Previous cc-review Runs

Scan existing reviews on the PR for previous cc-review runs:

```bash
EXISTING_REVIEWS=$(fetch_reviews "$OWNER" "$REPO" "$PR_NUMBER")
```

Filter reviews whose `body` contains `<!-- cc-review:run-id:`. For each match, extract the run-id UUID and the review ID. Identify the most recent cc-review review.

If a previous run is found, fetch its inline comments and build a list of `{path, line, body}` records for matching against current findings.

### 7.5e: Match Against Previous Findings

For each previous inline comment, check if a current finding matches by:
1. Same `file` (path)
2. Overlapping line range (within 3-line tolerance): `abs(previous.line - current.line_start) <= 3`
3. Same `category`

Matched findings are considered "already posted" and excluded from the new submission. Unmatched previous threads where no current finding overlaps are candidates for resolution (the issue was fixed).

### 7.5f: Resolve Fixed Threads

For each previous thread that has no matching current finding (the code fix addressed it):

1. Post a brief reply explaining the resolution:
   ```
   Resolved: this issue appears to be addressed in the current code.
   <!-- cc-review-triage -->
   ```
2. Resolve the thread via GraphQL:
   ```bash
   resolve_thread "$THREAD_NODE_ID"
   ```

### 7.5g: Interactive Local Review

Present all NEW findings (not matched against previous runs) for interactive review before posting.

**Critical and Important findings** (one at a time):

For each finding with severity Critical or Important, present:
- The finding details (file, line, severity, description, rationale, fix suggestion, source)
- Three options:
  - **Accept**: Mark the finding for posting
  - **Reject**: Exclude the finding from posting
  - **Edit**: Open text-only editing of the finding's description and mitigation text. Severity, file, and line are structural properties and are NOT editable during interactive review. The edit flow:
    1. Present the current `description` text and ask for the reviewer's replacement text
    2. Present the current `fix` (mitigation) text and ask for the reviewer's replacement text
    3. Store both edited values in the finding's transient `edited_text` field as a combined string: the edited description followed by the edited mitigation
    4. After editing, return to the accept/reject prompt for this finding (the reviewer must still explicitly accept or reject the edited finding)

**Minor and Notable findings** (batched by severity):

Present all Minor findings as a batch with:
- A summary list showing each finding's file, line, and description
- Options:
  - **Accept all**: Mark all Minor findings for posting
  - **Reject all**: Exclude all Minor findings
  - **Cherry-pick**: Present each finding individually with accept/reject

Repeat the same batch presentation for Notable findings.

Track the `accepted` (boolean) transient field on each finding.

### 7.5h: Reject-All Guard

If no findings were accepted (all rejected), skip PR posting entirely. Log: "All findings rejected. No GitHub review posted." The local findings report (`review-findings.md`) is still written in Step 7.

### 7.5i: Format Comment Bodies

For each accepted finding, format the inline comment body.

**Prose plugin detection**:

```bash
PROSE_AVAILABLE=false
if [ -d "$HOME/.claude/plugins/cc-prose" ] || [ -f ".claude/skills/prose-voice/SKILL.md" ]; then
  PROSE_AVAILABLE=true
fi
```

**If prose plugin is available**: Load the reviewer voice profile from `core/templates/reviewer-voice.md` and use it to shape the comment text with all three structural elements (what, why, fix).

**If prose plugin is not available**: Use the fallback template from `core/templates/reviewer-voice.md`:

```
**{severity}**: {description}

**Why this matters**: {rationale}

**Suggested fix**: {fix}

_Source: {source_agent}{also_reported_by}_
```

If the finding has `edited_text`, use that instead of the original `description` for the "what is wrong" element.

**Source footer**: Append to every comment:
- Single source: `_Source: {source_agent} agent_`
- With co-reporters: `_Source: {source_agent} (also flagged by: {also_reported_by joined by ", "})_`
- External tool (no "agent" suffix): `_Source: {source_agent}_`

### 7.5j: Generate "What Went Well" Section

When running in PR mode, the goal-alignment agent (Agent 6) produces a "What Went Well" section identifying positive patterns in the PR (solid error handling, clean abstractions, good test coverage).

If Agent 6 ran and produced positive observations, include them in the summary body before the findings table. If Agent 6 was skipped (no goals available), omit this section.

### 7.5k: Assemble Review Submission

Build the JSON payload for the GitHub review submission API:

**Event type**:
- `REQUEST_CHANGES` if any accepted finding has severity Critical or Important
- `COMMENT` otherwise

**Summary body** (the review `body` field):

```markdown
## cc-review Summary

### What Went Well
{positive observations from goal-alignment agent, if available}

### Findings

| Severity | File | Description | Source |
|----------|------|-------------|--------|
| {severity} | {file}:{line_start} | {description (truncated to 100 chars)} | {source_agent} |
...

{summary_only_findings with notes about why they are not inline}

### Review Details

- **Findings posted**: {accepted_count}
- **Findings reviewed and not posted**: {rejected_count}
- **Gate outcome**: {PASS or FAIL}
- **Participating agents**: {comma-separated list of all agents and tools that produced findings}

<!-- cc-review:run-id:{RUN_ID} -->
```

**Comments array**: For each accepted inline finding, place the comment at the **end** of the relevant line range so the reader sees the code context before the comment. Use `start_line` + `line` for multi-line findings; for single-line findings, use `line` only.

Multi-line finding (when `line_end` > `line_start` and both are within the diff hunk):
```json
{
  "path": "{file}",
  "start_line": {line_start},
  "line": {line_end},
  "side": "RIGHT",
  "start_side": "RIGHT",
  "body": "{formatted comment body from 7.5i}"
}
```

Single-line finding (when `line_end` is absent or equals `line_start`):
```json
{
  "path": "{file}",
  "line": {line_start},
  "side": "RIGHT",
  "body": "{formatted comment body from 7.5i}"
}
```

**Hunk boundary check**: If `line_end` falls outside the diff hunk range but `line_start` is within it, fall back to the single-line format using `line_start` only. Do not use a `start_line`/`line` range that extends beyond the diff hunk, as the GitHub API will reject it.

Write the complete payload to a temp file:

```bash
PAYLOAD_FILE=$(mktemp)
jq -n \
  --arg body "$SUMMARY_BODY" \
  --arg event "$EVENT_TYPE" \
  --argjson comments "$COMMENTS_JSON" \
  '{body: $body, event: $event, comments: $comments}' > "$PAYLOAD_FILE"
```

### 7.5k2: Truncation Guard

Before posting, check if the number of accepted inline findings exceeds the configured limit:

```bash
MAX_COMMENTS=$(resolve_config "pr_posting.max_inline_comments" "50")
```

If the inline comment count exceeds `MAX_COMMENTS`:

1. Sort accepted inline findings by severity (Critical first, then Important, Minor, Notable)
2. Keep the first `MAX_COMMENTS` findings as inline comments
3. Move the remaining findings to `summary_only_findings` with note: "Truncated: exceeded maximum inline comment limit ({MAX_COMMENTS})"
4. Log a warning:
   ```
   WARNING: {total} inline findings exceed limit of {MAX_COMMENTS}. {truncated_count} findings moved to summary body only.
   Omitted findings: {list of truncated finding IDs}
   ```
5. Rebuild the summary body to include the truncated findings

### 7.5l: Post Review

Call the platform function to post the review:

```bash
REVIEW_RESPONSE=$(post_review "$OWNER" "$REPO" "$PR_NUMBER" "$PAYLOAD_FILE")
```

On success: extract the review URL and log it.

On failure: proceed to error recovery (Step 7.5m).

Clean up the temp file:

```bash
rm -f "$PAYLOAD_FILE"
```

### 7.5m: Error Recovery

If the review posting fails, detect the failure type and respond accordingly:

**Detect `gh` authentication failure**:

```bash
if echo "$REVIEW_RESPONSE" | grep -qi "authentication\|401\|403\|login\|credential"; then
  AUTH_FAILURE=true
fi
```

**Write recovery file** (for all failure types):

```bash
RECOVERY_DIR=$(resolve_config "pr_posting.recovery_dir" ".cc-review")
mkdir -p "$RECOVERY_DIR"
RECOVERY_FILE="${RECOVERY_DIR}/recovery-${RUN_ID}.json"
cp "$PAYLOAD_FILE" "$RECOVERY_FILE"
```

The recovery file contains the full payload JSON (body, event, comments array) so the user can retry without re-running the full review.

**Report the failure**:

If authentication failure:
```
ERROR: GitHub authentication failed. Run `gh auth login` to re-authenticate.
Accepted findings saved to: {RECOVERY_FILE}
To retry after authenticating: re-run with --pr {PR_NUMBER}
```

If other failure (network, API error, rate limit):
```
ERROR: Failed to post GitHub review.
Response: {first 200 chars of REVIEW_RESPONSE}
Accepted findings saved to: {RECOVERY_FILE}
To retry: re-run with --pr {PR_NUMBER}
```

The local findings report (`review-findings.md`) is unaffected by posting failures since it was written in Step 7 before the posting attempt.

## Step 8: Console Summary

```
Review completed.

Gate: PASS|FAIL (after fix round N)

Review Agents:

| Agent                   | Found | Fixed | Remaining | Status    |
|-------------------------|-------|-------|-----------|-----------|
| Correctness             |     N |     N |         N | completed |
| Architecture & Idioms   |     N |     N |         N | completed |
| Security                |     N |     N |         N | completed |
| Production Readiness    |     N |     N |         N | completed |
| Test Quality            |     N |     N |         N | completed |
| Goal Alignment          |     N |     N |         N | completed/skipped |
| CodeRabbit (external)   |     N |     N |         N | completed/skipped/failed |
| Copilot (external)      |     N |     N |         N | completed/skipped/failed |
| Codex (external)        |     N |     N |         N | completed/skipped/failed |
| Test Suite (regression) |     N |     N |         N | passed/failed/skipped |
|-------------------------|-------|-------|-----------|-----------|
| Total                   |     N |     N |         N |           |

MVP: <agent name> (<N> findings)

Key fixes applied:
  1. <description> (<agent>)
  ...

Details: review-findings.md
```
