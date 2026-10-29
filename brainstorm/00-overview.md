# Brainstorm Overview

Last updated: 2026-10-29

## Sessions

| # | Date | Topic | Status | Spec | Issue |
|---|------|-------|--------|------|-------|
| 01 | 2026-08-03 | pr-review-comments | spec-created | 001 | - |
| 02 | 2026-08-04 | config-system | active | - | - |
| 03 | 2026-08-04 | reviewer-abstraction | superseded (by #05 reviewer-plugins) | - | - |
| 04 | 2026-08-14 | meta-reviewer | active | - | - |
| 05 | 2026-10-13 | reviewer-plugins | active | - | - |
| 06 | 2026-10-25 | bulk-review-triage | active | - | - |
| 07 | 2026-10-26 | repository-inbox | active | - | [#4](https://github.com/rhuss/cc-review/issues/4) |
| 08 | 2026-10-27 | inbox-action-alignment | active | - | [#7](https://github.com/rhuss/cc-review/issues/7) |
| 09 | 2026-10-27 | incremental-review | active | - | [#8](https://github.com/rhuss/cc-review/issues/8) |
| 10 | 2026-10-28 | review-convergence | active | - | [#11](https://github.com/rhuss/cc-review/issues/11) |
| 11 | 2026-10-29 | issue-assessment | active | - | - |

## Open Threads

- How should the "what went well" agent interact with the existing 6 review agents? Is it a 7th agent, or a post-processing step that reads the diff independently? (from #01)
- Should the `reviewer` voice profile be shipped as a file in the cc-review plugin, or generated on first use via `prose:voice`? (from #01)
- What happens when the PR diff is too large for the GitHub review API's comment limit? Truncation strategy or split into multiple reviews? (from #01)
- Should the interactive local review support an "edit" action where the user can rewrite the comment text before posting? (from #01)
- Should `--profile` and `--config` be mutually exclusive, or should `--config` override `--profile` values? (from #02)
- Should the init skill support generating a GitHub Actions workflow file that uses cc-review? (from #02)
- Should the config support environment variable interpolation (e.g., `$CC_REVIEW_TOKEN`) for CI secrets? (from #02)
- How should config errors be reported: fail fast with all errors, or warn and use defaults for invalid keys? (from #02)
- Should the descriptor support multiple output formats (structured JSON vs delimited text vs free-form)? (from #03)
- Should there be a "test" subcommand that runs a reviewer's detection + auth check + sample invocation? (from #03)
- How should reviewer descriptors handle tools that post directly to the PR (like CodeRabbit's bot) vs tools that output to stdout? (from #03)
- Should the abstraction support internal agents too (unifying the dispatch model), or stay external-only? (from #03)
- Should the critics see which agent produced each finding, or should findings be anonymized to prevent bias? (from #04)
- What is the exact schema for verdict output (per-finding verdict + agent score structure)? (from #04)
- Should quality scores influence future reviews (e.g., confidence multiplier for noisy agents)? (from #04)
- Exact frontmatter schema and validation: a JSON schema for the frontmatter, and how strictly to reject unknown fields? (from #05)
- How does `kind: command` express output parsing without a script (delimited / JSON / regex), and when is a `parser:` script required? (from #05)
- Do the meta-review agents (skeptic, calibrator) also become plugins, or stay core? They currently hard-code `ReportFindings`. (from #05)
- Config migration: keep `agents.*` and `external_tools.*` as deprecated aliases for one release, or break cleanly? (from #05)
- Should a plugin be able to opt its findings out of the autonomous fix loop (gator is review-only upstream)? (from #05)
- Should triage auto-discover bot profiles from `kind: command` reviewer metadata (carried over from #03)? (from #05)
- Remote plugin sources (git URLs in config, community catalog): parked for a later brainstorm. (from #05)
- Default cap on PRs per run (`--limit`), and what happens when the selection exceeds it. (from #06)
- Sequential or parallel per-PR subagents, and if parallel, what concurrency limit (rate limits on gh and external reviewers like CodeRabbit). (from #06)
- Unattended review policy: post findings as comments only, or also auto-fix on the user's own PRs? Never auto-fix someone else's PR seems a safe floor. (from #06)
- "Reviewed since head commit" needs the head SHA in the cc-review marker; does the marker change format, and how are older markers without a SHA treated? (from #06)
- Should single-PR `review --pr <n>` also switch to worktree checkout when the PR is not the current branch, or only warn? (from #06)
- Where does bulk mode read per-repo config when worktrees live outside the repo root (`.cc-review/` layering)? (from #06)
- Retention policy for `.cc-review/bulk/` state directories. (from #06)
- What exact evidence and precedence determine the three groups, and how should uncertain or shared responsibility be displayed? (from #07)
- What history window and item-state defaults keep the inbox useful, including stale participation, closed issues, merged PRs, draft PRs, and answered Discussions? (from #07)
- What are the exact repository and item-type filter arguments, and should users be able to filter the resulting groups too? (from #07)
- How should mentions, team review requests, bot activity, ordinary comments, and replies already addressed by later activity affect relevance and next-action judgments? (from #07)
- What ordering, result limits, and summary depth make a busy repository manageable? (from #07)
- How should the report disclose incomplete coverage, unavailable Discussions, missing permissions, or activity it could not inspect? (from #07)
- What evidence establishes ownership of an earlier review thread, and should manual review threads be included alongside cc-review threads in the first version? (from #08)
- Should relevant code changes without an author reply trigger reviewer triage, and how should already assessed but unresolved threads be reconsidered? (from #08)
- What evidence distinguishes requested fixes from additional changes warranting review, and how should uncertain cases map consistently to inbox and bulk selection? (from #08)
- Should reviewer triage include draft PRs by default, even if first reviews exclude them? How should inbox expose each action's effective filters and exclusions? (from #08)
- How should review and triage recognize verification already performed at the same code and conversation state while preserving a separate outstanding review obligation? (from #08)
- What shared evidence contract can inbox and bulk selection use without turning the inbox into a full review? The helper or snapshot format belongs in planning. (from #08)
- What sequencing lets #08 establish useful alignment before #09's incremental review behavior is available, and which behavior requires both features? (from #08)
- What evidence establishes a trustworthy completed personal baseline, including no-findings reviews, reviewer/configuration differences and chains of incremental runs? (from #09)
- What comparison evidence reliably separates author changes from upstream movement across rebases, force pushes and conflict resolutions, and when is full-review fallback required? (from #09)
- How should unsupported command-reviewer scope and incomplete reviewer coverage affect fallback, reporting and baseline completion? (from #09)
- What shared verification evidence should review, triage and meta-review receive to preserve findings across moved code, avoid duplicates and enforce the critical-only unchanged-code exception? (from #09)
- How should verification outcomes and new findings be presented between existing threads and the review summary, including acknowledgment of a renewed request on unchanged content? (from #09)
- What evidence identifies a follow-up when earlier reviews are manual, summary-only or lack a trustworthy incremental baseline, without confusing conversation history with completed code coverage? (from #10)
- How should materiality map to existing severity and gate settings, including older findings whose severity or blocking status was misclassified? (from #10)
- How should summary-only concerns and their replies retain identity and decision history when no inline thread exists? (from #10)
- What evidence distinguishes an accepted explanation or agreed deferral from an unaccepted author claim, and when does new evidence justify revisiting it? (from #10)
- How should incomplete or very large review histories be bounded and disclosed without silently omitting relevant decisions? (from #10)
- What minimum conversation context and final checks ensure the same policy for prompt and command reviewers, meta-review and reporting? (from #10)
- What should the command be named, and what issue-number, URL, and repository inputs should it accept? (from #11)
- What precedence and discovery rules should apply to project principles, contribution guidance, review hints, and maintainer decisions when sources conflict or are incomplete? (from #11)
- What bounded investigation and evidence presentation are sufficient to check issue claims without turning assessment into an implementation or full code review? (from #11)
- What should happen when the prose plugin is unavailable, and should issue replies use a dedicated maintainer voice? (from #11)
- How should later invocations incorporate new use-case evidence and prior maintainer answers without repeating questions or contradicting earlier decisions? (from #11)
- Should the inbox eventually suggest this command for relevant issues? Automatic invocation and bulk issue assessment are outside the initial agreed workflow. (from #11)

## Parked Ideas

- Remote plugin sources (git URLs in config, community catalog) (#05)
  Reason: Parked for a later brainstorm.
