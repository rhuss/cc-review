---
name: ci
description: Set up, inspect, update, disable or diagnose unattended cc-review in GitHub Actions using repository-owned identity and model credentials.
argument-hint: "setup|status|update|disable|doctor [--repo owner/name] [--ref COMMIT] [--remove]"
---

# Manage CI

Resolve cc-review core in order: the installed plugin's `core`, the invoking
project's `.cc-review/core`, then `~/.cc-review/core`. Use the first containing
`commands/ci.md` and `scripts/ci.py`. Report a missing-core error if none exists.
Set `CC_REVIEW_CORE_DIR` to its absolute path in every shell block.

Read and execute `commands/ci.md` from that core. Forward all user arguments
unchanged, preserve the invoking target repository and distinguish interactive
installation from unattended item execution. Never expose credential values.
