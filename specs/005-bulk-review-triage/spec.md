# Feature Specification: Bulk Review and Bulk Triage

**Feature Branch**: `005-bulk-review-triage`

**Created**: 2026-10-25

**Status**: Draft

**Input**: User description: "Bulk review and bulk triage across PRs. `--bulk` flag on the existing review and triage commands, backed by one shared orchestrator in core. Git worktree and isolated context per PR, resumable state document. PR selection: review-requested for the user and not yet reviewed at the current head (default), `--all-open`, `--search '<query>'`; triage selects the user's own open PRs with unresolved threads and commits and pushes fixes per PR. Deferred mode (default) writes per-PR results to `.cc-review/bulk/<run-id>/` and presents one consolidated decision table; `--unattended` applies a fixed policy; `--resume [<run-id>]` continues an interrupted deferred run and re-analyzes PRs whose head moved. The user's working tree is never touched; one PR failing does not stop the run." Derived from brainstorm `brainstorm/06-bulk-review-triage.md`.

## Clarifications

### Session 2026-10-25

- Q: Does "requested reviewer" include review requests sent to a team the user belongs to? → A: Yes. Selection follows the hosting service's own "review requested from me" semantics, which include team requests for teams the user is a member of.
- Q: When the user picks "apply fixes" for their own PR in bulk review, when does the fix loop run? → A: After the decision step, one PR at a time, in that PR's kept isolated checkout. Fixes are committed and pushed after the head check (FR-030); a review is not posted for that PR unless the user also picked "post review".
- Q: In unattended bulk review, is the posted review a blocking "request changes" review on other people's PRs? → A: No. Unattended mode always posts a non-blocking comment review; only deferred mode, where the user decides per PR, uses the single-PR posting rules (which may request changes on others' PRs).
- Q: What happens when a new bulk run starts while an unfinished run of the same command exists in the repository? → A: Deferred mode asks the user to resume it, abandon it (marked abandoned, state kept), or cancel. Unattended mode stops with an error naming the unfinished run id. No liveness detection of other sessions is attempted.
- Q: How is "already reviewed by cc-review at the current head" decided when a PR has several cc-review reviews? → A: The PR counts as reviewed at head when any review carrying the cc-review marker was submitted against the PR's current head commit. Reviews against older commits do not count.
- Q: Should the default selector also pick PRs the user already reviewed when new commits arrive (the direct request disappears after reviewing)? → A: Yes, PRs with a cc-review review by the user at an older head are selected again (FR-004).
- Q: How are PRs with zero findings remembered so they are not re-analyzed every run? → A: A short no-findings marker review is posted (FR-021a). Skipped PRs get no marker and come back next run.
- Q: What does "post review" mean in the bulk decision table, given single-PR posting asks per finding? → A: Post all new findings; an optional per-PR "review findings" choice opens the per-finding flow inside the same decision step (FR-018).
- Q: How does "apply fixes" re-review fixed code in bulk mode? → A: The coordinator drives the fix rounds: a fix worker applies, tests and commits one round, then the coordinator re-dispatches the reviewers on the changed files, up to the configured maximum rounds. This matches single-PR behavior.
- Q: What does `--bulk --resume --unattended` do when no unfinished run exists? → A: It starts a new run and honors selector flags given alongside. In deferred mode `--resume` reports "no unfinished run" and stops.
- Q: Is CI checked after a bulk triage push? → A: No. The summary states that CI was not checked and suggests single-PR triage for CI repair.
- Q: May posted reviews now carry the reviewed commit in single-PR mode too? → A: Yes, as a documented exception to FR-036.
- Q: What happens when a PR's head moves after its analysis but before the decision step? → A: The PR is analyzed again once, in the same run, before the decision table. If its head moves again before the decision, it is marked stale (re-run needed). The number of such re-analyses is recorded per PR in the state.
- Q: Is a failed PR retried on every resume? → A: No. A PR is retried until its attempts have failed 3 times, counted across resumes and recorded in the state; after that it stays failed, is not retried, and no longer keeps the run unfinished.
- Q: May command reviewers (external CLI tools) run inside the checkout of a PR from a fork, where they could load the PR's own agent instruction files? → A: Not by default. In bulk review and in the isolated single-PR checkout, command reviewers are skipped for cross-repository PRs and reported as "skipped (untrusted checkout)"; a per-reviewer config opt-in (`allow_untrusted_checkout.<name>: true`) lets one run. Prompt reviewers still run.
- Q: Whose cc-review marker reviews count when deciding "reviewed at head" and the re-review set? → A: Every author's except the PR author's own: a marker review posted by the PR's author is ignored, so an author cannot opt their PR out of bulk review. Markers by anyone else still count. Follow-up: the user's own marker on the user's own PR counts too, so `--all-open` does not re-review the user's PRs on every run.
- Q: Is `--spec` accepted for bulk triage? → A: No. Like bulk review, bulk triage rejects it with "--spec is not supported with --bulk", since a spec belongs to one change.
- Q: Can an interrupted run skip the rest of its analysis? → A: Yes, on resume in deferred mode: finish the interrupted PR and decide, or decide right away; the PRs not reached stay untouched for a later run (FR-028a).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Review My Review Queue in One Run (Priority: P1)

A developer has been asked to review six pull requests in a repository. Instead of checking out each branch and running `/review --pr <n>` six times, they run `/review --bulk`. cc-review finds the open PRs where the developer is a requested reviewer and that cc-review has not yet reviewed at their current head commit, reviews each one against that PR's own code without touching the developer's working tree, and records the results as it goes. When all PRs are analyzed, the developer sees one table: one row per PR with its title, finding counts by severity, and a proposed action. They pick per PR whether to post the review or skip it, in a single pass, and cc-review posts the chosen reviews.

**Why this priority**: This is the core use case named by the user ("review all un-reviewed PRs"). It delivers value on its own without triage, resume, or unattended mode.

**Independent Test**: In a test repository with three open PRs requesting the user's review (one already reviewed by cc-review at its current head), run `/review --bulk`, confirm exactly two PRs are analyzed, the user's checkout and branch are unchanged afterwards, and choosing "post" for one PR and "skip" for the other posts exactly one review.

**Acceptance Scenarios**:

1. **Given** open PRs #10, #11, #12 request the user's review and #12 has a cc-review review posted against its current head commit, **When** the user runs `/review --bulk`, **Then** #10 and #11 are selected and #12 is listed as "already reviewed at head" and not analyzed.
2. **Given** a selected PR whose branch is not checked out locally, **When** it is analyzed, **Then** every reviewer reads that PR's head version of each changed file, not the version in the user's working tree.
3. **Given** the user's working tree has uncommitted changes and is on branch `feature-x`, **When** a bulk run completes, **Then** the working tree, index, current branch, and uncommitted changes are exactly as before.
4. **Given** all selected PRs are analyzed, **When** the decision step starts, **Then** one consolidated table shows every PR with number, title, author, Critical/Important/Minor/Notable counts, status, and the proposed action, and the user decides for all PRs in one interaction.
5. **Given** the user chose "post" for #10 and "skip" for #11, **When** the decision is applied, **Then** a review with all new findings is posted on #10 (review type and inline placement as in single-PR review, without per-finding prompts), nothing is posted on #11, and the summary lists both outcomes.
6. **Given** a PR that cc-review reviewed at an older commit and that has new commits since, **When** the user runs `/review --bulk`, **Then** that PR is selected again.

---

### User Story 2 - Triage All My PRs with Open Comments (Priority: P1)

An author has four open PRs, three of which collected bot comments (CodeRabbit, Copilot) and one human comment overnight. They run `/triage --bulk`. cc-review finds their own open PRs that have unresolved review threads, triages each one in an isolated checkout of that PR's branch (assess every bot thread, prepare fixes, draft replies), and records the results. In the consolidated decision table the author approves the prepared changes per PR; for approved PRs cc-review commits, pushes to the PR branch, posts replies, and resolves handled threads, exactly as single-PR triage does. Human comments are collected per PR and presented for the author's decision in the same pass.

**Why this priority**: The user asked for bulk triage alongside bulk review; for authors with several open PRs it removes the most repetitive part of the review cycle.

**Independent Test**: In a test repository with two of the user's PRs carrying unresolved bot threads and one with none, run `/triage --bulk`, confirm only the two PRs are selected, approve one and skip the other, and verify the approved PR received a push plus replies while the skipped PR's branch and threads are unchanged.

**Acceptance Scenarios**:

1. **Given** the user authors open PRs #20 (3 unresolved threads), #21 (0 unresolved threads), and #22 (1 unresolved thread), **When** the user runs `/triage --bulk`, **Then** #20 and #22 are selected and #21 is listed as "no open threads".
2. **Given** a selected PR, **When** it is triaged in deferred mode, **Then** fixes are prepared and committed only in that PR's isolated checkout, nothing is pushed, and no reply is posted until the user approves that PR in the decision step.
3. **Given** the user approves #20 in the decision step, **When** the decision is applied, **Then** the prepared commit is pushed to #20's branch, replies are posted, and handled threads are resolved with the same rules as single-PR triage.
4. **Given** #22 has one unresolved human comment, **When** the decision step runs, **Then** the human comment is shown with the drafted response options from single-PR triage, and the user's choice is applied only for that comment.
5. **Given** the remote branch of an approved PR moved after it was analyzed, **When** the push is attempted, **Then** cc-review does not force-push; that PR is marked "stale, re-run needed" and no replies are posted for it.

---

### User Story 3 - Resume an Interrupted Bulk Run (Priority: P2)

Halfway through a bulk review of eight PRs the developer's session ends (laptop closed, context exhausted, network loss). They start a new session and run `/review --bulk --resume`. cc-review loads the most recent unfinished bulk run, keeps the results of PRs that were already analyzed at an unchanged head commit, re-analyzes PRs whose head moved in the meantime, analyzes the PRs it had not reached yet, and then shows the decision table for all eight.

**Why this priority**: The user explicitly asked that deferred mode stores intermediate results in a document so an interrupted run can be picked up again. Without it a long bulk run is all-or-nothing.

**Independent Test**: Start a bulk review of three PRs, stop it after the first PR is recorded as analyzed, push a new commit to the second PR, resume, and verify the first PR is not re-analyzed, the second and third are analyzed, and the decision table shows all three.

**Acceptance Scenarios**:

1. **Given** a bulk run with PRs A (analyzed at head H1), B (pending), C (pending), and A's head is still H1, **When** the user runs `--bulk --resume`, **Then** A is not re-analyzed and B and C are analyzed.
2. **Given** PR A was analyzed at head H1 and its head is now H2, **When** the run is resumed, **Then** A's earlier result is discarded and A is analyzed again at H2.
3. **Given** two unfinished bulk runs exist, **When** the user runs `--bulk --resume` without a run id, **Then** the most recently updated unfinished run of the same command (review or triage) is resumed and its id is printed.
4. **Given** a run was interrupted during the decision step after some PRs were already actioned, **When** it is resumed, **Then** actioned PRs are not posted or pushed again and only undecided PRs are offered in the decision table.
5. **Given** the user runs `--bulk --resume <run-id>` with an unknown id, **Then** cc-review stops with an error that lists the known unfinished run ids.
6. **Given** a deferred run was interrupted while PR B was being analyzed, with PR A analyzed and PRs C and D not reached, **When** the user resumes it, **Then** they can continue the analysis, finish B and then decide, or decide right away; with either shortcut C and D (and B for "decide right away") are left as not analyzed, nothing is posted on them, and a later bulk run selects them again.
7. **Given** a bulk run in progress, **When** the user opens its state document, **Then** they can read which PRs are done, pending, failed, or actioned, with each PR's finding counts or triage assessment, without any tool.

---

### User Story 4 - Unattended Bulk Run (Priority: P2)

A team lead wants a scheduled job (or a long-running session they leave alone) that reviews every PR waiting for them and posts the findings, without any prompts. They run `/review --bulk --unattended`. cc-review applies a fixed, documented policy per PR and ends with a summary report listing what it did for each PR.

**Why this priority**: The user asked for a switch between deferred and unattended operation. Unattended mode makes bulk usable in automation, but deferred mode alone already covers the interactive case.

**Independent Test**: Run `/review --bulk --unattended` against two selected PRs and verify no prompt appears, each PR gets a posted review, no code is changed on either PR branch, and a summary lists both PRs with their outcome.

**Acceptance Scenarios**:

1. **Given** `/review --bulk --unattended`, **When** the run completes, **Then** for every successfully analyzed PR with findings, the findings are posted as a non-blocking comment review, PRs with zero findings get the no-findings marker review (FR-021a), and no code is changed on any PR branch.
2. **Given** `/triage --bulk --unattended`, **When** the run completes, **Then** for every selected PR valid bot fixes are committed and pushed, replies are posted, and handled bot threads are resolved; human comments are left untouched and listed in the summary as needing attention.
3. **Given** unattended mode, **When** any step would normally ask the user something (PR choice, next-step menu, human comment approval, idea-inbox capture), **Then** the documented unattended default is applied and no prompt is shown.
4. **Given** unattended mode, **When** the run ends, **Then** a summary report is written to the run's state directory and printed, listing each PR with outcome (posted, pushed, skipped, failed) and a reason for every skip or failure.

---

### User Story 5 - Choose What "Un-reviewed" Means (Priority: P3)

A repository maintainer is not listed as a requested reviewer on most PRs but wants every open PR reviewed. They run `/review --bulk --all-open`. Another user wants only PRs with a certain label and runs `/review --bulk --search 'label:needs-review'`. In both cases cc-review still skips PRs it already reviewed at their current head.

**Why this priority**: The default selection covers the stated use case; the alternative selectors broaden it for maintainers and power users.

**Independent Test**: With five open PRs, one requesting the user's review and two carrying a label, verify the default selects one PR, `--all-open` selects all five (minus any already reviewed at head), and `--search 'label:<x>'` selects the two labelled PRs.

**Acceptance Scenarios**:

1. **Given** `--all-open`, **When** PRs are selected, **Then** every open, non-draft PR in the repository not yet reviewed by cc-review at its current head is selected.
2. **Given** `--search '<query>'`, **When** PRs are selected, **Then** the query is applied as a pull-request search restricted to the current repository and open PRs, and the "already reviewed at head" filter is still applied.
3. **Given** both `--all-open` and `--search` are passed, **Then** cc-review stops with an error saying the selectors are mutually exclusive.
4. **Given** `/triage --bulk --search '<query>'`, **When** PRs are selected, **Then** the query result is further restricted to PRs authored by the user that have unresolved threads.

---

### User Story 6 - Single-PR Review of a PR Not Checked Out (Priority: P3)

A developer runs `/review --pr 42` while on an unrelated branch. Today the reviewers read the files from the developer's working tree, so they review the wrong code. With this feature, when the requested PR's head is not what is checked out, the review runs against an isolated checkout of PR #42, the same way bulk mode does.

**Why this priority**: It is a latent correctness bug that bulk mode exposes and that the bulk isolation fixes as a side effect; it matters less than the bulk flows themselves.

**Independent Test**: On a branch whose version of a file differs from PR #42's version, run `/review --pr 42` with a reviewer that reports a marker present only in the PR's version, and verify the marker finding appears.

**Acceptance Scenarios**:

1. **Given** the current branch is not PR #42's head branch, **When** `/review --pr 42` runs, **Then** reviewers read PR #42's head version of each changed file and the user's working tree is unchanged.
2. **Given** the current branch is PR #42's head branch (whether ahead of, behind, or equal to the remote head, with or without uncommitted changes), **When** `/review --pr 42` runs, **Then** behavior is unchanged from today (local files are reviewed, fix loop may edit them).
3. **Given** `/review --pr 42` ran in an isolated checkout, **When** the next-step menu is shown, **Then** fix options are offered only if the user authors PR #42, and applied fixes are committed and pushed to the PR branch only after the user picks a fix option.

---

### Edge Cases

- **No PRs selected**: The run reports "No PRs matched" with the selector used and how many PRs were excluded as already reviewed at head (review) or without open threads (triage), and exits without creating a state directory.
- **More PRs than the limit**: Selection is capped at `--limit` (default 10). PRs are processed oldest-updated first; the excess PRs are listed by number as "not processed (limit)" so the user can run again.
- **PR checkout fails** (branch deleted, fork not reachable, merge state unknown): That PR is marked failed with the reason; the run continues with the next PR.
- **Reviewer or triage step fails for one PR**: That PR is marked failed with the reason and its isolated checkout is kept for inspection; the run continues.
- **PR closed or merged between selection and decision**: In the decision step the PR is shown as "closed" and no action is offered for it.
- **PR head moves between analysis and decision**: The PR is analyzed again once in the same run before the decision table; a second move before the decision marks it "stale, re-run needed" with no action offered.
- **PR that keeps failing**: Each failed attempt is counted across resumes; after 3 failed attempts the PR stays failed with its reason, is not retried, and the run can finish.
- **Draft PRs**: Excluded by default from all selectors; included only when the `--search` query contains `draft:true` or `is:draft`.
- **`--search` with repository or state qualifiers** (`repo:`, `org:`, `is:closed`, `is:merged`): Rejected with an error, since bulk mode always works on open PRs of the current repository.
- **PR state directory or kept checkout missing on resume** (for example, temporary files cleared): The affected PR is re-analyzed instead of acting on missing prepared work.
- **User's own PR branch is checked out locally** (bulk triage, or bulk review "apply fixes"): The isolated checkout uses the PR's remote head without taking over the local branch; after a push the summary tells the user their local branch is behind. If the local branch has commits not on the remote, the PR is marked "local commits not pushed" and only reply posting (triage) or review posting (review) is offered for it.
- **PR from a fork** (bulk triage): The user may not be able to push to the fork branch; the PR is marked "cannot push" in the decision step and only reply posting is offered.
- **Not authenticated / not a GitHub repository**: The run stops before selecting any PR with the same error the single-PR commands give.
- **Unfinished bulk run of the same command exists** when a new run starts: deferred mode offers resume, abandon (state kept, marked abandoned), or cancel; unattended mode stops with an error naming the unfinished run id.
- **Project reviewers added or edited by a PR under review**: Ignored for that PR's review, as in single-PR review, so an untrusted PR cannot inject reviewer prompts.
- **PR from a fork** (bulk review, or the isolated single-PR checkout): Command reviewers are skipped as "skipped (untrusted checkout)" unless the config opts them in (FR-011a); prompt reviewers run as usual.
- **State document edited or corrupted by hand**: `--resume` validates the machine-readable state; if invalid it stops with an error naming the file and does not overwrite it.
- **`--bulk` combined with `--pr`**: Rejected with an error, since `--pr` names a single PR.
- **`--resume` without `--bulk`**: Treated as `--bulk --resume`.
- **Rate limiting by an external reviewer for one PR**: That PR is marked failed with the rate-limit reason and the run continues.
- **Rate limiting by the hosting service** (affects every remaining PR): The run pauses instead of failing the remaining PRs; its state stays unfinished and the summary tells the user to continue with `--resume` later. Scheduled unattended jobs recover by running `--bulk --resume --unattended`, which continues the paused run or, when no unfinished run exists, starts a new one.

## Requirements *(mandatory)*

### Functional Requirements

**Invocation**

- **FR-001**: The `review` and `triage` commands MUST accept a `--bulk` flag that switches them from single-PR operation to bulk operation; no new user-facing command is added.
- **FR-002**: Bulk mode MUST accept these options: `--all-open` (review only), `--search '<query>'`, `--limit <n>` (positive integer, default 10), `--unattended`, and `--resume [<run-id>]`. Existing flags MUST be handled as follows:

  | Flag or setting | Bulk review | Bulk triage |
  |---|---|---|
  | `--config`, `--profile` | applied to every PR | applied to every PR |
  | reviewer selection (`--only`, `--no-<name>`, `--external`, `--no-external`), `--no-meta-review`, `--max-rounds`, `--hints`, `--sequential`, `--parallel` | applied to every PR | n/a |
  | `--no-fix` | "apply fixes" is not offered | n/a |
  | `--spec` | rejected (a spec belongs to one change) | rejected (a spec belongs to one change) |
  | `--output` | rejected (reports go to the run's state directory, FR-026) | n/a |
  | `--pr` | rejected | rejected |
  | `--idea-inbox` | n/a | capture is offered once, after the decision step, for all applied PRs (deferred); skipped (unattended) |
  | `--no-coverage-fix` | n/a | accepted, no effect (coverage remediation never runs in bulk) |
  | config `interactive: false` | treated as `--unattended` | treated as `--unattended` |

- **FR-003**: `--bulk` MUST be rejected together with `--pr`, `--all-open` MUST be rejected together with `--search`, `--all-open` MUST be rejected for triage, and a `--limit` that is not a positive integer MUST be rejected, each with an error naming the problem.

**Selection**

- **FR-004**: Default bulk review selection MUST be open, non-draft PRs in the current repository where either a review is requested from the user (directly or through a team the user belongs to), or the user previously submitted a cc-review review at an older commit and the PR has new commits since (the hosting service drops a direct request once the user reviews, so re-reviews would otherwise never be selected).
- **FR-005**: `--all-open` MUST select all open, non-draft PRs in the current repository; `--search` MUST select the open PRs in the current repository matching the given query.
- **FR-006**: Bulk review MUST exclude any selected PR that has at least one review carrying the cc-review marker submitted against its current head commit by someone other than the PR's author, and MUST report the excluded PRs and the reason. Reviews against older commits MUST NOT count, and neither MUST marker reviews by the PR's author (here and for the re-reviews of FR-004), except when the PR's author is the user running the bulk review.
- **FR-007**: Bulk triage MUST select open PRs authored by the user (further restricted by `--search` when given) that have at least one unresolved review thread, and MUST report authored PRs excluded for having none.
- **FR-008**: Selection MUST cap the number of processed PRs at `--limit`, processing least-recently-updated PRs first, and MUST list the PRs left out by the cap.

**Isolation**

- **FR-009**: Each PR MUST be analyzed in its own isolated checkout of that PR's head commit. The user's working tree, index, current branch, stash, and uncommitted changes MUST be unchanged by a bulk run, apart from the version-control-ignored `.cc-review/bulk/` directory (FR-033).
- **FR-010**: The coordinating session MUST retain only a bounded per-PR summary (status, counts, report location) once a PR's analysis is finished; full findings and reviewer output MUST live in files, so the number of PRs per run is not limited by one session's context. The mechanism that achieves this is a planning decision.
- **FR-011**: Configuration, review hints, and reviewer enablement MUST be resolved once from the repository the command was invoked in and applied to every PR. Project-layer reviewers changed by a PR MUST be ignored for that PR, as in single-PR review.
- **FR-011a**: Command reviewers (external CLI tools) MUST NOT run in the checkout of a cross-repository (fork) PR, in bulk review and in the isolated single-PR checkout (FR-035), unless the configuration opts the reviewer in with `allow_untrusted_checkout.<name>: true` (a boolean; invalid values are dropped with a warning). A reviewer skipped this way MUST be reported as "skipped (untrusted checkout)". Prompt reviewers MUST still run.
- **FR-012**: An isolated checkout MUST be removed after its PR is fully handled (actioned or skipped). It MUST be kept until the PR is decided when the PR has prepared but unapplied changes or when "apply fixes" is offered for it, and kept after a failure for inspection; the summary MUST name kept checkouts.

**Per-PR processing**

- **FR-013**: Per PR, bulk review MUST run the same review pipeline as single-PR review (discovery, dispatch, merge, meta-review, report), stopping before the next-step decision. The per-PR findings report MUST be written to `.cc-review/bulk/<run-id>/pr-<n>/`, and the decision table MUST show its path so the user can read full findings before deciding.
- **FR-014**: Per PR, bulk triage MUST run the same triage pipeline as single-PR triage for bot threads (assess, prepare fixes, draft replies) and MUST collect human comments with their drafted responses, stopping before pushing, posting, or resolving anything. Every triage step that posts, resolves, or pushes during a single-PR run (bot replies, thread resolution including stale handled threads, cc-review thread replies and resolution, CI-repair commits after push) MUST instead be recorded as a prepared action that runs only on "apply" (deferred) or by policy (unattended). CI checks and CI repair after push MUST NOT run in bulk mode; the summary MUST state that CI was not checked for pushed PRs and suggest single-PR triage for CI repair. Single-PR triage's mandatory status-bot cross-reference and coverage remediation steps MUST carry an explicit exception for bulk mode.
- **FR-014a**: Bulk triage MUST read and write the triage state of the repository the command was invoked in, not a state file inside the per-PR checkout.
- **FR-015**: A failure while processing one PR MUST mark only that PR as failed with a reason and MUST NOT stop processing of the remaining PRs.
- **FR-016**: PRs MUST be processed one after another.

**Deferred mode (default)**

- **FR-017**: In deferred mode no prompt MUST be shown while PRs are being analyzed.
- **FR-018**: After analysis, the user MUST be shown one consolidated decision table covering every PR in the run and MUST be able to decide the action for every PR in one interaction, plus "skip all" and "apply proposed actions" shortcuts. In bulk review, "post review" posts all new findings for that PR without per-finding prompts; a separate per-PR "review findings" choice opens the single-PR per-finding flow (accept, reject, edit) for that PR within the same decision step. Follow-up questions needed for edits (review findings, triage human-comment edits) belong to the decision step.
- **FR-019**: Actions offered per PR in bulk review MUST be "post review", "review findings" (FR-018), and "skip" for PRs with findings, and "post no-findings marker" and "skip" for PRs without; "apply fixes" MUST additionally be offered only for PRs authored by the user, alone or combined with "post review". Chosen fixes MUST run after the decision step, one PR at a time, in that PR's kept isolated checkout, and MUST be committed and pushed to the PR's branch subject to FR-030. When combined with "post review", only the findings that remain after fixing are posted.
- **FR-020**: Actions offered per PR in bulk triage MUST be "apply" (push prepared commits, post replies, resolve handled threads) and "skip", plus per human comment the same response choices as single-PR triage.
- **FR-021**: The proposed action shown per PR MUST be: review with findings → "post review"; review with zero findings → "post no-findings marker"; triage with prepared changes or replies → "apply"; failed or closed PR → no action.
- **FR-021a**: "Post no-findings marker" MUST post a short non-blocking comment review that carries the cc-review marker and states that no findings were reported at the reviewed commit, so later runs recognize the PR as reviewed at that head (FR-006). PRs the user chose to skip get no marker and are selected again by the next run.

**Unattended mode**

- **FR-022**: `--unattended` MUST complete the run without any prompt.
- **FR-023**: Unattended bulk review MUST post a non-blocking comment review for every successfully analyzed PR that has findings (never a "request changes" review), MUST post the no-findings marker (FR-021a) on PRs with zero findings, and MUST NOT change code on any PR branch.
- **FR-024**: Unattended bulk triage MUST apply each PR's prepared bot-thread changes (commit, push, reply, resolve), MUST leave human comments untouched, and MUST skip the idea-inbox capture prompt.
- **FR-025**: Unattended mode MUST record its policy decisions per PR in the state document like deferred mode, so an interrupted unattended run is resumable with `--resume` and resumes unattended.

**State and resume**

- **FR-026**: Every bulk run that selects at least one PR MUST have a run id and a state directory under `.cc-review/bulk/<run-id>/` containing a human-readable state document and a machine-readable state file, both updated after every PR status change and every completed sub-action.
- **FR-027**: The state MUST record the command, selector and options, each PR's number, title, author, head commit at analysis time, status (pending, analyzing, analyzed, applying, failed, stale, cannot-push, partially-applied, actioned, skipped, closed, not-analyzed), failure reason, the number of failed attempts (FR-028) and of re-analyses after a head move before the decision (FR-030), path to the per-PR report, finding counts or triage assessment, the decided action, and per completed sub-action its identifier: pushed commit, posted review id, and reply id per comment.
- **FR-028**: `--resume [<run-id>]` MUST continue the given run, or the most recently updated unfinished run of the same command when no id is given. It MUST keep results for PRs analyzed at an unchanged head, re-analyze PRs whose head moved or whose kept checkout or prepared commit is missing, analyze pending PRs, retry failed PRs until a PR's attempts have failed 3 times (counted across resumes and recorded in the state; such a PR then stays failed, is not retried, and counts as finished for the run), and never repeat a sub-action already recorded as done. Before re-posting a review or reply that is not recorded, it MUST check the PR for a review or reply this run already posted (by the run's cc-review marker or the triage reply records) and record it instead of posting again.
- **FR-028a**: When a deferred-mode run that stopped during its analysis is resumed, cc-review MUST offer to continue the analysis, to finish only the PR whose analysis was interrupted and then go to the decision step, or to go to the decision step right away. With either shortcut, every other PR not yet analyzed MUST become not analyzed for this run: nothing is posted or pushed for it, its checkout is removed, and it stays eligible for later bulk runs. Unattended runs MUST continue the analysis without asking.
- **FR-029**: A resumed run MUST use the options recorded in its state (selector, mode, reviewer flags); options passed alongside `--resume` other than `--bulk`, the run id, and `--unattended` matching the recorded mode MUST be rejected with an error. When no unfinished run of the command exists, `--resume --unattended` MUST start a new run using the other flags given, and deferred `--resume` MUST report "no unfinished run" and stop.
- **FR-030**: Before applying any decided action (post, push), the PR's current head MUST be compared with the expected head: the head recorded at analysis, or, once this run pushed to the PR, the last commit this run pushed (recorded before the push). If the head differs from the expected head, the action MUST NOT be applied and the PR MUST be marked "stale, re-run needed". A head that moved between a PR's analysis and the decision step MUST instead lead to one more analysis of that PR in the same run before the decision table; a second move before the decision MUST mark it "stale, re-run needed". On resume, a remote head equal to a prepared commit MUST be treated as that push having completed.
- **FR-031**: At most one unfinished bulk run per command and repository may exist at a time. Starting a new run while one exists MUST, in deferred mode, offer resume, abandon (mark abandoned, keep state), or cancel, and MUST, in unattended mode, stop with an error naming the unfinished run id.
- **FR-032**: State directories MUST be kept after a run finishes; a finished run MUST be marked finished in its state. cc-review MUST NOT delete them automatically.
- **FR-033**: When a bulk run creates `.cc-review/bulk/`, it MUST also create an ignore file inside it that excludes the whole directory from version control, so state and per-PR reports never show up as untracked changes in the user's repository.

**Reporting**

- **FR-034**: Every bulk run that selects at least one PR MUST end with a summary (printed and written to the state directory) listing every selected and excluded PR with its final outcome and reason.

**Single-PR fix**

- **FR-035**: Single-PR `review --pr <n>` MUST review PR #n's head code in an isolated checkout when the current branch is not PR #n's head branch, and MUST keep today's behavior (local files, including unpushed commits and uncommitted changes) when it is.

**Behavior preservation**

- **FR-036**: Running `review` or `triage` without `--bulk` (and, for review, with `--pr` pointing at the current checkout or without `--pr`) MUST behave exactly as before this feature, with one accepted exception: posted reviews now record the reviewed commit, so later runs can tell which head a review covered.

### Key Entities

- **Bulk Run**: One invocation of `--bulk`. Attributes: run id, command (review or triage), selector and options, mode (deferred or unattended), started and updated timestamps, overall status (selecting, analyzing, deciding, applying, paused, finished, abandoned).
- **PR Entry**: One PR within a run. Attributes: number, title, author, draft flag, head commit at analysis, status, failure reason, isolated checkout location, per-PR report location, finding counts (review) or triage assessment (triage), proposed action, decided action, action result.
- **Exclusion Record**: A PR considered but not selected, with the reason (already reviewed at head, no open threads, over limit, draft).
- **Human Comment Item** (triage only): A human review comment awaiting decision, with PR number, location, comment text, drafted response options, and the user's decision.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user with N PRs awaiting review gets all N reviewed and decided with one command invocation and one decision step (which may include follow-up questions only for PRs the user chooses to curate), instead of N invocations and N decision steps.
- **SC-002**: After any bulk run, including failed and interrupted runs, the user's working tree (excluding the ignored `.cc-review/bulk/` directory), branch, and uncommitted changes are identical to before the run in 100% of test cases.
- **SC-003**: Resuming an interrupted run never re-analyzes a PR whose head did not change and never repeats a post or push, verified across interruption points in every run phase.
- **SC-004**: A failure on one PR in a run of five leaves the other four processed and reported, in 100% of injected-failure test cases.
- **SC-005**: A bulk run of 10 PRs completes without the coordinating session running out of context.
- **SC-006**: A PR reviewed in bulk gets the same reviewer set, configuration source, and report structure as a single-PR review of the same PR head with the same configuration.
- **SC-007**: An unattended run completes with zero prompts in 100% of test cases, including runs with human comments, failures, and closed PRs.

## Assumptions

- The hosting platform is GitHub, accessed with the user's authenticated CLI, as for the existing single-PR commands. GitLab and other platforms are out of scope.
- "Reviewed by cc-review at the current head" is determined from reviews carrying the existing cc-review marker, the commit each review was posted against, and its author (the PR author's own markers are ignored); no marker format change is needed.
- Sequential processing (FR-016) is a deliberate first-version choice to stay within hosting-service and external-reviewer rate limits; parallel processing is out of scope.
- Bulk review never pushes to PRs the user does not author; fixing other people's PRs is out of scope.
- The default limit of 10 PRs is chosen to keep one run's wall-clock time and cost predictable; users raise it explicitly.
- Posting a short no-findings marker review is acceptable noise on the PR in exchange for not re-analyzing clean PRs on every run.
- The three harnesses (Claude Code, Codex, OpenCode) all receive the feature through the shared core command definitions; command shims need no changes beyond passing the new flags through.
- Triage loop mode, CI repair after push, and coverage remediation are not run in bulk mode; the user runs single-PR triage for those. The single-PR triage instructions that mark these steps as mandatory get an explicit bulk-mode exception (FR-014).
