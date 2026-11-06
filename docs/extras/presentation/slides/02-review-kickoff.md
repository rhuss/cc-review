---
layout: default
---

# A review starts now and finishes during the talk

```bash
/cc-review:review --pr <n> --profile thorough
```

<div class="term mt-10">
<div class="term-head">Gate: <span class="ok">PASS</span> (after fix round 1)</div>
<table>
<thead><tr><th>Reviewer</th><th>Found</th><th>Fixed</th><th>Remaining</th><th>Status</th></tr></thead>
<tbody>
<tr><td>Correctness</td><td>4</td><td>4</td><td>0</td><td class="ok">completed</td></tr>
<tr><td>Production Readiness</td><td>3</td><td>2</td><td>1</td><td class="ok">completed</td></tr>
<tr><td>CodeRabbit</td><td>3</td><td>2</td><td>1</td><td class="ok">completed</td></tr>
<tr><td>Greptile</td><td>-</td><td>-</td><td>-</td><td class="warn">skipped (not logged in)</td></tr>
</tbody>
</table>
</div>

<div class="mt-3 opacity-70 text-center">Illustrative result: real runs look different</div>

<style>
.slidev-code {
  font-size: 1.6rem !important;
  line-height: 1.4 !important;
  padding: 0.8rem 1.2rem !important;
  margin-top: 2rem !important;
}
.term {
  background: #1e1e1e;
  color: #e5e7eb;
  border-radius: 0.5rem;
  padding: 0.7rem 1.2rem;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
.term-head { margin-bottom: 0.3rem; }
.term table { width: 100%; border-collapse: collapse; }
.term th, .term td {
  font-size: 1.25rem !important;
  padding: 0.1rem 0.6rem;
  border: none;
  text-align: right;
  line-height: 1.25;
  white-space: nowrap;
}
.term th { color: #9ca3af; font-weight: 600; border-bottom: 1px solid #4b5563; }
.term th:first-child, .term td:first-child { text-align: left; }
.term th:last-child, .term td:last-child { text-align: left; }
.term .ok { color: #4ade80; }
.term .warn { color: #fbbf24; }
.term .dim { color: #9ca3af; }
</style>

<!--
**Goal:** the review is running, and everyone knows when the results come.

**Say:**

"Before I explain anything, let me give the panel some work. This is a real pull request, and I'm starting a thorough review on it right now."

*(switch to the terminal, run the command, wait until the reviewer list appears)*

"You see every reviewer cc-review found for this run, also the ones that won't run, each with a reason. Nothing is left out silently. If a tool isn't logged in, you see that here, instead of wondering later why it was so quiet."

"At the end you'll get a table like the one on the slide: one row per reviewer, what it found, what got fixed, what's still open. These numbers are made up. The real ones come in about 30 minutes."

**Background:**

- `thorough` is the biggest profile: all six built-in reviewers plus CodeRabbit, Codex, Copilot and Greptile, a confidence threshold of 80 instead of 70, and more fix rounds. Good for a demo, too expensive for every push.
- Gate PASS means no finding at a blocking severity is left. In `thorough`, Minor findings also block, so what remains is Notable observations.
- The review runs on its own in that terminal. I don't touch it until minute 35.

**Remaining rows of the illustration table (found / fixed / remaining, all completed):**

- Architecture & Idioms: 2 / 1 / 1
- Security: 1 / 1 / 0
- Test Quality: 2 / 2 / 0
- Goal Alignment: 1 / 0 / 1
- Codex: 2 / 2 / 0
- Copilot: 1 / 1 / 0

**If asked:**

- *Why not wait for it?* A thorough run with fix rounds takes 15 to 30 minutes. That's the honest cost of a full panel, and the reason `quick` exists.

**Transition:** "While the panel works, let's look at why we need a panel at all."

*Timing: part of the 5 minute kickoff*
-->

