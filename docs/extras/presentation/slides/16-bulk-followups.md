---
layout: default
---

# Review many PRs at once, and only what changed

```bash
/cc-review:review --bulk
/cc-review:review --bulk --resume --unattended
```

<div class="grid grid-cols-[auto_1fr] gap-x-6 gap-y-3 mt-10 sel">
  <div class="sel-key">Selected</div><div>review requested from you or your team, or new commits since your last cc-review</div>
  <div class="sel-key">Or pick</div><div><code>--all-open</code> · <code>--search "label:bug"</code> · <code>--prs 101,104</code></div>
  <div class="sel-key">Skipped</div><div>drafts, PRs already reviewed at their current commit</div>
  <div class="sel-key">Then</div><div>all PRs reviewed first, one decision table, only then any action</div>
</div>

<div class="mt-8">

- Follow-ups: **only the delta**, earlier findings verified

</div>

<style>
.slidev-code {
  font-size: 1.4rem !important;
  line-height: 1.6 !important;
  padding: 1rem 1.4rem !important;
  margin-top: 1.5rem !important;
}
.sel { font-size: 1.25rem; }
.sel-key { font-weight: 700; color: var(--primary); }
.sel code { font-size: 0.9em; }
</style>

<!--
**Goal:** review at maintainer scale. Optional slide, cut it if time is short.

**Say:**

"If you're a maintainer with a queue of pull requests, `--bulk` reviews all of them in one go. Every PR that asks for your review, plus the ones you reviewed before that got new commits."

"Each PR gets its own worktree and a fresh worker, so one review never influences the next. At the end you get one table and decide per PR: post the review, apply fixes on your own PRs, post a short no-findings note, or skip."

"And follow-up reviews only look at what changed since your last review, and check your earlier findings explicitly. On OpenShell, three follow-ups on the same day ended with 'no outstanding concerns', which is exactly what you want to tell an author quickly."

**Background:**

- The per-PR decision table at the end (example): #101, 2 Important, post review; #104, no findings, post "no findings". Other choices: apply fixes on your own PRs, or skip.
- Flow: every selected PR is reviewed in its own worktree before anything is posted or pushed. Then one decision table for all of them, then the actions run, each checking that the PR head hasn't moved. With `--unattended` the table is replaced by a fixed policy.
- Order and cap: least recently updated first, 10 PRs at most (`--limit`).
- Selection details: "review requested" includes requests to your teams. A cc-review marker posted by the PR's own author doesn't count as a review (unless that's you). `--search` stays inside the current repository's open PRs; drafts only with `draft:true` or `is:draft`. `--prs` is what `inbox` uses when you hand it several PRs.

- `--resume --unattended` is for scheduled runs: it picks up where the last run stopped and doesn't ask questions.
- Follow-up reviews are anchored on your last review that cc-review can verify, never on a guess.

**Transition:** "Every reviewer you saw today was found at run time. One of the places it looks is yours."

*Timing: 80 s*
-->
