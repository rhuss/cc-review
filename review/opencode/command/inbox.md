# Inbox

Show the user's repository action overview across PRs, issues, and Discussions.

Resolve core from the installed plugin's core directory, or the path in .opencode/plugins/cc-review/.core-path when installed by install.sh, then .cc-review/core, then ~/.cc-review/core. Verify commands/inbox.md and scripts/inbox.py exist.

If no core is found, report “cc-review inbox core not found; update or reinstall cc-review.”

Set CC_REVIEW_CORE_DIR to the resolved absolute path in every shell block. Read and execute commands/inbox.md, preserving the invoking working directory. Forward all arguments unchanged: --repo owner/name, repeatable --type pr,issue,discussion, --limit N, --since YYYY-MM-DD, --help.

The report is read-only by default. After it, inbox may offer an opt-in guided tour of the attention items and, only on the user's explicit choice inside a local checkout, hand off to the existing review, triage, issue, or bulk command; the report and tour never act on their own.
