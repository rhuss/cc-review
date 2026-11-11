# Brainstorm: Unattended cc-review in CI (GitHub Actions)

**Date:** 2026-11-11
**Status:** active
**Issue:** https://github.com/rhuss/cc-review/issues/16

## Problem Framing

cc-review's `review`, `triage` and `issue` commands are built for an interactive session: they draft, show a preview and ask before posting. Maintainers want the same help on every repository without sitting in front of a terminal: new PRs reviewed, bot reviewer comments triaged, new issues assessed and labeled, all inside CI with their own Anthropic API key (or provider) and a model of their choice.

The hard requirement is that a CI run goes from start to finish without asking a single question. A run that would need a human must end in a visible "needs attention" state, never hang or silently stop.

The second need is setup: wiring workflows, secrets, a bot identity, labels and config by hand is error-prone. A dedicated skill should set up and manage cc-review CI on a given repository.

Related work:
- #02 config-system: shipped the `ci` profile and `--config` for `claude -p`; open thread "Should the init skill support generating a GitHub Actions workflow file?" is answered here.
- #06 bulk-review-triage: defined `--bulk --unattended` and its fixed policy (COMMENT only, never fix, withheld on failed checks). This brainstorm extends that policy to single items and CI events.

Existing building blocks:
- `--bulk --unattended` for `review` and `triage` (`review/core/commands/bulk.md`, Unattended Policy) already guarantees no prompts in bulk mode.
- [claude-code-action](https://github.com/anthropics/claude-code-action) supports `plugins` and `plugin_marketplaces`, `anthropic_api_key` / OAuth token / workload identity federation, Bedrock and Vertex, `ANTHROPIC_BASE_URL`, `claude_args`, a GitHub App token via `github_token`, `allowed_bots` and comment trigger phrases.

Audience: any cc-review user, on their own repositories, with their own API key and their own bot identity. A centrally hosted cc-review service is not an option for that audience (it would hold every user's keys).

## Approaches Considered

### A: Central reusable workflow on claude-code-action, plus a `cc-review:ci` skill

cc-review ships a versioned reusable workflow or composite action (`rhuss/cc-review/ci@v1`) that wraps claude-code-action, installs the plugin, routes each event or comment command to a cc-review command, and enforces policy and concurrency. Each repository gets a thin caller workflow and `.cc-review/ci.yml`. A new `cc-review:ci` skill handles setup, status, update, disable and doctor.

- Pros: users receive fixes by bumping a tag; small footprint per repository; app tokens, provider auth and plugin installation come from claude-code-action; no hosting.
- Cons: depends on claude-code-action behavior; its tag-mode tracking comments may clash with cc-review markers, so cc-review likely runs it in plain prompt mode.

### B: Generated self-contained workflows calling `claude -p`

The setup skill writes complete workflow files that install the Claude Code CLI and call `claude -p "/cc-review:... --unattended"` with an explicit tool allowlist.

- Pros: no third-party action; fully transparent; easier to port to GitLab CI later.
- Cons: large generated YAML per repository drifts; upgrades need a setup re-run; token minting, provider auth and comment-command parsing must be rebuilt.

### C: Self-hosted GitHub App service

A webhook receiver that each user (or org) deploys, for example as a container on OpenShift, running Claude Code per job.

- Pros: best install UX for orgs with many repositories (install the app, done); central queue and rate limits; no workflow files.
- Cons: hosting and operations per user; overkill as a first step.

## Decision

**A now, C later.** Build the central reusable workflow on top of claude-code-action and the `cc-review:ci` skill. Design the command entry point (event or command in, cc-review command plus policy out) so that a hosted GitHub App service can reuse it later without changing core. C goes to parked ideas.

## Key Requirements

### Headless contract (cc-review core)

- `--unattended` works for single items, not only with `--bulk`: `review --pr <n>`, `triage --pr <n>`, `issue <n>`.
- In unattended mode no step asks anything. Every place that would ask applies a documented default instead (extends the bulk Unattended Policy).
- Any attempt to ask a question, or a run that ends without a recorded outcome, fails the item as "needs attention" with a reason. The run never hangs.
- `issue` gains an unattended mode: post the assessment reply and apply triage labels by policy.
- Tool permissions are fixed up front (allowlist shipped with the CI entry point), so Claude Code never stops on a permission prompt.

### Triggers

- PR opened / synchronized: review that PR; triage reviewer comments on follow-up pushes.
- Issue opened: run the issue assessment.
- Scheduled sweep: select only items without a complete cc-review marker for their current head commit or conversation state, then run the unattended bulk flow.
- Comment commands on PRs and issues.
- Every event trigger and every command can be switched on or off in `.cc-review/ci.yml`.
- Event triggers, commands and the sweep share one state model (cc-review markers on the item) and never interfere: one concurrency group per item, an in-progress item is skipped by the sweep, and cc-review ignores events caused by its own bot identity (no self-trigger loops).

### Comment commands

- A small, streamlined set: `/cc-review review`, `/cc-review triage`, `/cc-review assess`, `/cc-review fix`, `/cc-review help`.
- Only users with write access may run commands by default; configurable.
- Each command is acknowledged immediately (for example a reaction) and ends with a result or a clear "needs attention" reason.

### Autonomy policy (what CI may do without approval)

- Post PR reviews as COMMENT only; never approve, never request changes.
- Triage review threads: reply to bot reviewer comments and resolve threads the PR addressed; human comments are left untouched and listed under "needs attention".
- Issues: post the assessment reply and apply triage labels; never close.
- Push fixes only on `/cc-review fix` from a maintainer, only on same-repository branches, never on fork PRs.

### Fork safety

- PR code from forks is never executed in a context that holds secrets.
- Fork PRs are reviewed only after a maintainer comment command; the automatic event path explains how to request one.

### Identity and LLM

- Identity options: the user's own GitHub App created through GitHub's App manifest flow (recommended: named bot, scoped permissions, installable across repositories) or `GITHUB_TOKEN` as the zero-setup fallback.
- LLM access is pass-through: Anthropic API key, Claude Code OAuth token, workload identity federation, Bedrock, Vertex, or a gateway via `ANTHROPIC_BASE_URL`. The model is set in `.cc-review/ci.yml`.

### `cc-review:ci` skill

- `setup`: write the caller workflow and `.cc-review/ci.yml`, set secrets with `gh secret set`, optionally create the GitHub App via the manifest flow, create triage labels, run a test dispatch and report the result.
- `status`: show enabled triggers and commands, identity, model, last runs and items needing attention.
- `update`: bump the pinned CI version and migrate config.
- `disable`: switch triggers off or remove the setup cleanly.
- `doctor`: check secrets, app installation and permissions, workflow permissions, plugin version and label presence; explain each failure.

### UX

- One status surface per item (exact form decided in the spec), not a stream of bot comments.
- The sweep writes a run summary (GitHub step summary) with processed items and a "needs attention" list.
- Error messages say what happened and what the maintainer can do next.

### Out of scope

- Hosted GitHub App service (approach C, parked).
- GitLab CI.
- Closing issues or PRs; approve or request-changes reviews.
- Dashboards across repositories.

## Open Questions

- Reusable workflow (`workflow_call`) or composite action as the central entry point, and how the caller pins versions?
- Can claude-code-action run in plain prompt mode without its own tracking comments, or does cc-review need `path_to_claude_code_executable` / direct `claude -p` inside the action?
- What is the "one status surface per item": a GitHub check run, a single sticky comment, or the review itself plus a reaction?
- Exact marker evidence for "complete" per item type (PR review at head SHA, triage at conversation state, issue assessment at last maintainer activity), building on #06 and #08.
- How does the headless contract detect an attempted question reliably (no question tool in `-p` mode, model ending its turn with a question in text)?
- Which triage labels ship by default, and how does `setup` handle repositories that already have a label scheme?
- Cost and runaway guardrails: max turns per item, sweep `--limit`, skipping very large diffs, and how limits are reported.
- `/cc-review fix` on a PR: push to the PR branch, or open a follow-up PR against it? What happens when CI on the pushed fix fails?
- How does the setup skill handle the GitHub App manifest flow end to end (browser step, storing the private key as a secret, installing on the repository)?
- Does the bulk state directory (`.cc-review/bulk/`) matter on ephemeral runners, or do markers alone carry enough state for resume?
