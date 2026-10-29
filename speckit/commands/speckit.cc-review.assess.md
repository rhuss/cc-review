---
name: speckit.cc-review.assess
description: Assess initial issues for concrete need and project fit
---

# cc-review: Assess an Issue

This user command works independently of ship mode and does not require a feature spec.

Resolve core from the installed cc-review plugin, then .cc-review/core, then ~/.cc-review/core. Verify commands/assess.md, scripts/assess_issue.py, and templates/maintainer-voice.md. If missing, report “cc-review assess core not found; update or reinstall cc-review.”

Set CC_REVIEW_CORE_DIR to the resolved absolute directory in every shell block. Read and execute commands/assess.md from that directory, preserving the invoking working directory and all user arguments.

Supported arguments: issue number or URL, --repo owner/name, --help. Do not inject --spec or other review/triage arguments. The output is an assessment and draft reply; publishing and implementation are separate actions.
