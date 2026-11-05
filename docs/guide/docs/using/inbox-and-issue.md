# Inbox and issue assessment

<!-- Sources:
cc-review:README.md:86
cc-review:README.md:88
cc-review:README.md:90-96
cc-review:README.md:98
cc-review:README.md:102
cc-review:README.md:108-115
cc-review:README.md:117
cc-review:README.md:119
cc-review:README.md:121
cc-review:review/core/commands/inbox.md:26-27
cc-review:review/core/commands/inbox.md:94-96
cc-review:review/core/commands/inbox.md:108
cc-review:review/core/commands/inbox.md:110-118
cc-review:review/core/commands/issue.md:16-17
cc-review:review/core/commands/issue.md:79
cc-review:review/core/commands/issue.md:81
-->

A repository collects pull requests, issues, and Discussions from many people, and not every one of them is yours to act on. Two commands help you decide where your attention goes before you start reviewing or writing code. `/cc-review:inbox` surveys one repository and groups the open items by who needs to act next. `/cc-review:issue` takes a single issue and separates its concrete need, its fit with the project, and whether the work is justified, then drafts a reply you can send. Both commands are read-only. Neither posts a comment, edits code, or changes an issue, so you can run either one to understand a situation without touching it.

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

The inbox keeps relevance apart from responsibility. It does not decide that you owe a reply because you authored an item, took part in it once, or someone posted after you. For each item it works out why the item appears, the current state, any outstanding request and who that request falls to, and the step you would take next. When the evidence does not settle who acts next, the item is marked uncertain and asks you to check the context, which is not a claim that you owe an answer.

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

## Assess a single issue

Before you commit time to an issue, you want to know whether it describes a real need, whether that need fits the project, and whether building it is justified. `/cc-review:issue` reads the issue conversation and any matching project guidance, makes those three judgments separately, and gives you both the reasoning and a reply you can post.

Assessment works on GitHub.com issues only, the target must be an issue (pull requests are rejected), and you name it explicitly.

1. Run the command with the issue number:

   ```
   /cc-review:issue 42
   ```

   You can also pass a full issue URL, or add `--repo owner/name` to assess an issue in a repository you are not checked out in.

2. Read the two parts of the result. The first is the maintainer reasoning, ending in one of four recommendations: **Pursue**, **Need more evidence**, **Clarify project direction**, or **Do not pursue**. The second is a separate friendly reply drafted for you to send. When the issue does not yet establish a concrete use case, the draft asks the author for one real example rather than proposing a solution.

## Both commands only read

Neither command changes anything on GitHub or in your checkout.

> [!IMPORTANT]
> The inbox runs no review, triage, checkout, assignment, merge, reply, or thread-resolution action; every suggested action is text for you to act on. Assessment never implements, posts, assigns, labels, or closes an issue, and it never launches a review. Posting a drafted reply is a separate step you take yourself.

> [!NOTE]
> This page covers the commands you run. For how the inbox weighs responsibility and how assessment judges need and fit, read [How it works](../how-it-works/index.md). For the full flag list, see the [Reference](../reference/index.md).

> [!NOTE]
> These commands were verified against cc-review <!-- guide:attr cc-review-version -->1.4.0<!-- /guide:attr -->.
