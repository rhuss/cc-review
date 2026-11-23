---
name: issue
description: Use when a maintainer needs to decide whether an initial GitHub issue describes a concrete need, fits the project, and warrants implementation, or needs a welcoming issue reply, for one issue or a batch of untouched issues
argument-hint: "<issue-number-or-URL> [--repo owner/name] [--unattended] | --bulk [--search Q] [--limit N] [--scan S] [--repo owner/name] | --resume [<run-id>]"
---

# Assess an Issue

Resolve cc-review core in order:

1. The installed plugin's core directory (relative to the plugin root).
2. .cc-review/core in the invoking project.
3. ~/.cc-review/core.

Use the first directory containing commands/issue.md, scripts/assess_issue.py, templates/need-and-fit.md, and templates/maintainer-voice.md, plus scripts/issue_bulk.py, scripts/run_state.py, and commands/issue-bulk.md. If none exists, report “cc-review issue core not found; update or reinstall cc-review.”

Set CC_REVIEW_CORE_DIR to that absolute directory in every shell block, except the collector command, which uses the literal absolute script path as the command describes. Read and execute commands/issue.md, preserving the invoking working directory and forwarding all user arguments unchanged: issue number or URL, --bulk, --search, --limit, --scan, --resume [<run-id>], --repo owner/name, --unattended, --help.

The collector needs network access to the GitHub API. In a sandboxed harness, request network permission for its first run, as commands/issue.md describes.

With --unattended, the shared policy posts the assessment and configured labels without prompts. Interactive mode drafts replies; implementation remains separate. Bulk mode (--bulk, --resume) is interactive: it posts only replies the maintainer approves, one by one, and can open draft PRs for small fixes the maintainer chooses.
