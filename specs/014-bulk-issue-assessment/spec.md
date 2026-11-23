# Feature Specification: Bulk Issue Assessment with Optional Draft-PR Fixes

**Feature Branch**: `015-bulk-issue-assessment`

**Created**: 2026-11-23

**Status**: Draft

**Input**: Brainstorm `brainstorm/17-bulk-issue-assessment.md`. Add a bulk mode to the cc-review `issue` command that selects incoming issues by search filters, skips issues that were already handled, assesses each selected issue in a fresh context, lets the maintainer approve and post each reply one by one, and optionally fixes small issues as draft pull requests. Deterministic parts (selection, skip rules, paging, run state, loop control, posting, pull request creation, report counts) are scripts; the prompt holds only judgment and conversation.

## Clarifications

### Session 2026-11-23

- Q: Is an approved reply posted right away, or only after the whole approval pass? → A: Right away, as soon as the maintainer approves that issue; the post result is recorded before the next issue is shown.
- Q: Do all assessments finish before the first approval, or do assessment and approval alternate per issue? → A: All assessments finish first (assessment pass), then the approval pass walks the assessed issues in selection order.
- Q: How does the maintainer edit a reply draft? → A: By describing the change in their own words or pasting replacement text; the reply is redrafted, re-rendered through the same validation, and shown in full again.
- Q: What may a fix worker do beyond editing files in its worktree? → A: Nothing. It reads the project and edits files in its worktree; it runs no commands, makes no network calls, pushes nothing, and opens nothing. Pushing the branch and opening the draft pull request are done afterwards by the deterministic helper, only for a fix that stayed within the small bound.
- Q: Is `--search` required? → A: No. Without it, candidates are all open issues; the skip rules still apply.
- Q: What counts as a linked pull request? → A: Any pull request that references the issue (closing keyword or cross-reference). A maintainer pull request causes a skip when it is open or merged, not when it was closed unmerged. Only open non-maintainer pull requests can be handed to review.
- Q: May a fix run the project's tests on the maintainer's machine? → A: No. Code edited under the influence of untrusted issue text never runs locally; tests run in the repository's checks on the draft pull request, and the pull request body says so. (Supersedes an earlier per-batch test confirmation, found unsafe in plan review because the confirmation preceded the code it would run.)
- Q: May an edit change the recommendation? → A: Yes; a changed recommendation re-renders the comment and recomputes the label and fix eligibility.
- Q: Does the issue author's own comment, or a maintainer's label or assignment, count as answered? → A: No. Only a reply from a maintainer other than the issue author counts.
- Q: Is test code in a fix unlimited? → A: No. Test files have their own cap of 300 added plus removed lines.
- Q: Where does run state live when there is no local clone of the target repository? → A: In a per-user cc-review state directory keyed by repository; the batch works, fixes are not offered.
- Q: How is the per-issue decision asked when post/edit/skip plus fix/review/leave exceed one question's options? → A: One prompt with two questions: Reply (Post, Edit, Skip) and Follow-up (Fix it or Review linked PRs, Leave it); it counts as one decision step.
- Q: What happens when an issue's history is longer than one selection query returns? → A: It is skipped with reason "history too long to verify" and listed in the report.
- Q: Which code review decisions shaped the final behavior? → A: Run state moves out of the checkout; state is hashed around every worker; a 30-minute session lock guards resume; binary changes abandon fixes; only maintainer or bot markers count; withheld posts drop unpushed fixes; the maintainer's own git filters are accepted.
- Q: What happens when posting a comment or label fails (network, permissions, rate limit)? → A: The failure is recorded for that issue and shown immediately; the run continues with the next issue, and a resumed run retries only posts whose comment was not confirmed as published.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Assess and answer a batch of incoming issues (Priority: P1)

A maintainer wants to work through new issues that nobody has handled yet, including issues opened by people who never interacted with them. They run `issue --bulk` with a search filter (labels and keywords), get a batch of up to ten untouched issues, and for each issue see an assessment and a full reply draft. They post, edit or skip each reply. Posting adds the assessment comment and the label for the recommendation.

**Why this priority**: This is the core gap. Today an issue from a stranger stays invisible to cc-review until someone touches it, and the single-issue command needs an explicit number. A batch flow with per-issue approval delivers value even without fixes.

**Independent Test**: In a test repository with several open issues (some untouched, some already answered), run `issue --bulk --search 'label:bug'` and confirm that only untouched matching issues are selected, each gets an assessment and reply draft, and only replies the maintainer approves are posted, each with the recommendation label.

**Acceptance Scenarios**:

1. **Given** open issues matching the search, none answered by a maintainer, **When** the maintainer runs `issue --bulk --search '<query>'`, **Then** up to the batch limit of issues are selected, newest first, and each is assessed with the same need, fit and recommendation judgment as the single-issue command.
2. **Given** an assessed issue, **When** the approval step reaches it, **Then** the maintainer sees the complete rendered comment (reply plus assessment section) exactly as it would be posted and chooses post, edit or skip.
3. **Given** the maintainer chooses post, **When** posting completes, **Then** the issue has the rendered comment (carrying the cc-review assessment marker) and the label mapped to the recommendation, and nothing else on the issue changed.
4. **Given** the maintainer chooses edit and describes the change or pastes replacement text, **When** the reply is redrafted, **Then** the new rendered comment is shown in full again and requires a new post, edit or skip decision.
5. **Given** the maintainer chooses skip, **When** the run continues, **Then** nothing is posted to that issue and the report lists it as skipped by the maintainer.

---

### User Story 2 - Transparent selection with skip rules and paging (Priority: P1)

The maintainer trusts that the batch contains only issues that still need a first answer, and that nothing is dropped silently. Issues that already have a cc-review assessment, a maintainer reply, or a maintainer-owned linked pull request are skipped. When skipped issues leave the batch short, selection keeps going through older matching issues until the batch is full or no candidates remain, bounded by a scan ceiling.

**Why this priority**: Without correct skip rules the batch fills with already-handled issues, which is the problem the inbox showed (all ten selected issues were backlog with no action). Without paging a batch can come back nearly empty although untouched issues exist.

**Independent Test**: Run selection against fixtures containing issues in each skip category plus more untouched issues than fit on the first page, and confirm the selected set, the skip reasons, and the scanned count without any model involvement.

**Acceptance Scenarios**:

1. **Given** an issue with a comment carrying the cc-review assessment marker, **When** selection runs, **Then** the issue is skipped with reason "already assessed".
2. **Given** an issue where a commenter recorded as owner, member or collaborator, other than the issue author, replied, **When** selection runs, **Then** the issue is skipped with reason "maintainer replied".
3. **Given** an issue referenced by an open or merged pull request that a maintainer opened, or that a maintainer reviewed or commented on, **When** selection runs, **Then** the issue is skipped with reason "maintainer PR #M".
4. **Given** an issue referenced only by a pull request from a non-maintainer with no maintainer activity, **When** selection runs, **Then** the issue is selected and the linked pull request is recorded with it.
5. **Given** an issue opened by a maintainer with no replies, **When** selection runs, **Then** the issue is selected.
6. **Given** a limit of 10 and a first page where 8 candidates are skipped, **When** selection runs, **Then** it continues to older candidates until 10 issues are selected or candidates are exhausted.
7. **Given** the scan ceiling is reached before the batch is full, **When** selection stops, **Then** the report states that the ceiling was reached, how many candidates were scanned, and how to raise it.
8. **Given** a finished run, **When** the report is shown, **Then** it lists every skipped issue with its reason and the counts of candidates scanned, skipped by reason, and selected.

---

### User Story 3 - Fix small issues as draft pull requests (Priority: P2)

For an issue whose assessment recommends pursuing it and judges the change small, the maintainer can choose "fix it" in addition to (or instead of) posting the reply. After all approvals, the chosen fixes run one at a time, each in its own isolated worktree with a fresh context, and each opens a draft pull request that says "Fixes #N". The draft pull request is the review checkpoint.

**Why this priority**: It turns small confirmed problems into reviewable changes without manual setup, but the assessment and reply flow is valuable on its own.

**Independent Test**: In a test repository with a small confirmed bug issue, run a batch, choose "fix it", and confirm that a draft pull request referencing the issue is opened from a new branch, that the maintainer's checkout is unchanged, and that the pull request body states that tests are left to the pull request's checks.

**Acceptance Scenarios**:

1. **Given** an assessment with recommendation Pursue and a fix-eligible judgment, **When** the approval step reaches it, **Then** the maintainer is offered "fix it" or "leave it" independently of the post decision.
2. **Given** an assessment that is not fix-eligible, **When** the approval step reaches it, **Then** no fix option is offered and the reason is visible.
3. **Given** one or more chosen fixes, **When** the approval pass ends, **Then** the fixes run sequentially after all approvals, each in a fresh worktree created from the default branch, never in the maintainer's checkout.
4. **Given** a fix completes within the small bound, **When** it is published, **Then** a branch is pushed and a draft pull request is opened under the maintainer's account with a body containing "Fixes #N", a short summary, and a note that tests were not run locally and are left to the pull request's checks.
5. **Given** any fix, **When** it is prepared and published, **Then** no project code, test, build or hook command runs on the maintainer's machine for that fix.
6. **Given** a fix that fails or grows beyond the small bound, **When** the fix worker stops, **Then** no branch is pushed, no pull request is opened, the worktree is removed, and the report states the reason. Any reply already posted stays.

---

### User Story 4 - Hand a newcomer's linked pull request to review (Priority: P2)

When a selected issue has a linked pull request from a non-maintainer, the assessment mentions that pull request and the reply may refer to it. Instead of "fix it", the maintainer is offered "review linked PRs" for open linked pull requests. Chosen pull requests are handed to the existing bulk review after the batch.

**Why this priority**: It closes the gap where an issue and its "Fixes #N" pull request from the same newcomer would otherwise fall through: the issue skipped as "has a PR", the PR missed or excluded by bulk review selection, and the need-and-fit question never asked.

**Independent Test**: With an issue referenced by a non-maintainer draft pull request, run a batch and confirm the issue is selected, the assessment names the pull request, the "review linked PRs" choice is offered, and choosing it results in a `review --bulk --prs M` handoff at the end.

**Acceptance Scenarios**:

1. **Given** a selected issue with a non-maintainer linked pull request, **When** the assessment is shown, **Then** it names the pull request with its link.
2. **Given** that issue, **When** the approval step offers actions, **Then** "review linked PRs" (naming each open linked pull request) replaces "fix it".
3. **Given** one or more "review linked PRs" choices, **When** the batch ends, **Then** the chosen pull requests are handed to `review --bulk --prs <list>` as one explicit list, or the exact command is printed where the harness cannot chain commands.

---

### User Story 5 - Resume an interrupted batch (Priority: P3)

A batch can take a while. If the session ends mid-run, `issue --bulk --resume` continues where it stopped without re-assessing finished issues, re-posting replies, or opening duplicate pull requests.

**Why this priority**: Protects against duplicate public comments and duplicate pull requests, but most batches finish in one sitting.

**Independent Test**: Interrupt a run after some replies were posted and one fix was queued, then resume and confirm posted issues are not posted again, pending approvals continue, and the queued fix runs once.

**Acceptance Scenarios**:

1. **Given** an unfinished run, **When** the maintainer starts `issue --bulk` without `--resume`, **Then** they are told an unfinished run exists and offered to resume it or start fresh; starting fresh marks the old run abandoned.
2. **Given** a resumed run, **When** it continues, **Then** issues with a recorded post are never posted again, recorded decisions are kept, and only undecided issues and unfinished fixes remain.
3. **Given** a fix that recorded an opened pull request, **When** the run resumes, **Then** that fix is not run again.

---

### Edge Cases

- No candidates match the search: report "No issues matched" with the search used; no run is created.
- All candidates are skipped: report zero selected with skip counts by reason; never describe that as a verified empty queue when the scan ceiling was reached.
- An issue receives a maintainer reply or a cc-review assessment between selection and posting: before posting, the issue is re-checked; if it no longer qualifies, posting is withheld and the maintainer is told why.
- An issue is closed between selection and posting: posting is withheld and reported.
- The recommendation label does not exist in the repository: the comment is posted, the label is not created, and the report names the missing label.
- No verified matching local checkout of the target repository exists, or the maintainer lacks push access to the target repository (for example when only a fork could receive the branch): fix options are not offered and the reason is stated once for the batch.
- The default branch moved while fixes were queued: each fix starts from the current default branch tip at fix time.
- A fix branch name already exists locally or remotely and is not recorded by this run: the fix stops without overwriting and reports the conflict.
- The session ends after a fix branch was pushed but before its pull request was opened: on resume only the pull request is opened, after confirming no open pull request for that branch exists.
- Selection fails partway (rate limit, network, API error): the command stops with an actionable error and creates no run; a failed selection is never reported as an empty batch.
- Collecting or assessing one selected issue fails: that issue is recorded as "assessment failed", left out of the approval pass, and listed in the report; the other issues continue.
- Issue text contains instructions addressed to the assistant: they are treated as untrusted data, never followed, and flagged in the assessment.
- The issue's linked pull request is from a fork: it still counts as a linked pull request for skip and handoff purposes.
- Collection of an issue's conversation is incomplete (shortened history or timeout): the assessment states the limitation and never issues a definitive decline based on missing evidence.
- Posting a comment or label fails (network, permissions, rate limit): the failure is recorded and shown, the run moves on, and resume retries only unconfirmed comments, so a comment is never published twice.
- The harness cannot run per-issue subagents: issues are assessed inline one at a time with a stated warning about context accumulation.

## Requirements *(mandatory)*

### Functional Requirements

**Invocation**

- **FR-001**: The `issue` command MUST accept a bulk mode, `issue --bulk`, with an optional `--search <query>` (repository issue search qualifiers and keywords, for example `label:bug crash`; without it all open issues are candidates), `--limit N` (batch size, default 10), `--scan N` (scan ceiling, default 100), `--repo owner/name`, and `--resume [<run-id>]`.
- **FR-002**: Bulk mode MUST validate all arguments before any service call, and before the single-item unattended dispatch of the `issue` command, with these rules:

  | Input | Result |
  |---|---|
  | issue number or URL with `--bulk` or `--resume` | error: a bulk run selects its own issues |
  | `--unattended` with `--bulk` or `--resume` | error: bulk issue assessment is interactive only |
  | `--search`, `--limit` or `--scan` without `--bulk` | error naming the flag and `--bulk` |
  | `--resume` with `--search`, `--limit` or `--scan` | error: a resumed run keeps its recorded options |
  | `--resume` alone | implies bulk mode |
  | `--resume` or `--resume <id>` with no matching unfinished issue run | error: `no unfinished issue run '<id>'; unfinished runs: <ids or none>` |
  | `--repo` with `--resume` | error: a resumed run keeps its recorded options |
  | `--limit` outside 1 to 100, `--scan` outside 1 to 1000, or `--scan` below `--limit` | error naming the allowed range |
  | `--search` containing `repo:`, `org:`, `user:`, `is:pr`, `type:pr`, `is:closed`, `is:merged`, `is:open`, `state:`, `is:issue` or `sort:`, including negated forms such as `-is:open` | error: the repository comes from `--repo`, and state, type and order are fixed |
- **FR-003**: The existing single-issue `issue <number>` behavior MUST remain unchanged.

**Selection**

- **FR-004**: Candidates MUST be open issues of the target repository matching the search, regardless of author, ordered by creation time, newest first. Selection MUST always restrict the search to open issues itself, so pull requests and closed issues never count as scanned candidates.
- **FR-005**: An issue MUST be skipped when a comment by a maintainer or a bot account carries the cc-review assessment marker (reason "already assessed"). The marker in comments by other users is ignored, so pasting it cannot suppress an assessment.
- **FR-006**: An issue MUST be skipped when any comment comes from a user, other than the issue author, whose association with the repository is owner, member or collaborator (reason "maintainer replied"). Comments from bots, the issue author's own comments, and labels or assignments without a comment do not count as maintainer replies.
- **FR-007**: A pull request references an issue when it links it with a closing keyword or cross-references it. An issue MUST be skipped when an open or merged pull request references it and that pull request was opened by a maintainer, or a maintainer reviewed or commented on it (reason "maintainer PR #M"). Bot accounts never count as maintainers.
- **FR-008**: An issue referenced only by pull requests from non-maintainers without maintainer activity, or only by pull requests closed without merging (whoever opened or reviewed them), MUST stay eligible, with those pull requests and their states recorded.
- **FR-009**: Issues opened by maintainers MUST be eligible under the same skip rules as any other issue.
- **FR-010**: Selection MUST continue to older candidates until the batch limit is met, candidates are exhausted, or the scan ceiling is reached, and MUST record the number scanned and whether the ceiling was reached.
- **FR-011**: Selection MUST record every skipped issue with its reason, and the result MUST be reproducible from the same repository data without model involvement.
- **FR-011b**: When an issue's comments, timeline, or a linked pull request's reviews or comments exceed what one selection query returns, the issue MUST be skipped with reason "history too long to verify" rather than selected on incomplete evidence.
- **FR-011a**: A selection failure (rate limit, network or API error) MUST stop the command with an actionable error and create no run; it MUST never be reported as an empty batch.

**Assessment**

- **FR-012**: Each selected issue MUST be assessed in a fresh context containing only that issue's collected data and the project context, applying the same need-and-fit judgment, assessment fields, example gate, and maintainer voice as the single-issue command. When collecting or assessing an issue fails, the issue MUST be recorded as "assessment failed" with the reason, left out of the approval pass, and listed in the report; the other issues continue.
- **FR-013**: Each assessment MUST additionally state whether the issue is fix-eligible: recommendation Pursue, the problem confirmed in the code or a clearly bounded change, and an estimated change within the small bound: at most 3 changed non-test files and at most 100 added plus removed lines in them, plus at most 300 added plus removed lines in test files. Test files are files under a `test/`, `tests/`, `spec/` or `__tests__/` directory, or named `*_test.*`, `test_*.*`, `*.test.*` or `*.spec.*`. Every assessment MUST record the code-confirmation and size estimate regardless of its recommendation, so fix eligibility can be recomputed after an edit.
- **FR-014**: When an open non-maintainer pull request is linked, the assessment MUST name it with its link. Closed or merged linked pull requests may be mentioned but are not required.
- **FR-015**: Issue titles, bodies and comments MUST be treated as untrusted data in every step, including fixes; embedded instructions are never followed and are flagged in the assessment.

**Approval and posting**

- **FR-016**: The approval pass MUST start only after every selected issue has been assessed, MUST present issues one at a time in selection order, showing the complete rendered comment exactly as it would be posted, and accept post, edit or skip. An edit takes the maintainer's described change or replacement text, redrafts and re-renders the reply through the same validation, and shows it in full again. When an edit changes the recommendation, the label and fix eligibility MUST be recomputed from the new recommendation before the comment is shown again.
- **FR-016a**: An approved reply MUST be posted immediately after its approval, and the post result MUST be recorded before the next issue is presented.
- **FR-017**: For fix-eligible issues the approval pass MUST offer "fix it" or "leave it" independently of the post decision. For issues with one or more open non-maintainer linked pull requests it MUST offer a single "review linked PRs" choice (naming each pull request) instead of "fix it"; closed or merged linked pull requests are mentioned in the assessment but never handed to review.
- **FR-018**: Posting MUST add exactly the approved rendered comment and the label mapped to the recommendation (using the project's CI label mapping when configured, otherwise the bundled defaults), and MUST NOT close, assign, or otherwise change the issue.
- **FR-019**: Before posting, the issue MUST be re-checked against the skip rules and its open state; posting is withheld with a stated reason when it no longer qualifies. A withheld post also abandons a chosen fix that has not been pushed yet, because the issue was closed or answered in the meantime.
- **FR-020**: A missing recommendation label MUST NOT block posting the comment and MUST NOT be created automatically; the report names it.
- **FR-020a**: A failed post (comment or label) MUST be recorded for that issue and shown to the maintainer immediately; the run continues with the next issue, and a resumed run retries only posts whose comment was not confirmed as published. On resume, a comment carrying this run's marker counts as posted (not withheld), and a label that failed to apply is retried.

**Fixes**

- **FR-021**: Fix options MUST be offered only when the invoking checkout is verified to be the target repository (as the single-issue command verifies its matching project root) and the maintainer can push to the target repository; otherwise the batch states once why fixes are unavailable.
- **FR-022**: Chosen fixes MUST run after the approval pass, one at a time, each in a fresh context and its own worktree created from the current default branch tip, never touching the maintainer's checkout, branch, or index.
- **FR-022a**: A fix worker MUST only read the project and edit files inside its worktree, and run nothing; it MUST make no network calls, push nothing, and open nothing. Pushing and opening the draft pull request are done afterwards by the deterministic helper, only for a fix within the small bound.
- **FR-023**: A fix worker MUST stop without publishing when it cannot produce a fix or expects to exceed the small bound, and the reason MUST be recorded. After the worker stops, the deterministic helper MUST measure the worktree change against the small bound of FR-013 and abandon the fix, without committing or pushing, when it is exceeded.
- **FR-024**: Fixes MUST NOT run project tests, builds, or other project code on the maintainer's machine, and the commit MUST be created without running the repository's git hooks. The pull request body MUST state that tests were not run locally and are left to the repository's checks on the pull request.
- **FR-025**: For a completed fix within the bound, the helper MUST create one commit under the maintainer's git identity with a conventional-commit message derived from the issue (type `fix` for bugs, `feat` for features, `chore` otherwise), push a new branch, and open a draft pull request under the maintainer's account whose body contains "Fixes #N", a sanitized short summary of the change, and the note of FR-024. Branches that exist locally or remotely and are not recorded by this run MUST NOT be overwritten.
- **FR-025a**: Commit, push and pull request creation MUST be recorded as separate steps. On resume, a pushed branch without a recorded pull request only gets its pull request opened, after confirming no open pull request for that branch already exists.
- **FR-026**: Fix worktrees and their local fix branches MUST be removed after the pull request is opened or the fix is abandoned.

**Handoff, report and state**

- **FR-027**: "Review linked PRs" choices MUST be handed to `review --bulk --prs <list>` as one explicit list after the fix pass, or printed as the exact command where the harness cannot chain commands.
- **FR-028**: The final report MUST list per issue: posted, post failed (with reason), label missing, skipped by maintainer, withheld with reason, assessment failed (with reason), draft pull request link, pull request pending (pushed, pull request not yet opened), pull requests handed to review, or fix abandoned with reason; plus the selection coverage of FR-010 and FR-011.
- **FR-029**: Run state MUST be durable across sessions so that `--resume` continues an unfinished run: stored assessments are reused (only issues without one are assessed), recorded decisions are kept, confirmed posts are never repeated, and fixes that recorded a pull request never run again. Starting a new run while an unfinished one exists marks the old run abandoned.
- **FR-030**: Argument validation, selection, skip rules, paging, run state, loop control, posting, re-checks, branch and pull request creation, and report counts MUST be performed by bundled deterministic helpers that can be tested with fixtures and without a model. The command prompt MUST limit itself to assessment, drafting, fixing, and conversation with the maintainer.
- **FR-031**: Helpers shared with selection or run state MUST not assume pull requests as the item kind, so that the later bulk runner refactor (brainstorm #18) can adopt them.
- **FR-032**: Where the harness supports subagents, each assessment and each fix MUST run in its own subagent; otherwise the command MUST degrade to sequential inline processing with a stated warning.

### Key Entities

- **Candidate issue**: An open issue matching the search, with its author association, comments' author associations, assessment markers, and referencing pull requests.
- **Skip record**: An issue number plus a skip reason (already assessed, maintainer replied, maintainer PR #M, history too long to verify).
- **Batch run**: One bulk invocation with its arguments, selection result, coverage counts, per-issue state, status (running, finished, abandoned), and creation time; resumable by run id.
- **Issue item state**: Per selected issue: assessment or assessment failure, rendered comment, fix eligibility, linked pull requests with their state and author role, decisions (post/edit/skip, fix/leave/review linked PRs), post result (comment and label separately), fix result.
- **Fix result**: Branch name, recorded steps (committed, pushed, pull request opened), draft pull request link or abandonment reason, measured change size.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A maintainer processes a batch of 10 untouched issues without typing any issue number, with exactly one decision prompt per issue (covering post, edit or skip together with any fix or review choice) plus one per requested edit.
- **SC-002**: 100% of posted comments are exactly the text the maintainer saw and approved, and no comment is posted without an approval.
- **SC-003**: 0 issues in a batch have a prior cc-review assessment, a maintainer reply, or a maintainer-owned linked pull request at selection time, verified against fixtures covering each skip category.
- **SC-004**: Every candidate scanned appears in the report as selected or skipped with a reason; the sum of selected and skipped equals the scanned count.
- **SC-005**: When enough untouched issues exist within the scan ceiling, the batch is filled to the limit in 100% of fixture runs, regardless of how many candidates are skipped.
- **SC-006**: The maintainer's checkout (current branch, index, tracked and untracked files) and its local branch list are identical before and after a run that includes fixes.
- **SC-007**: Every fix choice ends as either one draft pull request referencing the issue or a recorded abandonment reason; resuming a run never produces a second comment or a second pull request for the same issue.
- **SC-008**: Selection, skip rules, paging, and report counts are covered by automated tests that run without network access or a model.

## Assumptions

- `--search` uses the repository's issue search syntax, so labels and keywords are expressed as in `review --bulk --search`; no separate `--label` or `--keyword` flags in this version.
- "Maintainer" means the author association owner, member or collaborator as recorded by the hosting service on each comment and pull request; contributors without those roles count as non-maintainers.
- The scan ceiling defaults to 100 candidates and is configurable per run with `--scan` (1 to 1000).
- The small bound for fixes (at most 3 changed non-test files, at most 100 added plus removed lines in them, at most 300 lines in test files) is an estimate at assessment time and a limit the deterministic helper enforces after the fix. Test files have a separate, larger cap, so fixes are not discouraged from adding tests.
- Run state and fix worktrees live in a per-user cc-review state directory keyed by repository, never inside the checkout, so workers have no reason to write there. Without a local clone of the target repository fixes are not offered.
- Assessment and fix workers have file-write access as harness subagents do; the helpers detect changes to run state and to the checkout, and the command warns before the fix pass that a fix worker can write files. A full sandbox is out of scope.
- One session at a time works on a run: a run lock held by the active session expires after 30 minutes without activity.
- The maintainer's own git filters (for example git-lfs) run during fix steps as in any git use; filters added by a worker are detected and abort the fix.
- A fix whose change contains a binary file is abandoned.
- `review --bulk` and `issue --resume` take no `--repo`, so handoff and resume for another repository run from a checkout of that repository; the output names the repository (follow-up).
- Fix branches are named `cc-review/fix-issue-<N>` and pull request titles follow conventional commit style derived from the issue.
- Only GitHub.com repositories are supported, as with the single-issue command.
- Bulk issue assessment is interactive only; unattended bulk issue assessment stays with CI.
- Out of scope: the inbox pointer to new issues (brainstorm #17 approach C), moving review and triage bulk onto a shared runner (brainstorm #18), and applying the paging rule to `review --bulk` selection.
