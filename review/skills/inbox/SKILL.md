---
name: inbox
description: Read-only repository action overview across PRs, issues, and Discussions, with an opt-in guided tour
argument-hint: "[--repo owner/name] [--type pr,issue,discussion] [--limit N] [--since YYYY-MM-DD]"
---

# Inbox

Resolve cc-review core in order:

1. The installed plugin's core directory (relative to the plugin root).
2. .cc-review/core in the invoking project.
3. ~/.cc-review/core.

Use the first directory containing commands/inbox.md and scripts/inbox.py. If none exists, report “cc-review inbox core not found; update or reinstall cc-review.”

Set CC_REVIEW_CORE_DIR to that absolute directory in every shell block, except the collector command, which uses the literal absolute script path as the command describes. Read and execute commands/inbox.md, preserving the invoking working directory and forwarding all user arguments unchanged. Supported arguments: --repo, repeatable --type, --limit, --since, --help.

The collector needs network access to the GitHub API. In a sandboxed harness, request network permission for its first run, as commands/inbox.md describes.

The report is read-only by default. After it, inbox may offer an opt-in guided tour of the attention items and, only on the user's explicit choice inside a local checkout, hand off to the existing review, triage, issue, or bulk command. The report and tour never act on their own.
