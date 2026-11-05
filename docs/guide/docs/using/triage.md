# Triage pull request comments

<!-- Sources:
cc-review:README.md:191-205
cc-review:README.md:211-221
cc-review:README.md:239-242
cc-review:review/core/commands/triage.md:13-15
cc-review:review/core/commands/triage.md:196-203
cc-review:review/core/commands/triage.md:218-224
cc-review:review/core/commands/triage.md:460-500
cc-review:review/core/commands/triage.md:502-546
cc-review:review/core/commands/triage.md:887-949
-->

An open pull request collects review comments from bots (CodeRabbit, Copilot, Devin, Greptile) and from human reviewers, and each one needs a reply or a fix. The `/cc-review:triage` command fetches the PR's review threads, classifies each as bot or human, and then handles them by kind: it works through the bot comments on its own and presents the human comments to you for approval. This page covers how to start a triage pass, how bot and human comments are handled, and why triage drafts replies instead of pushing a fix on your behalf. For the mechanism behind each step, see [How it works](../how-it-works/index.md).

## Triage the comments on a PR

Start here when a pull request has gathered review comments you want to work through. Triage needs an authenticated `gh` CLI. If `gh` is not authenticated, the command stops and asks you to run `gh auth login` first.

1. From the PR's branch, run:

   ```
   /cc-review:triage
   ```

   With no arguments, triage uses the open pull request for your current branch. When your branch has no PR but you have exactly one other open PR in the repository, triage uses that one and tells you which.

2. To target a specific pull request by number, pass `--pr`:

   ```
   /cc-review:triage --pr 42
   ```

   Triage includes draft PRs, so you can work through comments before the PR is marked ready for review.

Check: triage recorded its state for the PR.

```bash
ls .cc-review/.triage-state.json
```
<!-- expect: exit 0 -->

## How bot and human comments are handled

Triage splits the review threads into bot threads and human threads and treats them differently.

Before it processes anything, triage logs every bot author it found and how many threads each one has, so no bot's comments slip through unseen. It matches each bot against a known profile (CodeRabbit, Copilot, Devin, and Greptile are recognized) and falls back to conservative defaults for any bot it does not know, but it still assesses every thread on its own.

For each bot thread, triage reads the comment and the code it points at, then reaches one of three verdicts:

- **Valid**: the comment identifies a real issue or improves the code, so triage applies the fix.
- **Invalid**: the code at the cited lines is already correct, so triage skips the fix and prepares a rejection reply that cites the lines proving the bot wrong.
- **Deferred**: the suggestion has merit but is out of scope for this PR, so triage records it and prepares a deferral reply.

Human threads are not handled automatically. Triage presents each one to you with the reviewer's comment, the code in question, and its own assessment (agree, disagree, or partial), together with a drafted reply. You then approve the reply as written, edit it before it posts, or skip the thread to leave it open for the next pass.

## Triage drafts replies, it does not push a reviewer fix

Triage works on comments on your own PR and on reviewer feedback you own on another author's PR. These two roles behave differently, and the difference matters when the PR is not yours.

> [!IMPORTANT]
> When you triage reviewer feedback you own, triage verifies the current code and the exact feedback thread and drafts a response for your approval. In that role it never commits or pushes a code fix. Author triage, on your own PR, keeps its fix workflow and applies valid bot fixes as described above.

For how the review command's fix loop handles the same question of which PRs it can push to, see [Fixes and PR ownership](review.md#fixes-and-pr-ownership).

## Add spec context and control coverage fixes

A few flags adjust what a triage pass does:

- `--spec <path>` gives triage a specification file so it can judge whether a suggestion aligns with the requirements.
- `--no-coverage-fix` skips the automatic coverage remediation.
- `--idea-inbox <path>` captures out-of-scope ideas in a file instead of acting on them.

When Codecov data is available for the PR, triage cross-references it with the bot findings and reports, per file, whether a coverage gap overlaps with an issue a bot already flagged. That overlap strengthens the case for accepting fixes that add error handling or branch coverage.

To triage several of your PRs in one pass, run `/cc-review:triage --bulk`. On your own PRs it keeps the prepared-fix workflow; for reviewer feedback it prepares exact-thread replies without changing any branch, and leaves answers that still need your judgment pending.

> [!NOTE]
> This page covers the commands you run. For how triage verifies threads and classifies bots, read [How it works](../how-it-works/index.md). For the full flag list, see the [Reference](../reference/index.md).

> [!NOTE]
> These commands were verified against cc-review <!-- guide:attr cc-review-version -->1.4.0<!-- /guide:attr -->.
