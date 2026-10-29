# Agent Instructions

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - `make validate`
3. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   git push
   git status  # MUST show "up to date with origin"
   ```
4. **Clean up** - Clear stashes, prune remote branches
5. **Verify** - All changes committed AND pushed
6. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds

<!-- >>> spex managed Codex guidance >>>
This block is managed from .specify/spex.json. Keep project guidance outside it.
-->

## Spex workflow in Codex

Invoke Spex skills with `$`, for example `$speckit-specify`, `$speckit-plan`,
`$speckit-tasks`, and `$speckit-implement`. Do not print `/...` examples for
Codex skills. Use `$speckit-spex-help` for the current command list.

When a Spex skill needs a choice, present a short numbered list inline and wait
for the answer. Use Codex subagents only when the user requests parallel work.

<!-- <<< spex managed Codex guidance <<< -->
