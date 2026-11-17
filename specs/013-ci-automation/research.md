# Research

## Central entry point

Decision: reusable workflow owns matrix/item concurrency; composite action is also available to callers. Pin caller to an immutable cc-review commit and pin upstream actions. This keeps generated files thin while supporting customization.

## Model execution

Decision: use `anthropics/claude-code-action/base-action` pinned to verified upstream commit `d5f7970ae232b6039636a16ea7f251e58e814f38`. Its prompt-file, plugins, model args, provider inputs, execution_file and structured_output outputs are documented in the [base action](https://github.com/anthropics/claude-code-action/tree/d5f7970ae232b6039636a16ea7f251e58e814f38/base-action). It supplies plain prompt execution without the top-level action's GitHub tracking comments. Proposal-only tools keep publication policy outside the model. Plugin installation is local from the pinned integration checkout.

## Forks and credentials

Decision: default branch config only, no PR checkout, fixed read-only model tools and environment without GitHub token. GitHub transport outside the model owns writes. [GitHub security guidance](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target) prohibits executing untrusted PR code with secrets. Fork automatic requests produce guidance; maintainer comment review reads bounded API evidence.

## Status and replay

Decision: one sticky comment with versioned per-operation state, trusted only from configured identity. Head SHA for review; head plus thread activity for triage; non-bot issue activity/body for assessment. Re-fetch under item lock and before publishing. Ignore local bulk state across runners; server markers carry resume evidence.

## Fixes

Decision: deterministic file-content proposals committed through Git data APIs; no arbitrary command execution. Restrict paths, reject workflows/config/credentials, require existing successful checks and recheck current permission/head. Non-force ref update protects concurrent pushes. Future hosted App can reuse Python route/proposal interfaces.

## Identity/providers

Decision: optional scoped GitHub App token minted outside model; GITHUB_TOKEN fallback. Provider inputs pass through base-action API/OAuth/federation and Bedrock/Vertex env; external workflows can establish cloud identity before calling composite action. Optional App manifest uses GitHub's browser registration and code exchange; setup reports browser work honestly.

The moving v1 tag did not contain base-action at its resolved commit; use the verified immutable main commit above. Raw v1 content was inconsistent with git tag resolution, so the action pin was verified by commit URL.
