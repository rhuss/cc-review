# Assess an Issue

Resolve core from the installed plugin's core directory, or the path in .opencode/plugins/cc-review/.core-path when installed by install.sh, then .cc-review/core, then ~/.cc-review/core.

Use the first directory containing commands/issue.md, scripts/assess_issue.py, templates/need-and-fit.md, and templates/maintainer-voice.md. If none exists, report “cc-review issue core not found; update or reinstall cc-review.”

Set CC_REVIEW_CORE_DIR to the resolved absolute path in every shell block, except the collector command, which uses the literal absolute script path as the command describes. Read and execute commands/issue.md, preserving the invoking working directory. Forward all user arguments unchanged: issue number or URL, --repo owner/name, --help.

The command assesses initial issues and drafts a welcoming reply; it does not publish or implement.

Forward `--unattended` unchanged for single items and bulk flows; the shared core policy owns all unattended defaults.
