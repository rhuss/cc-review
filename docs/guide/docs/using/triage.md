# Triage pull request comments

<!-- Sources:
cc-review:README.md:198-229
cc-review:README.md:245-249
cc-review:README.md:251-255
cc-review:README.md:261-270
cc-review:review/core/commands/triage.md:9-16
cc-review:review/core/commands/triage.md:34-46
cc-review:review/core/commands/triage.md:48-56
cc-review:review/core/commands/triage.md:58-75
cc-review:review/core/commands/triage.md:76-82
cc-review:review/core/commands/triage.md:204-236
cc-review:review/core/commands/triage.md:214-219
cc-review:review/core/commands/triage.md:237-243
cc-review:review/core/commands/triage.md:456-473
cc-review:review/core/commands/triage.md:475-503
cc-review:review/core/commands/triage.md:505-517
cc-review:review/core/commands/triage.md:519-552
cc-review:review/core/commands/triage.md:906-935
cc-review:review/core/commands/triage.md:936-970
cc-review:review/core/commands/triage.md:971-989
cc-review:review/core/commands/triage.md:1075-1134
cc-review:review/core/commands/unattended.md:9-24
cc-review:review/core/commands/unattended.md:26-34
-->

An open pull request collects review comments from bots (CodeRabbit, Copilot, Devin, Greptile) and from human reviewers, and each one needs a reply or a fix. The `/cc-review:triage` command fetches the PR's review threads, classifies each as bot or human, and then handles them by kind: it works through the bot comments on its own and presents the human comments to you for approval. When several human threads are open, one overview and a single decision can settle all of them. This page covers how to start a triage pass, how bot and human comments are handled, how to approve replies in a batch, and why triage drafts replies instead of pushing a fix on your behalf. For the mechanism behind each step, see [How it works](../how-it-works/index.md).

## Triage the comments on a PR

Start here when a pull request has gathered review comments you want to work through. Triage needs an authenticated `gh` CLI. If `gh` is not authenticated, the command stops and asks you to run `gh auth login` first.

1. From the PR's branch, run:

   ```
   /cc-review:triage
   ```

   With no arguments, triage uses the open pull request for your current branch. When your branch has no PR but you have exactly one open PR of yours, triage uses that one and tells you which. When you have several open PRs, it shows the list and asks which one to triage.

2. To target a specific pull request by number, pass `--pr`:

   ```
   /cc-review:triage --pr 42
   ```

   Triage includes draft PRs.

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

### Approve human replies as a batch

When two or more human threads are unresolved, triage first assesses every thread and drafts every reply. Only then does it show one overview: each comment is numbered and comes with its file and line, the verdict, and the drafted reply in full. One question follows with three choices:

- **Approve all** posts every drafted reply in the order shown.
- **One by one** walks the per-thread loop. There you can also choose **Approve the rest**, which posts the current reply and every later one from the overview.
- **Skip all** posts nothing and leaves every comment open.

Triage records the state of each comment after the decision, so the next pass knows what was answered.

## Triage drafts replies, it does not push a reviewer fix

Triage works on comments on your own PR and on reviewer feedback you own on another author's PR. The first is author triage; the second is reviewer triage, and it applies only when at least one unresolved cc-review thread belongs to you. The two roles behave differently, and the difference matters when the PR is not yours.

> [!IMPORTANT]
> When you triage reviewer feedback you own, triage verifies the current code and the exact feedback thread and drafts a response for your approval. In that role it never commits or pushes a code fix. Author triage, on your own PR, keeps its fix workflow and applies valid bot fixes as described above.

The draft is what you approve, so triage shows it in full before anyone decides. In a bulk run, the approve pass renders the reviewer plan with `triage_preview.py`; a single-PR run may render the plan the same way and show the whole file. Applying or skipping the plan follows the normal approval policy.

For how the review command's fix loop handles the same question of which PRs it can push to, see [Fixes and PR ownership](review.md#fixes-and-pr-ownership).

## Add spec context and control coverage fixes

A few flags adjust what a triage pass does:

- `--spec <path>` gives triage a specification file so it can judge whether a suggestion aligns with the requirements.
- `--no-coverage-fix` skips the automatic coverage remediation.
- `--idea-inbox <path>` captures out-of-scope ideas in a file instead of acting on them.

When Codecov data is available for the PR, triage cross-references it with the bot findings and reports, per file, whether a coverage gap overlaps with an issue a bot already flagged. That overlap strengthens the case for accepting fixes that add error handling or branch coverage.

Coverage remediation runs when a Codecov check fails or when a file's patch coverage falls below the configured threshold. In a bulk run this step does not run at all.

## Read the triage summary

Every pass ends with a summary, even when every thread was already handled. In author triage it groups bot comments by author with accepted, rejected, deferred, skipped, and already handled counts, then counts the human decisions: approved, edited, skipped, and pending. When Codecov data is present, it adds a per-file coverage table and appends a warning line naming how many files fall below the patch coverage threshold. Reviewer triage instead reports confirmed fixes, still-present findings, accepted explanations, deferred and unclear outcomes, and names every thread left open by its ID and path.

## Triage several PRs in one pass

To triage several of your PRs in one run, add `--bulk`:

```
/cc-review:triage --bulk
```

A bulk triage covers open PRs with eligible author or reviewer-owned feedback. On your own PRs it keeps the prepared-fix workflow; for reviewer feedback it prepares exact-thread replies without changing any branch, and leaves answers that still need your judgment pending. Before anything is pushed or posted, you see each PR's commit and every reply in full and approve, edit, or skip it.

A bulk run does the thinking per PR in a prepare pass that records every action instead of performing it. Nothing is pushed, posted, or resolved, and no question is asked, until the decision step applies the recorded plan.

Name the PRs yourself when you already know which ones to triage:

```
/cc-review:triage --bulk --prs 41,42
```

`--prs` takes a comma-separated list and cannot be combined with `--pr`, `--all-open`, or `--search`. It also needs `--bulk` (or `--resume`); so do the other bulk selectors, `--search <query>` and `--limit <n>`. `--spec` is not supported with `--bulk`.

## Run a triage without questions

Add `--unattended` to a single-PR triage to run it without questions:

```
/cc-review:triage --pr 42 --unattended
```

Under the fixed unattended policy, triage makes no code changes and replies only to bot reviewer threads. It resolves only exact threads that the current code and the complete conversation prove addressed. Human comments stay untouched and are listed under needs attention. The GitHub Actions setup uses the same policy; see [Automate cc-review in GitHub Actions](ci.md).

A bulk run also accepts `--unattended` together with `--resume`, which continues an unfinished run or starts a new one without asking anything. Unattended triage leaves human comments for you.

> [!NOTE]
> This page covers the commands you run. For how triage verifies threads and classifies bots, read [How it works](../how-it-works/index.md). For the full flag list, see the [Reference](../reference/index.md).

> [!NOTE]
> These commands were verified against cc-review <!-- guide:attr cc-review-version -->1.9.0<!-- /guide:attr -->.
