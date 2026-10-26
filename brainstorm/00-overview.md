# Brainstorm Overview

Last updated: 2026-10-26

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

## Parked Ideas

- Remote plugin sources (git URLs in config, community catalog) (#05)
  Reason: parked for a later brainstorm.
