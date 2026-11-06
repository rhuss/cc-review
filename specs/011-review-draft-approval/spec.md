# Feature Specification: Review Draft Approval

**Feature Branch**: `011-review-draft-approval`

**Created**: 2026-11-02

**Status**: Draft

**Input**: Brainstorm `brainstorm/12-review-draft-approval.md`, GitHub issue [#13](https://github.com/rhuss/cc-review/issues/13): "Bulk review: show each drafted review for approval before posting, and keep its attribution accurate", extended to single-PR interactive review.

## Overview

A PR review that cc-review posts appears on GitHub under the user's account. Today the user approves findings, but the final text (summary body, "What Went Well", rewritten inline comments) is generated and posted without the user seeing it. That text can contain sentences the run cannot back (claims that the user curated findings, test results nobody recorded), typography defects, and comments that lost the labeled structure of the reviewer template.

This feature makes every interactive posting path draft the review first, check the draft automatically, show it to the user in full, and post exactly the approved text after fresh safety checks. Attribution statements are built from facts the run recorded, and the comment structure is fixed by construction instead of being left to the prose rewrite.

## Clarifications

### Session 2026-11-02

- Q: Which conversation changes since analysis withhold a post? → A: Any review thread, review comment or PR conversation comment created after the analysis time (recorded when the analysis collects the conversation; when the analysis time or an item's creation time is unknown, an item counts when it was not present at analysis time, compared by identity, not count) and written by someone other than the authenticated user, a bot account, or an author listed in `pr_posting.ignore_authors`; edits to existing comments do not count.
- Q: What may a user change through an edit at the approval step? → A: Any text in the summary body and inline comment bodies (including the attribution statement), removal of an inline comment, and a downgrade of the review type from request for changes to plain comment; file paths, lines, the pinned commit and the run marker are not editable.
- Q: How is the bulk approval pass answered when several previews are pending? → A: One preview at a time in run order, each shown in full and followed by its own question (approve, edit, skip, or stop and resume later); no "approve all" shortcut, so every posted review was read.
- Q: Where does the attribution statement appear in the posted review? → A: As the first line of the "Review Details" section, before the counts.
- Q: Are the thread replies and resolutions of Step 7.5f written before approval? → A: No. They are part of the draft, shown in the preview, and performed in the post phase.
- Q: Does the new conversation check replace the existing Follow-up Continuity history recheck? → A: No. Both run; a change in either leads to the same withhold and choice. The history recheck compares only new history items under the same rule as the conversation check (created after the analysis, by someone other than the user, a bot or an ignored author; edits do not count), so the run's own pushes and comments never trigger it.
- Q: What counts as curated? → A: The user answered every Critical and Important finding individually; recorded as a flag at decision time, not inferred from the accepted-findings file.
- Q: Do the claim rules apply to finding text written by reviewers? → A: No. They govern text cc-review generates (attribution statement, summary prose, What Went Well); finding text is attributed through its source footer.
- Q: Which statuses do withheld, skipped and deferred PRs get? → A: Check failure withhold: `withheld` with a reason; re-run later: `stale`; skip: `skipped`; fixes pushed but post skipped: `actioned` with a reason. Single-PR mode reports each in its final summary.
- Q: Do bot comments count as a conversation change? → A: No. Comments by bot accounts are ignored, and so are comments by the logins in `pr_posting.ignore_authors` (default empty; for CI accounts that are regular GitHub users); new reviews by other people count.
- Q: What happens when an edit removes an inline comment? → A: The finding is dropped from the review: its table row is removed and the posted and not-posted counts are adjusted.
- Q: What if no pinned commit is available? → A: Never post without one; a missing or mismatched commit makes the review stale, with no redraft.
- Q: In bulk mode, how are thread actions handled for a PR that gets no review? → A: Like a review draft: the drafting worker only drafts them (no write call, no approval); the deferred Approve pass shows their preview with approve, edit, skip or stop; unattended mode approves them by policy; the Post pass performs them after the check, and a changed conversation withholds them.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Approve the exact review text in single-PR review (Priority: P1)

A user runs an interactive single-PR review, decides which findings to post, and then sees the complete review exactly as it would appear on GitHub: the review type (plain comment or request for changes), the full summary body, every inline comment with its file and line, and the findings that only go into the summary with the reason. The user approves, asks for a change, or skips posting. Only an approved draft is posted, and it is posted unchanged.

**Why this priority**: This is the smallest slice that removes the core risk (unseen text under the user's name) and it exercises the shared draft, check, preview and post path that every other story reuses.

**Independent Test**: Run an interactive single-PR review against a test PR, choose to post findings, and confirm that a preview appears before any write to GitHub, that skipping posts nothing, and that an approved review on GitHub matches the approved draft byte for byte.

**Acceptance Scenarios**:

1. **Given** an interactive single-PR review with accepted findings, **When** the findings decision completes, **Then** the user sees the full preview, including any proposed thread replies and resolutions, and nothing has been written to GitHub yet.
2. **Given** a preview, **When** the user approves it, **Then** the posted review (body, review type, inline comments with paths and lines, pinned commit) is identical to the approved draft.
3. **Given** a preview, **When** the user describes a change in plain words, **Then** the change is applied to the draft, the automatic checks run again, the updated preview is shown, and the user is asked again.
4. **Given** a preview, **When** the user skips, **Then** no review is posted and the local report still exists.

---

### User Story 2 - Approve all bulk drafts in one sitting (Priority: P1)

A user runs a deferred bulk review over several PRs and decides per PR (post, fix, fix then post, marker, skip). During apply, cc-review first runs all fix rounds and pushes, then drafts the review for every PR that will be posted, without writing anything to GitHub. The user then goes through every preview together, in run order, and approves, edits or skips each one. Only after that pass are the approved reviews posted, each after fresh safety checks.

**Why this priority**: The bulk run that triggered the issue posted five reviews whose text the user never saw. This is the mode where the gap does the most damage.

**Independent Test**: Run a deferred bulk review over at least two test PRs with `post` decisions and confirm that all previews are shown before any review is posted, that a skipped PR gets no review, and that each posted review matches its approved draft.

**Acceptance Scenarios**:

1. **Given** a deferred bulk run with `post` decisions, **When** apply starts, **Then** no review is posted for any PR before all of its previews have been shown and answered.
2. **Given** a PR with the decision fix then post, **When** its draft is prepared, **Then** the draft reflects only the findings that the fix rounds left open.
3. **Given** an approved PR, **When** an interrupted run is resumed, **Then** the user is not asked again for that PR unless its draft changed since approval.
4. **Given** an approved PR whose head moved after analysis, **When** the post pass reaches it, **Then** nothing is posted and the PR is marked stale, as today.
5. **Given** an approved PR that received new review threads or comments since analysis, **When** the post pass reaches it, **Then** nothing is posted until the user chooses to post anyway, skip, or re-run later.

---

### User Story 3 - Attribution that matches what happened (Priority: P1)

A reader of a posted review sees one fixed attribution statement that is true for this run: whether the user curated the findings one by one, which commands the run itself executed and with what result, and that repro scenarios come from reading the code unless they were executed. The prose rewrite cannot invent other first-person claims.

**Why this priority**: False statements under the user's name ("I curated", "tests passed") are the most serious defect reported in the issue, and the preview alone does not prevent them in unattended mode.

**Independent Test**: Draft reviews for a PR posted without per-finding review and for one with per-finding review, and confirm that only the second says the findings were curated, and that neither contains a test result the run did not record.

**Acceptance Scenarios**:

1. **Given** a PR posted without per-finding review, **When** its draft is built, **Then** the text does not say that the user curated or selected findings.
2. **Given** a PR whose findings the user reviewed one by one, **When** its draft is built, **Then** the attribution statement says the findings were curated.
3. **Given** a reviewer agent that reported running a test, but the run recorded no outcome for it, **When** the draft is built, **Then** the result is either absent or labeled as reported by an agent and not verified.
4. **Given** a run whose fix round executed the test suite, **When** the draft is built, **Then** the attribution may name that command with its recorded outcome.

---

### User Story 4 - Predictable comment structure (Priority: P2)

Every inline comment follows the reviewer template: a bold severity label with what is wrong, a "Why this matters" part, a "Suggested fix" part, and the source footer, in that order. The summary keeps its fixed headings. The prose rewrite improves wording inside each part but cannot remove or merge the labels.

**Why this priority**: Users rely on a predictable format to scan reviews; a previous run lost the labels because the humanizer smoothed them into prose.

**Independent Test**: Draft a review with the prose rewrite enabled and confirm that every inline comment contains the three labels and the source footer in order, and the summary contains its headings in order.

**Acceptance Scenarios**:

1. **Given** the prose rewrite is available, **When** a draft is built, **Then** every inline comment starts with the severity label and contains "Why this matters" and "Suggested fix" labels and the source footer, in that order.
2. **Given** the reviewer voice template, **When** a user reads its examples, **Then** every example starts with the severity label, matching the fallback template.

---

### User Story 5 - Automatic draft checks (Priority: P2)

Before a draft is shown (or, in unattended mode, before it is posted), an automatic check verifies it: run marker present, pinned commit equals the expected head, comment and summary structure intact, no em or en dashes, no first-person verification claims that the run's facts do not back, and no sentence that runs into the next without a space. A failing draft goes back to drafting once; whatever still fails is shown next to the preview.

**Why this priority**: The check catches small defects a human might miss while reading many previews, and it is the only safeguard in unattended mode.

**Independent Test**: Feed drafts with each defect type to the check and confirm each is reported; feed a clean draft and confirm it passes.

**Acceptance Scenarios**:

1. **Given** a draft missing the run marker, **When** the check runs, **Then** it reports the missing marker.
2. **Given** a draft containing "I ran the tests" without a recorded execution, **When** the check runs, **Then** it reports an unsupported claim.
3. **Given** a draft that still fails after one redraft, **When** the preview is shown, **Then** the remaining check findings appear next to it.

---

### User Story 6 - Unattended and non-interactive posting unchanged in behavior (Priority: P3)

Unattended bulk runs and single-PR runs with interaction turned off still post without asking anyone, with the same review types and policies as today. They now use the same draft building, structure and attribution rules and the automatic check.

**Why this priority**: Nobody is present to approve, so behavior must stay non-blocking; the shared path improves text quality there too.

**Independent Test**: Run an unattended bulk review and confirm no prompt appears, reviews are posted as non-blocking comments as today, and the posted text passes the automatic check.

**Acceptance Scenarios**:

1. **Given** an unattended bulk run, **When** apply runs, **Then** no preview or question is shown and reviews are posted as today.
2. **Given** an unattended draft that still fails the check after one redraft, **When** posting, **Then** the review is withheld for that PR, the PR gets the status `withheld` with the check findings as reason, and the run summary lists it under "Needs attention".

---

### Edge Cases

- The user edits a draft so that it fails the check (for example, adds a dash): the remaining findings are shown with the updated preview, and the user may still approve.
- A draft has no inline comments (all findings are summary-only or an approved unchanged-request acknowledgment): the preview still shows the full summary and review type.
- The duplicate check finds a review carrying this run's marker already on the PR (an earlier timed-out post succeeded): nothing new is posted; the existing review is recorded and reported.
- The approved draft file was changed after approval (by hand or by a redraft): posting refuses it and the user is asked again.
- The head moved between approval and post in single-PR mode: nothing is posted; the user is told the review is stale and the local report is kept.
- Posting fails with a timeout although GitHub created the review: the existing marker search detects it and no duplicate is posted.
- The inline comment count exceeds the configured limit: truncation happens during drafting, so the preview shows the truncated result and the moved findings.
- The user stops the bulk approval pass midway: decisions already given are recorded; a resume continues with the unanswered previews.
- The prose rewrite is not available: drafts use the template wording; all rules for structure, attribution and checks still apply.

## Requirements *(mandatory)*

### Functional Requirements

**Drafting**

- **FR-001**: Every review posting path (single-PR interactive, single-PR non-interactive, deferred bulk, unattended bulk) MUST first produce a draft consisting of the exact submission payload, the proposed thread actions (replies to and resolutions of earlier threads, continuation responses) and a human-readable preview, without any write call to GitHub. Thread actions are performed only in the post phase, after approval and the checks of FR-021 (fingerprint, head and conversation checks, without the review post), which run immediately before each reply and each resolution. When thread actions are approved without a review, the approval records a fingerprint of the thread actions alone.
- **FR-002**: The preview MUST contain the review type in plain words, the full summary body, every inline comment with its file path and line (or line range), and every summary-only finding with the reason it is not inline.
- **FR-003**: Inline comments MUST be assembled from the reviewer fallback template with the labels `**{severity}**:`, `**Why this matters**:`, `**Suggested fix**:` and the `_Source: ..._` footer, in that order. The prose rewrite MUST receive and change only the text inside each part, never the labels, file paths, line numbers, identifiers, commands or numbers.
- **FR-003a**: A finding edited during the findings decision MUST keep its edited description and edited fix as separate values, each placed in its own template part ("what is wrong" and "Suggested fix"). Text the user wrote is not passed through the prose rewrite.
- **FR-004**: The summary body MUST be assembled from its fixed sections, in this order: `## cc-review Summary`, `### Follow-up progress` when the PR has prior review history (as required by Follow-up Continuity), `### What Went Well` when there are positive observations, `### Findings` with its table, `### Review Details`, then the run marker and completion lines. The prose rewrite MAY change only prose inside sections.
- **FR-005**: The reviewer voice template's examples MUST start with the severity label (for example `**Critical**:`), consistent with the fallback template, which is the single format contract.
- **FR-006**: Truncation to the configured maximum number of inline comments MUST happen during drafting, so the preview reflects what will be posted.

**Attribution**

- **FR-007**: The summary body MUST contain exactly one attribution statement generated by cc-review from recorded run facts, not by the prose rewrite, placed as the first line of the "Review Details" section. The prose rewrite MUST keep it verbatim.
- **FR-008**: The attribution statement MUST say the findings were curated or selected by the user only when the user answered every Critical and Important finding individually in the findings decision (bulk drill-down or single-PR per-finding review). A "post all" shortcut or batch acceptance alone is not curation. The curation flag is recorded at decision time (FR-010a), never inferred from the existence of the accepted-findings file.
- **FR-009**: A command or test result MUST appear in posted text only when the run itself executed that command and recorded its outcome; results reported by reviewer agents without a recorded execution MUST be omitted or labeled as reported by an agent and not verified.
- **FR-010**: When the posted review contains a repro scenario (a failure scenario or reproducer that a reviewer describes as steps or inputs leading to the defect), the attribution statement MUST state that such scenarios were derived from reading the code and were not executed, unless the run recorded their execution. Without any repro scenario, this part of the statement is omitted.
- **FR-010a**: The run MUST record its facts per PR at the moment they happen and keep them next to the PR's run data, so they survive a resume: the curation choice made at the findings decision, and for every fix round the test command with its round and outcome (passed, failed, or no test command detected). An empty regression list alone is not evidence that tests passed. Command reviewers (external review tools) are not "executed commands" for attribution purposes; their output is attributed through the source footer.
- **FR-011**: Text that cc-review generates (attribution statement, summary prose, What Went Well) MUST NOT contain first-person verification claims ("I ran", "I tested", "I verified", "I curated" and equivalents) that the recorded run facts do not support. FR-009 to FR-011 govern this generated text; finding text written by a reviewer is attributed to that reviewer through its source footer and is not checked for claims.

**Automatic draft check**

- **FR-012**: An automatic check MUST run on every draft before it is previewed or (in unattended and non-interactive modes) posted, and report: missing run marker; missing or different pinned commit; an inline comment missing any of the three labels or the source footer, or with them out of order; summary sections missing or out of order; attribution statement missing, duplicated, or not the first line of "Review Details"; em or en dashes; unsupported first-person verification claims (FR-011); a sentence end (`.`, `!` or `?`) directly followed by an uppercase letter without a space. The dash, first-person and missing-space checks apply only to prose: text inside inline code, fenced code blocks, URLs and file paths is excluded.
- **FR-013**: When the check fails, the draft MUST be sent back to drafting once with the check findings; remaining findings MUST be shown next to the preview.
- **FR-014**: In unattended and non-interactive modes, a draft that still fails the check after one redraft MUST NOT be posted; the PR gets the status `withheld` with the remaining check findings as reason (bulk) or is reported as withheld in the final summary (single-PR), and is listed as needing attention.
- **FR-014a**: A missing or different pinned commit is not sent back to drafting: no review is posted without a pinned commit, and the review is treated as stale (FR-022).

**Approval**

- **FR-015**: In single-PR interactive review, after the findings decision, the user MUST see the full preview and choose approve, edit, or skip before anything is posted.
- **FR-016**: An edit MUST be given in plain words, applied to the draft, followed by a re-run of the automatic check and a fresh preview before the user is asked again. An edit MAY change any text of the summary body and inline comment bodies (including the attribution statement), remove an inline comment (which drops that finding from the review entirely: its findings-table row is removed and the posted and not-posted counts are adjusted), or downgrade the review type from request for changes to plain comment. It MUST NOT change file paths, lines, the pinned commit or the run marker.
- **FR-017**: Approval MUST record a fingerprint of the approved payload. Posting MUST refuse a payload whose fingerprint differs from the approved one.
- **FR-018**: In deferred bulk review, apply MUST run in three passes: (1) prepare: fix rounds and pushes for PRs with fix decisions, then drafts for all PRs with post decisions; (2) approve: all previews shown in one pass in run order, one preview at a time, each shown in full and answered with approve, edit, skip, or stop (resume later), with no "approve all" shortcut; (3) post: approved drafts posted one PR at a time.
- **FR-019**: Each bulk approval or skip MUST be recorded the moment it is given; a resumed run MUST NOT ask again for a PR whose draft is unchanged since approval, and MUST ask again when it changed.
- **FR-019a**: Drafts MUST be persisted with the PR's run data and reused on resume. A draft is rebuilt only when its file is missing or its inputs changed (expected head, set of findings to post, run facts); rebuilding is the only way a draft's fingerprint changes.
- **FR-020**: A PR skipped at the approval pass MUST be treated like a skipped decision today (status `skipped`, no review, no marker, selected again by the next run). When this run already pushed fixes to that PR, its status is `actioned` with the reason "fixes pushed, review not posted".

**Posting**

- **FR-021**: Immediately before each post, cc-review MUST check that (a) the PR head equals the expected head, (b) no review with this run's marker exists on the PR, and (c) no review thread, review comment or PR conversation comment was created after the analysis time by someone other than the authenticated user, a bot account, or an author listed in the configuration key `pr_posting.ignore_authors` (a list of logins, default empty, treated like bot accounts); a new review by another person also counts. The analysis time is recorded when the analysis collects the conversation; when it is missing, or an item has no creation time, an item counts when it was absent at analysis time (compared by identity). Edits to existing comments do not count for this check. The Follow-up Continuity history recheck before every remote action still runs and applies the same rule to the items of the rebuilt history: only new items by other people count, never edits, the run's own pushes or the user's own comments.
- **FR-022**: A moved head MUST withhold the post and mark the PR stale (bulk) or report the review as stale (single-PR), keeping the local report.
- **FR-023**: An existing review with this run's marker MUST be recorded and reported as the posted review; no second review is posted.
- **FR-024**: A conversation change (FR-021(c)) or a Follow-up Continuity history change (FR-021) MUST withhold the post; in interactive modes the user chooses post anyway, skip (status `skipped`), or re-run later (status `stale`); in unattended mode the PR gets the status `withheld` with the reason and is reported as needing attention. Single-PR mode reports the outcome in its final summary.
- **FR-020a**: Analysis MUST record, in both single-PR and bulk mode, the analysis time and the identities (and author type, so bot accounts can be ignored) of the PR's review threads, review comments, conversation comments and reviews, so the check in FR-021(c) can compare against them.
- **FR-025**: The submitted review request MUST match the fingerprint of the approved payload (interactive modes) or of the checked draft (unattended and non-interactive modes, which record a fingerprint for the checked draft the same way). What GitHub stores afterwards is not compared.
- **FR-026**: Existing error recovery MUST be kept: timeouts trigger the marker search before any retry; authentication and other failures write the recovery file; a head-moved rejection is reported as stale without retry (except the existing brief retry after a push by this run).

**Unchanged behavior**

- **FR-027**: Unattended bulk mode and non-interactive single-PR mode MUST NOT prompt the user, and MUST keep today's review type policy (unattended posts non-blocking comments).
- **FR-028**: Triage posting (thread replies and resolutions) is out of scope and MUST NOT change.
- **FR-029**: The fixed-text no-findings marker is not drafted or previewed; it keeps today's behavior, including its head check. SC-001 and SC-002 apply to reviews with a generated summary body.

### Key Entities

- **Review draft**: the exact submission payload for one PR (review type, summary body, inline comments, pinned commit) plus its preview; produced without writes; stored next to the PR's run data.
- **Draft check result**: the list of check findings for one draft, with the redraft attempt count.
- **Run facts**: what the run itself knows about this review: whether findings were curated one by one, which commands the run executed with their outcomes, and whether repro scenarios were executed. Source of the attribution statement and of the unsupported-claim check.
- **Approval record**: per PR, the user's answer (approved, skipped) and the fingerprint of the approved payload; persisted so a resumed run can rely on it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In interactive single-PR and deferred bulk review, 100% of posted reviews were shown in full to the user and approved before posting.
- **SC-002**: 100% of submitted review requests match the fingerprint of the approved (or, in unattended and non-interactive modes, checked) draft.
- **SC-003**: 0 posted reviews claim user curation for a PR whose findings were not reviewed one by one, and 0 contain a command or test result the run did not record.
- **SC-004**: 100% of posted inline comments contain the severity, "Why this matters" and "Suggested fix" labels and the source footer in order.
- **SC-005**: Each defect class listed in FR-012 is detected by the automatic check on a test draft that contains it, and a clean draft passes.
- **SC-006**: For a five-PR deferred bulk run, the user answers all previews in a single approval pass without waiting for drafting between previews.
- **SC-007**: Unattended runs complete without any prompt, as today.

## Assumptions

- The only commands the run itself executes are the test runs of fix rounds (and command reviewers, which are attributed through the source footer). Their outcomes are not fully recorded today; FR-010a adds that. Reviewer agents' own commands are not recorded, and recording them is out of scope.
- Non-interactive single-PR review is treated like unattended mode (nobody to approve), so it posts directly after the automatic check.
- New threads or comments since analysis are detected against the conversation data recorded at analysis time, by identity (see FR-021).
- The approval record for single-PR review only needs to live for the session; a single-PR review interrupted before posting is re-run rather than resumed.
- The exact wording of the attribution statement for each combination of facts is a planning decision, constrained by FR-007 to FR-011.
- An edited draft may still fail the automatic check (for example, the user adds an unsupported claim); the user sees the findings and may approve anyway, because the review goes out under their own name.
- When the prose rewrite is unavailable, template wording is used; structure, attribution and checks apply unchanged.
