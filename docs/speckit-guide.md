# cc-spex Integration Guide

How cc-review works with [cc-spex](https://github.com/rhuss/cc-spex).

## How Delegation Works

When cc-spex's `spex-deep-review` extension runs (triggered by the `review-code` quality gate), it checks for cc-review:

1. **spec-kit extension registry**: checks `.specify/extensions/.registry` for `cc-review.enabled == true`
2. **Filesystem probe**: checks `.cc-review/core/commands/review.md` and `~/.cc-review/core/commands/review.md`

If found, cc-spex delegates the full review to cc-review with `--spec`, `--hints`, and `--output` flags. If not found, cc-spex runs its simplified built-in review (same 6 agents, same fix loop, but no external tool integration).

## Install as spec-kit Extension

```bash
# From cc-review directory
./adapters/speckit/install.sh

# Or manually
specify extension add ./adapters/speckit --dev
```

Verify:
```bash
jq '.extensions["cc-review"]' .specify/extensions/.registry
```

## What Changes

| Feature | Without cc-review | With cc-review |
|---------|-------------------|----------------|
| Review agents | 6 agents (built-in prompts) | 6 agents (cc-review prompts) |
| External tools | Skipped | CodeRabbit, Copilot, Codex |
| PR triage | Not available | Full triage workflow |
| Fix loop | 3 rounds | 3 rounds (configurable) |
| Spec compliance | From review-code gate | From review-code gate + cc-review |

## Spec-Aware Review

When cc-spex delegates, it automatically passes the feature spec:

```
--spec specs/<feature>/spec.md
--hints .specify/review-hints.md
--output specs/<feature>/review-findings.md
```

Review agents cross-check implementation against FR-NNN requirements from the spec.

## Triage with spec-kit

The spec-kit triage adapter adds:
- **Ship pipeline guard**: skips triage in autonomous ship mode
- **Constitution principles**: extracts principles from `.specify/memory/constitution.md` as review context
- **Idea inbox**: captures deferred findings to `brainstorm/idea-inbox.md`

## Simplified Fallback

When cc-review is NOT installed, cc-spex's built-in deep-review runs:
- Same 6 agent perspectives and prompts
- Same fix loop (up to 3 rounds)
- Same finding schema and deduplication
- Same gate logic (Critical + Important = 0 for PASS)
- Skips external tool integration (Steps 2 and 4)
- No triage capability

## Migration

If you were using cc-spex's built-in deep-review and triage:

1. Install cc-review: `./adapters/speckit/install.sh`
2. Move review hints: `cp .specify/review-hints.md .cc-review/review-hints.md` (optional, cc-spex adapter checks both locations)
3. Move config: create `.cc-review/config.yml` from `config/config-template.yml` if you had custom `deep-review-config.yml` settings
4. Triage: use `/review` (cc-review) instead of `/speckit-spex-collab-triage` (removed from spex-collab)
