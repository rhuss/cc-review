---
name: speckit.cc-review.inbox
description: Read-only personal repository inbox for PRs, issues, and Discussions
---

# cc-review: Inbox (spec-kit integration)

This user command works independently of ship mode and does not require a feature spec.

Resolve cc-review core from the installed cc-review plugin, then .cc-review/core, then ~/.cc-review/core. Verify commands/inbox.md and scripts/inbox.py. If missing, report “cc-review inbox core not found; update or reinstall cc-review.”

Set CC_REVIEW_CORE_DIR to the resolved absolute directory in every shell block. Read and execute commands/inbox.md from that directory, preserving the invoking working directory and all user arguments.

Supported arguments: --repo owner/name, repeatable --type pr,issue,discussion, --limit N, --since YYYY-MM-DD, --help. Do not inject --spec or other review/triage arguments.

Report only; never launch review, triage, or response actions.
