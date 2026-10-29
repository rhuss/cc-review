# Assess an Issue

Resolve core from the installed plugin's core directory, or the path in .opencode/plugins/cc-review/.core-path when installed by install.sh, then .cc-review/core, then ~/.cc-review/core.

Use the first directory containing commands/assess.md, scripts/assess_issue.py, and templates/maintainer-voice.md. If none exists, report “cc-review assess core not found; update or reinstall cc-review.”

Set CC_REVIEW_CORE_DIR to the resolved absolute path in every shell block. Read and execute commands/assess.md, preserving the invoking working directory. Forward all user arguments unchanged: issue number or URL, --repo owner/name, --help.

The command assesses initial issues and drafts a welcoming reply; it does not publish or implement.
