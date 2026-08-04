# Data Model: PR Review Comments

## Entities

### Finding (extended, transient fields)

The existing Finding entity (`core/schemas/finding.schema.json`) is not modified on disk. Two transient in-memory fields are added during the posting pipeline:

| Field | Type | Description |
|-------|------|-------------|
| `accepted` | boolean | Whether the reviewer accepted this finding for posting. Set during interactive review. |
| `edited_text` | string or null | Reviewer's edited description text, replacing the original `description` field in the posted comment. Null if not edited. |

These fields exist only in the review command's in-memory working set during Step 7.5. They are not persisted to `review-findings.md` or the finding schema.

### Review Submission

A transient data structure assembled from accepted findings before posting.

| Field | Type | Description |
|-------|------|-------------|
| `pr_number` | integer | Target PR number |
| `run_id` | string (UUID) | Unique identifier for this review run |
| `event` | enum | `REQUEST_CHANGES` or `COMMENT` |
| `body` | string | Summary body (What Went Well + findings table + attribution + run-id marker) |
| `comments` | array | Inline comment objects for the GitHub API |

Each entry in `comments`:

| Field | Type | Description |
|-------|------|-------------|
| `path` | string | File path relative to repo root |
| `line` | integer | Line number within the diff hunk |
| `side` | string | Always `RIGHT` (review comments on the new version) |
| `body` | string | Formatted comment text (what/why/fix + source footer) |

### Run ID Marker

Embedded in the review body as an HTML comment:

```
<!-- cc-review:run-id:550e8400-e29b-41d4-a716-446655440000 -->
```

Used by re-run detection to identify previous cc-review reviews on the same PR.

### Diff Hunk Map

Built from `gh pr diff` output to determine which findings can be posted inline.

| Field | Type | Description |
|-------|------|-------------|
| file | string | Relative file path |
| hunks | array | List of `{start: int, end: int}` line ranges from the new side of the diff |

### Previous Review Record

Extracted from existing reviews on re-run.

| Field | Type | Description |
|-------|------|-------------|
| review_id | integer | GitHub review ID |
| run_id | string | UUID from the marker |
| thread_id | string | GraphQL node ID for each inline comment thread |
| path | string | File path the comment is on |
| line | integer | Line number the comment is on |
| body | string | Original comment body |

## Relationships

```
Review Command
  ├── dispatches 6 agents + external tools
  │     └── produces Findings
  ├── builds Diff Hunk Map (from gh pr diff)
  ├── interactive review
  │     └── marks Findings as accepted/rejected/edited
  ├── assembles Review Submission
  │     ├── inline comments (from accepted findings within diff hunks)
  │     └── summary body (all accepted findings + summary-only findings)
  └── posts via gh api

Re-run
  ├── scans Previous Review Records (by run-id marker)
  ├── matches previous comments against current findings (by file + line proximity)
  └── resolves matched threads via platform.sh resolve_thread

Triage
  ├── recognizes cc-review threads (by source footer pattern)
  ├── assesses replies against original finding
  └── resolves or leaves open via platform.sh
```

## State Transitions

### Finding Lifecycle (within a single review run)

```
[Discovered] → [Deduplicated] → [Presented] → [Accepted|Rejected|Edited] → [Posted|Skipped]
```

### Thread Lifecycle (across runs)

```
[Posted] → [Reply received] → [Triage assesses] → [Resolved|Left open]
                             → [Re-run detects fix] → [Resolved]
```
