# Using cc-review

<!-- Sources:
cc-review:README.md:3-6
cc-review:README.md:24-71
cc-review:README.md:76-140
cc-review:README.md:198-204
cc-review:README.md:261-270
cc-review:review/core/scripts/discover-reviewers.sh:666-680
cc-review:docs/CI.md:1-12
-->

This section takes you from a fresh install to a steady review routine. cc-review is a review plugin for the coding agent you already run, whether that is Claude Code, Codex, or OpenCode. It runs several specialized reviewers on your changes and merges their findings into one report, so you see the issues worth acting on rather than a separate result from each reviewer and tool. You also get a clear view of which pull requests, issues, and discussions still need you next. Once the routine works locally, you can move the same checks into GitHub Actions and let them run on repository events. Read the pages in sequence to get set up and build the routine, or jump straight to the command you need.

The pages, in reading order:

- [Install cc-review](install.md) adds the plugin to Claude Code, Codex, or OpenCode and lists the command-line tools to install first.
- [Review your changes](review.md) runs a review over your current branch or a specific pull request and explains how to read the report it returns.
- [Triage pull request comments](triage.md) sorts a pull request's review comments into bot and human and drafts the replies for your approval.
- [Inbox and issue assessment](inbox-and-issue.md) shows what needs your attention across a repository and helps you judge whether a new issue is worth the work.
- [Automate cc-review in GitHub Actions](ci.md) automates reviews, triage, and issue assessment in GitHub Actions, set up with `cc-review:ci setup`.
