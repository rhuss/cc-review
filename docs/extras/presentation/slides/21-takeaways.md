---
layout: center
class: text-center
---

# Three takeaways

<div class="tk-grid">
  <div class="tk" style="background: #a5d8ff; border-color: #1971c2">
    <ph-users-three class="tk-icon" />
    <div class="tk-label">Diversity wins</div>
    <div class="tk-body">More agents, more vendors, fewer blind spots</div>
  </div>
  <div class="tk" style="background: #ffd8a8; border-color: #e8590c">
    <ph-scales class="tk-icon" />
    <div class="tk-label">Critics</div>
    <div class="tk-body">Every finding checked against the code before you see it</div>
  </div>
  <div class="tk" style="background: #b2f2bb; border-color: #2f9e44">
    <carbon-renew class="tk-icon" />
    <div class="tk-label">Your code</div>
    <div class="tk-body">On your code: fix, test, re-review</div>
  </div>
</div>

<style>
.tk-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1.5rem;
  margin: 2.5rem auto 0;
  max-width: 54rem;
}
.tk {
  border: 2px solid;
  border-radius: 0.9rem;
  padding: 1.6rem 1.4rem;
  min-height: 13rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  color: #1e1e1e;
}
.tk-icon { font-size: 2.6rem; margin-bottom: 0.6rem; }
.tk-label { font-size: 1.7rem; font-weight: 700; margin-bottom: 0.9rem; }
.tk-body { font-size: 1.4rem; line-height: 1.4; }
</style>

<!--
**Goal:** three sentences people remember, then back to the demo.

**Say:**

"Three things to take home."

"One: diversity wins. Every reviewer has blind spots, and models from the same vendor share them. More focused agents from different vendors means more perspectives: Codex found the double decoding, Gator the trace ID mismatch CodeRabbit missed. On real PRs, two thirds of the findings got fixed."

"Two: critics. Before a finding reaches you, it's checked against the code and its severity is calibrated. Honestly, that part still has room to grow, but every change is logged with a reason."

"Three: on your own code, a review shouldn't end in a report. You pick what to fix, and cc-review fixes, tests and reviews again. On other people's PRs, it posts the review instead."

**If asked:**

- *What about team-specific rules?* Every comment your team keeps repeating is a reviewer waiting to be written: one Markdown file (slide 18), and it joins the panel on the next run.

**Transition:** "Let's see what the panel found." *(switch to the terminal; run sheet in `demo-prep.md`)*

*Timing: 90 s*
-->

