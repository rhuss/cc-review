---
name: inbox
description: Personal repository action overview across PRs, issues, and Discussions
argument-hint: "[--repo owner/name] [--type pr,issue,discussion] [--limit N] [--since YYYY-MM-DD]"
---

# Inbox

Resolve cc-review core in order:

1. The installed plugin's core directory (relative to the plugin root).
2. .cc-review/core in the invoking project.
3. ~/.cc-review/core.

Use the first directory containing commands/inbox.md and scripts/inbox.py. If none exists, report “cc-review inbox core not found; update or reinstall cc-review.”

Set CC_REVIEW_CORE_DIR to that absolute directory in every shell block. Read and execute commands/inbox.md, preserving the invoking working directory and forwarding all user arguments unchanged. Supported arguments: --repo, repeatable --type, --limit, --since, --help.

The command is read-only and only suggests follow-up actions.
