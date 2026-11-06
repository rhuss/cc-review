---
layout: default
---

# Triage, inbox and issue handle the rest

<div class="flex flex-col justify-center" style="height: calc(100% - 5rem)">

<div class="grid grid-cols-3 gap-6">
<div class="cmd-box" style="background: #ffd8a8; border-color: #e8590c">
  <div class="cmd">triage</div>
  <div>Bot and human comments; drafts replies</div>
</div>
<div class="cmd-box" style="background: #eebefa; border-color: #9c36b5">
  <div class="cmd">inbox</div>
  <div>PRs, issues, Discussions by who acts next</div>
</div>
<div class="cmd-box" style="background: #eebefa; border-color: #9c36b5">
  <div class="cmd">issue</div>
  <div>Need, fit, value; reply draft</div>
</div>
</div>

<div class="mt-10 text-center opacity-80">More on this in the demo</div>

</div>

<style>
.cmd-box {
  padding: 1.2rem 1.4rem;
  border-radius: 0.75rem;
  border: 2px solid;
  color: #1e1e1e;
  font-size: 1.25rem;
}
.cmd {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-weight: 700;
  font-size: 1.6rem;
  margin-bottom: 0.8rem;
}
</style>

<!--
**Goal:** a short preview of the three commands shown live later.

**Say:**

"Three more commands, and you'll see all of them live in a few minutes, so just the idea here."

"`triage` handles the comments on a PR, from bots and from humans. It knows how each bot behaves, for example whether CodeRabbit resolves its own threads, and drafts replies. As the author it can fix things; as a reviewer it only checks the code and drafts."

"`inbox` answers: what's waiting for me in this repository? Pull requests, issues, discussions, sorted by who has to act next. It starts with a table of what needs your attention, and for each item a short situation and its own take, which may well be 'no reply needed'. If you want, it then walks you through the items one by one, and for any of them it can start `review`, `triage` or `issue` right there."

"And `issue` looks at a new issue and asks: is the need real, does it fit the project, is it worth doing? Then it drafts a friendly reply."

**Background:**

- None of the three posts anything on its own. Drafts only, and you decide.
- `inbox` is read-only and gives evidence for every grouping (who commented last, which review is open).
- Report layout: "Needs your attention" table (item, what, why you, certainty, next step), one detail block per item with situation, "My take" and evidence links, then short lists for "waiting on others" and "no current action", and a compact coverage account (limits are never hidden).
- Guided tour: opt-in at the end of the report, only in an interactive run with attention items. Up to five items per batch, one at a time; each item gets a focused briefing from the collected snapshot (a subagent per item where the harness supports it), nothing is re-fetched.
- Handoff: inside a local checkout, a toured PR can go straight to `review --pr N` or `triage --pr N`, an issue to `issue`; several PRs together go to `bulk` as one list. Discussions only get a suggestion. Where the harness can't chain commands, it prints the exact command instead. The handed-off command does its own confirmations; `inbox` itself never writes.

**Transition:** "One more thing about review itself: scale, and time."

*Timing: 80 s*
-->
