# Quickstart: Issue Assessment

Use the installed harness's assess skill or command:

```text
assess 42
assess 42 --repo owner/project
assess https://github.com/owner/project/issues/42
assess --help
```

Claude Code and Codex discover review/skills/assess. OpenCode install.sh copies command/assess.md. The spec-kit adapter is $speckit-cc-review-assess after extension installation.

Requirements: Python 3.9+, jq, gh authenticated for the repository, and an AI coding harness. Prose is optional. A matching checkout enables local guidance and focused code inspection; otherwise the report discloses unavailable project context.

Expect a maintainer assessment and a separate reply draft. Answer any material question about project direction before wording is finalized. Missing use-case details become a focused question to the author, without a plan.

Assessment never posts. Tests: python3 -B tests/test_issue_assessment.py; make test; make validate.
