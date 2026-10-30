---
name: issue
description: Use when a maintainer needs to decide whether an initial GitHub issue describes a concrete need, fits the project, and warrants implementation, or needs a welcoming issue reply
argument-hint: "<issue-number-or-URL> [--repo owner/name]"
---

# Assess an Issue

Resolve cc-review core in order:

1. The installed plugin's core directory (relative to the plugin root).
2. .cc-review/core in the invoking project.
3. ~/.cc-review/core.

Use the first directory containing commands/issue.md, scripts/assess_issue.py, templates/need-and-fit.md, and templates/maintainer-voice.md. If none exists, report “cc-review issue core not found; update or reinstall cc-review.”

Set CC_REVIEW_CORE_DIR to that absolute directory in every shell block. Read and execute commands/issue.md, preserving the invoking working directory and forwarding all user arguments unchanged: issue number or URL, --repo owner/name, --help.

This command assesses issues and drafts replies. Publishing and implementation are separate actions.
