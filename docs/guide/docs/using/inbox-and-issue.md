# Inbox and issue assessment

<!-- Sources:
cc-review:README.md:78-108
cc-review:README.md:109-126
cc-review:README.md:261-270
cc-review:review/core/commands/inbox.md:18-42
cc-review:review/core/commands/inbox.md:89-113
cc-review:review/core/commands/inbox.md:119-172
cc-review:review/core/commands/inbox.md:173-226
cc-review:review/core/commands/issue.md:8-18
cc-review:review/core/commands/issue.md:27-39
cc-review:review/core/commands/issue.md:81-92
cc-review:review/core/commands/issue.md:101-122
cc-review:review/core/templates/issue-assessment.md:1-5
cc-review:review/core/commands/unattended.md:9-21
cc-review:docs/CI.md:132-174
-->

A repository collects pull requests, issues, and Discussions from many people, and not every one of them is yours to act on. Two commands help you decide where your attention goes before you start reviewing or writing code. `/cc-review:inbox` surveys one repository and groups the open items by who needs to act next. `/cc-review:issue` assesses a single issue, separates its concrete need, its fit with the project, and whether the work is justified, and drafts a reply.

The inbox report and the guided tour are read-only, and interactive assessment never posts a comment. Acting on what you find is a separate, explicit step: you hand chosen items to other commands yourself, and explicit unattended assessment is the one form of assessment on this page that publishes on its own.

Both commands need Python 3.9 or newer, `jq`, and an authenticated `gh` for the repository you work with.

Check: the tools both commands rely on are available.

```bash
gh --version && jq --version && python3 --version
```
<!-- expect: exit 0 -->

## See what needs your attention

One repository gathers pull requests, issues, and Discussions from everyone who works on it, and the inbox explains which of them need you. It covers your own items, your assignments, review requests (including requests to your teams), mentions in pull requests and issues, and conversations you commented on or reviewed. The report groups every item by the action it is waiting on, so you read it top to bottom instead of opening each thread to find out.

1. From a checkout of the repository, run the command with no arguments:

   ```
   /cc-review:inbox
   ```

2. Read the report. It sorts every item into **Needs your attention**, **Waiting on others**, and **No current action**. Each entry says why it appears, links to the activity that supports it, and suggests a next step. A pull request can suggest both a review and a triage pass, because one does not clear the other.

The report has a fixed shape:

- A compact header names the repository, the authenticated user, the collection time, the selected types, the active state and history scope, and the per-type limit.
- **Needs your attention** leads as a table with five fixed columns: Item, What, Why you, Certainty, and Next step. Explicit requests come before uncertain ones, then the most recently updated. Each row links the item, gives the reason it concerns you in a few words, labels the judgment **Explicit**, **Inferred**, or **Uncertain**, and suggests an action such as answering a comment or replying and then triaging.
- Below the table, one detail block per attention item restates the situation, keeps a separately labeled **My take** apart from it, and links at least one piece of evidence. My take is the assistant's own judgment. It is an opinion, never an obligation, and it may say that no response is worthwhile.
- **Waiting on others** and **No current action** stay brief as two-column lists: the item, and what you are waiting on or the current state.
- A compressed coverage account closes the report. It gives the selected counts per type, selection omissions, capped searches, failed or unavailable sources, missing or truncated context, and the activity and text bounds, and it identifies items whose context was not read before the shared collection deadline.

The inbox keeps relevance apart from responsibility. It does not decide that you owe a reply because you authored an item, took part in it once, or someone posted after you. For each item it works out why the item appears, the current state, any outstanding request and who that request falls to, and the step you would take next. When the evidence does not settle who acts next, the item is marked uncertain and asks you to check the context, which is not a claim that you owe an answer.

Producing the report writes nothing: no comment is posted, no thread is resolved, no branch is pushed, no review or triage agent is launched, and the working tree does not change. Acting on an item is always a separate, explicit step.

## Narrow the inbox

By default the inbox reports all three item types: open pull requests and issues (including drafts) with no date cutoff, and Discussions updated in the last 90 days. Four flags narrow that scope.

- `--repo owner/name` picks a repository explicitly, even when you are not inside a checkout of it. Without the flag the inbox follows the repository that `gh` is pointed at.
- `--type pr,issue,discussion` selects one or more item types. Repeat the flag to combine selections; the default is all three.
- `--limit N` keeps the most recently updated items per type, from 1 to 100. The default is 10 per type.
- `--since YYYY-MM-DD` filters every selected type by its last update, and replaces the 90-day Discussion window.

For example, this reports only pull requests, up to 20 of them, updated since the start of October:

```
/cc-review:inbox --type pr --limit 20 --since 2026-10-01
```

## Take the guided tour

After the report, the inbox can offer a guided tour of the attention items. Acting on an item is never automatic, so the tour is an opt-in step you ask for.

The command offers the tour only when the **Needs your attention** group is non-empty and the run is interactive. When the group is empty or nobody can answer a prompt, it ends with the complete read-only report, and declining the offer changes nothing.

1. Choose a batch. A batch holds at most five attention items. The default is the top five in report order, explicit requests first and then the most recently updated; you can accept it or name items from the table. A selection with more than five items, or with an item outside the attention group, is rejected and you are asked again. When fewer than five attention items exist, the batch is all of them.

2. Read each briefing. The tour walks the batch one item at a time and draws context only from the item's slice of the snapshot it already collected. It never re-collects repository state. When your agent supports subagents, a fresh per-item subagent reads only that item's entry and returns a short briefing; otherwise the same briefings appear inline, one at a time.

3. Choose an action per item, then confirm. Nothing runs per item. For a pull request the choice is review, triage, or skip, and both actions are offered when both apply. For an issue it is assessment with the `issue` command, or skip. A Discussion gets a textual suggestion, because no matching command exists. After the last item, the tour shows the recorded choices and asks you to confirm them.

4. Hand off the batch. Confirmed pull requests always go to bulk mode. Every PR chosen for review goes to `review --bulk --prs <list>`, and every PR chosen for triage goes to `triage --bulk --prs <list>`, as one explicit list per command even when a list holds a single PR. The tour never starts `review --pr N` or `triage --pr N`, because a single-PR run executes in the current context and the invoking checkout, while bulk mode analyzes each PR in its own worker and detached worktree. Issues are assessed one at a time with the `issue` command after the bulk runs.

Fan-out is offered only when the inbox runs inside a local checkout of the target repository. With `--repo owner/name` and no checkout, or with a checkout of a different repository, the tour says that acting is unavailable and still delivers the full read-only report and the briefings.

When your agent cannot launch and chain a command in this session, the tour does not fail. It prints the exact commands for you to run as a text handoff, for example `review --bulk --prs 109` or `triage --bulk --prs 109,44`.

When a batch launched at least one command, the tour ends with that batch, because the snapshot no longer reflects the actions just taken and the context now carries the hand-offs. Continue from a fresh session: clear the conversation (for example `/clear` in Claude Code or `/new` in Codex), run `inbox` again, and work from the new report. When the batch launched nothing and unvisited attention items remain, the tour offers the next five or a re-run.

## Assess a single issue

Before you commit time to an issue, you want to know whether it describes a real need, whether that need fits the project, and whether building it is justified. `/cc-review:issue` reads the issue conversation and any matching project guidance, makes those three judgments separately, and renders a reply draft and maintainer reasoning.

Assessment works on GitHub.com issues only, the target must be an issue (pull requests are rejected), and you name it explicitly.

1. Run the command with the issue number:

   ```
   /cc-review:issue 42
   ```

   You can also pass a full issue URL, or add `--repo owner/name` to assess an issue in a repository you are not checked out in.

2. Read the rendered comment. It has three layers: a friendly reply visible to everyone, a collapsed maintainer block, and the full assessment as hidden JSON for later agent runs. The renderer prints the reply first, then an `### Assessment` section that holds the collapsed block. The title of the collapsed block carries the verdict, the kind, and the impact. Inside are a short summary, a small table for the use case, why it matters, and fit, the alternatives, the recommendation with its label, and a nested Evidence and limits block. The recommendation is one of **Pursue**, **Need more evidence**, **Clarify project direction**, or **Do not pursue**.

3. Read the private part. The rendered reply is your draft, and the command never posts it. For you, the result also covers the coverage of the assessment (collected history and text limits, warnings, uninspected evidence, unavailable project context or an uncertain local revision, and the scope that was assessed), material uncertainties, and any pending maintainer question.

Interactive assessment never posts comments, edits code, assigns, labels, or closes the issue, and it never launches a review. Posting the drafted reply is a separate step you take yourself.

Explicit `issue N --unattended` is the exception. An unattended run asks no questions and posts the rendered reply and the configured triage labels under the unattended policy. That policy also governs unattended review and triage, including the CI workflows; read [CI setup and policy](ci.md) for how it is configured and what it publishes.

> [!IMPORTANT]
> The inbox report, the guided tour itself, and interactive assessment are read-only. The tour's fan-out and `issue N --unattended` hand work to commands that act under their own confirmation and publication policy; the inbox adds no write authority of its own.

> [!NOTE]
> This page covers the commands you run. For how the inbox weighs responsibility and how assessment judges need and fit, read [How it works](../how-it-works/index.md). For the full flag list, see the [Reference](../reference/index.md).

> [!NOTE]
> These commands were verified against cc-review <!-- guide:attr cc-review-version -->1.9.0<!-- /guide:attr -->.
