---
name: review
description: Multi-agent code review with autonomous fix loop. Dispatches 6 specialized review agents, merges findings, auto-fixes Critical/Important issues.
argument-hint: "[--pr <number>] [--spec <path>] [--hints <path>] [--output <path>] [--no-fix] [--max-rounds <n>] [--no-external] [--no-coderabbit] [--no-copilot] [--no-codex] [--parallel] [--sequential]"
---

# Code Review

## Prerequisites

### Config Resolution

```bash
source "$(dirname "$0")/../scripts/resolve-config.sh"
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

### Output Path

```bash
OUTPUT_DIR=$(resolve_config "output_dir" ".")
OUTPUT_PATH="${OUTPUT_FLAG:-$OUTPUT_DIR/review-findings.md}"
```

## Step 1: Determine Changed Files

```bash
MAIN_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@' || echo "main")
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
TEST_CMD=$(resolve_config "test_command" "")
TEST_TIMEOUT=$(resolve_config "test_timeout_seconds" "300")

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

Dispatch all review agents and external tools together. In sequential mode (default), run them one after another. In parallel mode (`--parallel`), dispatch all of them concurrently.

Each internal agent gets:
- The Common Preamble from `core/agents/preamble.md`
- Its specific prompt from `core/agents/<name>.md`
- The list of changed files and their contents
- The spec text (if `--spec` provided)
- Review hints (if detected)
- For Agent 6 only: the DECLARED_GOALS block

If `REVIEW_HINTS` is non-empty, include item 11 in the preamble with the contents of the review hints file between the delimiters. If empty, omit item 11.

**Dispatch list:**
1. Correctness (`core/agents/correctness.md`)
2. Architecture & Idioms (`core/agents/architecture.md`)
3. Security (`core/agents/security.md`)
4. Production Readiness (`core/agents/production.md`)
5. Test Quality (`core/agents/test-quality.md`)
6. Goal Alignment (`core/agents/goal-alignment.md`) - skip if `GOALS_AVAILABLE` is false
7. CodeRabbit (external) - skip if not `CODERABBIT_AVAILABLE`
8. Copilot CLI (external) - skip if not `COPILOT_AVAILABLE`
9. Codex CLI (external) - skip if not `CODEX_AVAILABLE`

Report progress after each completes:
```
Agent 1/N: Correctness... done, N findings
Agent 2/N: Architecture & Idioms... done, N findings
...
Agent 7/N: CodeRabbit (external)... done, N findings
```

### External Tool Invocations

**CodeRabbit** (if `CODERABBIT_AVAILABLE`):
```bash
REVIEW_FILES=$(git diff --name-only "${MAIN_BRANCH}...HEAD" 2>/dev/null | grep -v -E '^(specs/|brainstorm/)' | sort -u)
coderabbit review --agent --files $REVIEW_FILES 2>&1
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

## Step 4: Merge and Deduplicate Findings

1. Collect all findings from internal agents and external tools
2. Normalize to the Finding schema (see `core/schemas/finding.schema.json`)
3. Sort by file path, then line number
4. Deduplicate: for findings with same file, overlapping line range, and same category, keep the one with the longer description. Add the other's source_agent to `also_reported_by`. Use higher severity and confidence.
5. Exception: `goal-alignment` findings do NOT dedup against other categories
6. Assign sequential IDs (FINDING-1, FINDING-2, ...)

## Step 5: Gate Check

- Count Critical and Important findings
- If Critical + Important = 0: **GATE PASS**
- If Critical + Important > 0: proceed to fix loop (or fail if `--no-fix` or max rounds reached)
- Notable findings are excluded from the gate check

## Step 6: Autonomous Fix Loop

Maximum rounds from config (default 3). Skip if `--no-fix` is passed.

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
