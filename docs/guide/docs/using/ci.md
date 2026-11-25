# Automate cc-review in GitHub Actions

<!-- Sources:
cc-review:README.md:261-270
cc-review:docs/CI.md:1-12
cc-review:docs/CI.md:14-23
cc-review:docs/CI.md:25-45
cc-review:docs/CI.md:47-61
cc-review:docs/CI.md:63-67
cc-review:docs/CI.md:69-76
cc-review:docs/CI.md:78-95
cc-review:docs/CI.md:97-104
cc-review:docs/CI.md:106-110
cc-review:docs/CI.md:112-123
cc-review:docs/CI.md:125-133
cc-review:docs/CI.md:135-177
cc-review:docs/CI.md:179-185
cc-review:docs/CI.md:187-210
cc-review:docs/CI.md:212-238
cc-review:docs/CI.md:240-258
cc-review:docs/CI.md:260-278
cc-review:docs/CI.md:280-307
cc-review:review/core/commands/ci.md:1-110
cc-review:review/skills/ci/SKILL.md:1-16
cc-review:review/core/commands/unattended.md:1-70
cc-review:review/core/commands/review.md:9-16
cc-review:review/core/scripts/ci.py:207-218
cc-review:review/core/scripts/ci.py:248-255
cc-review:review/core/scripts/ci.py:372-375
cc-review:review/core/scripts/ci.py:455-459
cc-review:review/core/scripts/ci.py:598-606
cc-review:review/core/commands/review.md:635
cc-review:review/config/config-template.yml:31-39,48-54
-->

Reviews, triage, and issue assessment can run inside a repository from GitHub events, without a local invocation. `cc-review:ci setup` installs a pinned GitHub Actions caller with your model credentials and a bot identity. Automatic pull review, bot comment triage, issue assessment, maintainer comment commands, and bounded sweeps then share the same guarded publication policy and one item status surface.

The integration runs in your repository with your model account. There is no hosted cc-review service or shared API key. The reusable entry point is `rhuss/cc-review/.github/workflows/cc-review-reusable.yml@<commit>`, and setup pins both that reference and its `integration_ref` input to the same immutable commit. Choose a commit that contains the CI files.

## What setup installs

Setup generates a small caller workflow and `.cc-review/ci.yml`, helps configure provider secrets, labels, and identity, then dispatches a smoke test once the workflow is available on GitHub. It chooses an immutable 40-character cc-review commit that contains the CI workflow and never uses a moving tag or `main` as the generated pin. The helper refuses unmanaged workflow replacement and preserves an existing valid config.

Two steps stay with you in the browser:

- **GitHub App registration and installation**, when you choose App identity. Setup generates a manifest with scoped permissions. GitHub's browser registration and installation approvals remain user steps, and the one-time manifest code is exchanged privately. Only the App ID and private key are retained.
- **The Actions event policy**, when the repository is public. The workflow file does not change; a repository admin or organization owner allows `pull_request_target` in repository settings.

## Set up the automation

Run setup in the repository you want to automate. The command is interactive, while item execution in CI is always headless. It uses any preferences and authorization you already supplied.

1. From a matching local checkout of the target repository, run:

   ```
   cc-review:ci setup
   ```

   Setup infers the repository from `gh repo view --json nameWithOwner` unless you pass `--repo owner/name`. It requires a matching local checkout before it writes files.

2. Answer the configuration choices: provider and model, enabled triggers, the mode of each operation, identity, label mapping, and resource limits. Setup explains the fixed unattended policy as part of these choices.

3. Store the model credentials without pasting values into arguments. `gh secret set` reads the value from stdin or a private local file:

   ```bash
   gh secret set ANTHROPIC_API_KEY --repo owner/name
   ```

   The `gateway` provider also needs the repository variable `CC_REVIEW_ANTHROPIC_BASE_URL`.

4. Choose the bot identity. With `GITHUB_TOKEN`, keep `identity.bot_login: github-actions[bot]`. With a GitHub App, complete the browser registration and installation, set the App ID as the `CC_REVIEW_APP_ID` repository variable, store the private key as the `CC_REVIEW_APP_PRIVATE_KEY` secret, and set `bot_login` to the App slug plus `[bot]`.

5. Review the generated files, commit them, and push them within the authorized setup scope. Dispatch the smoke test after the workflow is on the default branch, or add an explicit `--ref` for a test branch. Find the exact dispatched run and watch it by ID:

   ```bash
   gh workflow run cc-review.yml --repo owner/name
   gh run watch <run-id> --exit-status
   ```

   A successful empty sweep proves the wiring only. Dispatch an agreed item number with `help` to verify status publication, and use a disposable PR or issue for a paid model smoke test when authorized.

Check: setup generated the configuration file in your checkout.

```bash
test -f .cc-review/ci.yml
```
<!-- expect: exit 0 -->

> [!CAUTION]
> Never put keys or tokens in chat, source, commits, or command arguments. Supply secrets through stdin or a private local file.

## Events and operations

The default events are PR opened and synchronized, a submitted bot review, issue opened, new item comments, a six-hour sweep, and manual dispatch. Follow-up PR pushes select bot triage and review. When a bot reviewer (CodeRabbit, Greptile and similar) submits a review on a same-repository PR, triage starts right away instead of waiting for the next push or sweep (`triggers.bot_reviews`).

`triggers` decides when automatic runs can start, and `enabled: false` stops everything. A manual dispatch with no number runs a bounded sweep; a number plus an operation targets one item. Fix is comment-only.

`operations` decides what runs, per operation:

| Mode | Automatic (new issue or PR, push, sweep) | `/cc-review <op>` comment or manual dispatch |
|---|---|---|
| `auto` | yes | yes |
| `on-demand` | no | yes |
| `off` | no | no; the request gets a "disabled" status |

`on-demand` suits issue assessments when automatic replies might put off new reporters, and any operation whose token cost should be spent deliberately. Only users allowed by `command_permissions` (writers by default) can request it. When `review` is `on-demand`, opening a PR adds a status row saying a review is available with `/cc-review review`, which shows the integration is active without spending a model run. `off` posts nothing. `fix` and `help` are always on-demand. The default is `auto` for review, triage and assess. Older configurations with boolean `commands` still load: `true` keeps the default mode and `false` means `off`.

## Command comments

Users allowed by `command_permissions` (writers by default) request an operation with a whole-comment command. Commands work as top-level PR comments and as replies inside a review thread.

| Command | Target | Effect |
|---|---|---|
| `/cc-review review` | PR | Review summary in the sticky status, anchored by a COMMENT review at the observed head |
| `/cc-review triage` | PR | Reply to bot threads and resolve verified addressed concerns |
| `/cc-review assess` | Issue | Assessment reply and mapped triage labels |
| `/cc-review fix` | Same-repository PR | Propose file changes and push a child commit after policy checks. Replied inside a review thread, it fixes only that thread's concern |
| `/cc-review help` | Either | Show command help in the sticky status |

Current repository write, maintain or admin permission is required by default. `command_permissions` may additionally allow read or triage permission for other commands; fix always requires a writer. The runtime rechecks permission and the original comment before publication. Shell suffixes, quoted examples, and multi-command comments do not run.

A thread reply needs the `pull_request_review_comment` trigger in the caller, and `cc-review:ci update` adds it to older callers. Thread replies on fork PRs are ignored, because GitHub gives those runs no secrets. Only `fix` is scoped to its thread; the other commands act on the whole PR wherever they are posted.

The bot reacts on the command comment:

| Reaction | Meaning |
|---|---|
| 👀 | Command picked up |
| 🚀 | Completed |
| 👍 | Already current or skipped; nothing to do |
| 😕 | Needs attention; the status comment has the reason |

## What the unattended policy does

Every CI operation runs under a fixed unattended policy. Reviews use COMMENT, never approval or request changes. Pending or failed checks withhold review and fix publication. A reply or resolve that GitHub refuses on one thread does not stop the others; the status names the failed threads, and the run log has GitHub's message.

Triage touches bot reviewer threads only; human threads appear under needs attention. Assessment never closes or assigns issues. Fixes require a writer's explicit comment, an unchanged same-repository head, and successful existing checks. Changes are committed through the GitHub data API without executing project code, and a non-force ref update rejects competing pushes. Fix proposals are limited to existing regular, non-hidden files and bounded content. Code tests are not executed by this entry point, and a pushed fix runs the repository's ordinary CI. Inspect those checks before merging. There is no automatic rollback or repeated fix loop.

A thread fix sees only its thread and that thread's file. After pushing, the bot replies in each fixed thread with a link to the new commit, a one or two sentence summary of the change, and a hidden marker. It leaves the thread open. When the model finds that the current files already address the request (for example a repeated command on a fixed thread) and proposes no change, the fix ends as skipped with a reason and a 👍 reaction, and nothing is pushed. The publisher does not check this on its own; a proposal with changed files is pushed. A PR-wide `/cc-review fix` skips resolved threads and threads that carry a fix marker, works on the files those remaining threads point to (all changed files when there are none), and marks the threads its change addresses. File contents are bounded by `limits.fix_bytes`.

The CI analysis is proposal-only. It receives bounded diff and conversation evidence, the bundled review perspectives or need and fit guidance, bounded default-branch project guidance, and the unattended policy. It has no GitHub token, question tool, shell, network, or project execution. Issue assessments additionally get read-only `Read`, `Grep`, and `Glob`, confined to the default-branch checkout. Other operations run without tools, and the PR head is never checked out. A deterministic publisher checks the structured proposal before any mutation and requests maintainer attention when the supplied evidence is insufficient.

Published text follows the [cc-prose](https://github.com/rhuss/cc-prose) humanizer; `prose: false` in `.cc-review/ci.yml` turns this off. Because guidance is not a guarantee, the publisher also replaces any remaining em or en dash outside code with plain punctuation before posting a review, assessment, or thread reply.

A single updated bot status comment (heading `### cc-review CI`) shows a table with one row per action: its result, when it was updated, and the run log. The row of a completed fix links the pushed commit. The comment is posted as soon as an operation starts and edited in place. The model's full reasoning goes to the run's step summary. The status comment shows only each action's result, which for a skipped or needs-attention result includes the short reason. A hidden marker in the same comment records per-operation state, and only markers authored by the configured identity are trusted.

Single-item core commands also accept `--unattended` outside CI: `review --pr 7 --unattended`, `triage --pr 7 --unattended`, and `issue 42 --unattended`. Review and triage reuse the bulk fixed policy on an explicit one-item selector. Issue assessment uses the guarded assessment publisher and your authenticated posting identity. Interactive invocations retain their draft and approval flows.

## Issue assessments

An assessment posts one comment in three layers. The first is a friendly reply to the reporter, visible to everyone. The second is a collapsed block for maintainers whose title carries the verdict, the kind, and the impact. The third is the full assessment as hidden JSON for later agent runs. The verdict is one of "worth doing", "needs an example", "needs a maintainer decision", or "not planned for now".

Without a concrete, real-world example (for bugs: reproduction steps or a bug confirmed in the code), the reply asks for one, severity and alternatives are left out, and the recommendation cannot be Pursue. A bug counts as confirmed only when the code shows it, cited with file and line. The label follows the recommendation. The manual `issue` command renders the same format as its draft and never posts.

## Identity

`GITHUB_TOKEN` is the simplest setup. Keep `identity.bot_login: github-actions[bot]`. The caller requests contents, issues, and pull-requests write plus checks and actions read, so organization policy must permit these workflow permissions. GITHUB_TOKEN writes generally do not trigger new workflows; use a GitHub App if fix pushes must trigger ordinary CI.

A named GitHub App is recommended for a reusable bot identity across repositories. The manifest cannot set a logo, so setup points you to the bundled `cc-review-app.png` icon to upload under the App's "Display information" settings. The selection and worker jobs request repository-scoped installation tokens, with contents read except during an authorized fix, so reactions, status, and replies all come from the App. Doctor can verify installation access with a freshly minted token in `CC_REVIEW_APP_TOKEN`.

## Model providers

Set `model` to the provider's model identifier and `provider` to the selected path. The generated caller passes the names through to the pinned claude-code-action base action.

| Provider | Secrets | Repository variables |
|---|---|---|
| `anthropic` | ANTHROPIC_API_KEY | none |
| `gateway` | ANTHROPIC_API_KEY | CC_REVIEW_ANTHROPIC_BASE_URL |

`gateway` sends the same API key to an Anthropic-compatible endpoint, for example an internal model gateway. Earlier versions also offered `oauth`, `federation`, `bedrock`, and `vertex`; a configuration that still names one of them fails with a message pointing to these two.

Supply secrets with `gh secret set` using stdin or a private local file. Doctor reads secret names only. Provider values never enter item snapshots or prompts.

## Forks and configuration trust

The workflow checks out only the default branch configuration and the pinned cc-review integration. It never checks out a PR head. Automatic fork events publish guidance to request review from a writer. An authorized `/cc-review review` reads fork diff data through the API and cannot execute fork code. Fork triage and fixes are refused, and events authored by the configured bot are ignored.

Before publishing, a CI run compares the item with the state it analyzed and withholds the result when that state moved. A review or fix is withheld when the PR head changed. A triage reply or resolution is withheld when the head changed or when any review thread on the PR gained or changed a comment by anyone other than the configured bot identity; a human comment, another bot's comment, a new thread started by someone else, and an edited comment all count. An assessment is withheld when the issue title or body changed, or when a comment by anyone other than the configured bot identity was added or changed. A new PR comment that leaves the head unchanged does not stop a CI review. The posting check that counts other people's PR comments, with [`pr_posting.ignore_authors`](../reference/config-and-schema.md#pr_posting) for logins treated like bots, belongs to local review runs.

## Public repositories: allow pull_request_target

PR events reach the workflow through `pull_request_target`, which runs the default-branch workflow with access to secrets. GitHub will block this trigger on public repositories unless an Actions event policy allows it. Until the policy requirement applies, runs show a "Workflow execution policy warning (evaluate mode)" annotation. Private and internal repositories are not affected.

To keep automatic PR reviews working, a repository admin or organization owner creates a policy under **Settings > Actions > Policies > New actions policy**. The workflow file itself does not change.

- **Enforcement status:** Active.
- **Target workflows:** Add target > path `cc-review.yml`, so other workflows keep the default block.
- **Restrict events:** checked. Allowed events is an allowlist for the targeted workflow, so add every trigger in the caller's `on:` block, not only `pull_request_target`. For the default caller that is `pull_request_target`, `issues`, `issue_comment`, `pull_request_review`, `pull_request_review_comment`, `schedule`, and `workflow_dispatch`.
- **Restrict actors** and **Require lockfile:** unchecked.

> [!IMPORTANT]
> A trigger you leave out of the policy stops firing for cc-review.

After saving, trigger a run by pushing to a PR or running `gh workflow run cc-review.yml`. If the "Workflow execution policy" annotation is gone, the policy matches.

## Limits and failures

Defaults are 10 sweep items, 30 model turns, 15 model minutes per item, and 100,000 diff bytes. Config validation bounds these to 100 items, 100 turns, 60 minutes, and 1,000,000 diff bytes. A sweep's processed-item limit is separate from the bounded API scan.

Oversized, missing-patch, or truncated evidence is withheld. No prompt or permission request can suspend an item: a missing or malformed structured outcome, model timeout, or denied operation becomes needs attention with a remedy. An API outage that prevents status publication is visible as a failing workflow and step summary; inspect the run and retry. Manual cancellation may leave a running marker until its expiry.

Common remedies:

- Failed or pending checks: fix or wait for those checks, then rerun the command.
- Changed head or conversation: rerun against current evidence.
- Missing credentials, labels, or permissions: run `cc-review:ci doctor` and follow its specific setting, secret, or grant instructions.
- Human threads or insufficient current-code evidence: inspect and handle them as a maintainer.
- Fork event: have a writer post `/cc-review review`.
- Model, tool, or result failure: inspect the linked run and retry; raise a bounded resource setting only when the item requires it.

## Manage the installation

Four commands manage an installed automation. Status only reports the current state; update and disable change the installation after you commit and push. Doctor validates the installation and explains what it cannot confirm.

- **`cc-review:ci status`** presents enabled triggers and commands, identity, model and provider, the immutable ref, recent run URLs and conclusions, and attention items. It reports the attention scan scope (the latest 30 open items) and never changes config or posts comments.
- **`cc-review:ci doctor`** validates config, consistent pins, secret names (never values), provider variables, labels, recent runs, and the remote plugin version. It explains every failure and the next action, and inspects the caller permissions: issues and pull-requests write, checks and actions read, and contents write for fixes. For a public repository it reminds the owner that `pull_request_target` needs an explicit Actions event policy, which doctor cannot read.
- **`cc-review:ci update`** resolves a new immutable integration commit and updates both pins while retaining caller additions and config settings. It adds the `pull_request_review_comment` trigger to older callers. An unsupported config schema stops with an explicit migration message instead of resetting your settings. Re-run doctor and a smoke dispatch after committing and pushing.
- **`cc-review:ci disable`** sets `enabled: false`, which prevents all events, commands, dispatches, and sweeps after commit and push. With `--remove` it removes only managed workflow, config, and manifest files. Labels, secrets, and App installations remain for the owner to revoke if desired.
