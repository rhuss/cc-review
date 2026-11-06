# cc-review: many reviewers, one verdict

**Session:** 60 minutes (live demo with an embedded 30 minute slide block)
**Slide block:** 19 slides at ~90 s = 28.5 min, plus ~1.5 min buffer (pipeline slide, transitions); 5 demo bridge slides not counted
**Audience:** Developers who use AI coding agents daily (intermediate), internal session
**Primary message:** cc-review gives every change a panel of focused reviewers and a skeptic that filters them, and you can add your own reviewer with one Markdown file.

---

## Demo kickoff (bridge, 2 slides, 0-5 min)

### Slide B1: cc-review: many reviewers, one verdict
- Subtitle: multi-agent code review for Claude Code, Codex and OpenCode
- Speaker, date
- Visual: section-opener image (a review panel / jury bench)

### Slide B2: A review starts now and finishes during the talk
- The command: `/review --pr <n> --profile thorough`
- Watch the reviewer status table fill: completed, skipped, failed
- "We come back to the results in 30 minutes"
- Visual: terminal screenshot of the kickoff

---

## Introduction (3 slides, ~4.5 min)

### Slide 1: Most AI review comments get ignored
- 56% of CodeRabbit suggestions rejected (31k reviews), false positives the main reason
- AI comments addressed 1-19% of the time, human comments ~60%
- More comments per PR, less relevance per comment
- Visual: big-number layout; sources in footer (arXiv 2607.03316, 2508.18771)

### Slide 2: cc-review runs a panel, then makes it argue
- Focused reviewers plus external tools, in parallel
- A skeptic and a calibrator filter findings before you see them
- A fix loop resolves what matters, then re-reviews
- Same pattern the industry converged on (Cursor Bugbot, Anthropic Code Review), but across vendors and locally, before you push
- Visual: icon strip (panel -> skeptic -> fix -> report)

### Slide 3: Five commands: one PR flow, one repo view
- `review`: panel review with fix loop
- `triage`: handle bot and human PR comments
- `inbox`: what waits for you in a repository
- `issue`: assess a new issue, draft a reply
- `init`: generate config, list reviewers
- Visual: two lanes. A pull request (init, review, review --pr, triage, left to right) and the repository at any time (inbox, issue, no arrows); doubles as agenda

**Transition:** "Here is how you get to where I was five minutes ago."

---

## Section 1: Get started (2 slides, ~3 min)

### Slide 4: Two commands to install
- `/plugin marketplace add rhuss/cc-rhuss-marketplace`
- `/plugin install cc-review@cc-rhuss-marketplace`
- Codex and OpenCode: one line each (marketplace add / `install.sh`)
- Needs `jq`, `yq`, `gh`, Python 3.9+; external CLIs optional
- Visual: code block

### Slide 5: Three ways to run your first review
- `/review`: your branch against main
- `/review --pr 42`: a PR, in its own worktree
- `/review --profile quick`: correctness + security, one fix round, the cheap path
- Profiles: `quick`, `thorough`, `ci`; all flags in backup
- Visual: code block with one-line annotations

**Transition:** "So what happens after you press enter? Exactly what is running right now."

---

## Section 2: Many reviewers (3 slides, ~5 min)

### Slide 6: What is running right now (centerpiece, ~2-3 min)
- Discover -> Dispatch in parallel -> Merge -> Meta-review -> Gate and fix -> Report
- Revealed stage by stage (v-click)
- Speaker notes: prompt reviewers are fresh-context subagents, command reviewers are CLIs with timeouts; dedup rule (same file, overlapping lines, same category, keep the stronger, record `also_reported_by`)
- Visual: Mermaid pipeline flowchart, five stages

### Slide 7: Six lanes and four outside voices
- Correctness, Architecture & Idioms, Security, Production Readiness, Test Quality, Goal Alignment
- External: CodeRabbit, Codex, Copilot, Greptile
- Each lane has a role gate: "Stay in your lane."
- Footnote: opt-in Gator, a principal-engineer persona from NVIDIA OpenShell
- Visual: grid of 6 lane tiles plus one "External" box

### Slide 8: Every reviewer judges what was built, not what was intended
- No praise, no quota; zero findings is a valid result
- Distrust comments, commit messages and test names; read the code
- No git log, no plan docs
- Confidence >= 70; every finding needs file, line, impact and fix
- Visual: quote card for the title line

**Transition:** "Ten reviewers produce a lot of findings. Now the panel argues with itself."

---

## Section 3: One verdict (4 slides, ~6.5 min)

### Slide 9: Two critics check every finding before you see it
- Skeptic: tries to refute each finding against the code; marks it confirmed, weak or false positive
- Calibrator: checks severity, finds contradictions between reviewers; lower severity wins
- Measured (6 meta-reviewed runs, 128 findings): 13% downgraded, almost never upgraded; the Skeptic removed none outright
- You stay the last filter: on OpenShell, 29 findings were held back at the posting step
- Visual: two columns (Skeptic | Calibrator) merging into "one verdict" (Excalidraw)
- Speaker notes: be candid that the Skeptic rarely removes; the reviewer rules already demand evidence, and improving the Skeptic is ongoing work

### Slide 10: The panel grades itself on every run
- Precision and signal-to-noise per reviewer, written to every report
- Mean over 6 runs: correctness 0.90, production 0.90, architecture 0.87, security 0.87, gator 0.85, codex 0.78, goal-alignment 0.74, test-quality 0.65
- Test-quality is lowest in every run, so it is the first lane to tune
- Visual: horizontal bar chart of per-reviewer precision

### Slide 11: Findings get fixed, tested and re-reviewed
- Gate: Critical + Important = 0 passes; Minor and Notable never block
- Fix bottom-up per file, run tests; a failing test becomes a Critical finding
- Re-review only the modified files, up to 3 rounds
- 140 local reports since March: 82% of Critical and Important findings fixed (547 of 670)
- Visual: cycle diagram (fix -> test -> re-review -> gate), Mermaid

### Slide 12: On real PRs, two thirds of the findings get fixed
- NVIDIA/OpenShell: 30 cc-review reviews on 20 PRs, 208 inline findings
- 64% addressed, 87% of the Important ones; 2% withdrawn or rejected
- Leaving out unanswered (mostly last week's) findings: 73% addressed, 82% addressed or moved to a follow-up
- Caught: double percent-decoding of OTLP headers (Codex, #5082); credentials printed to the startup log (security, #5083); mismatched trace IDs that CodeRabbit missed in the same run (gator, #4789)
- Visual: big number "64%" plus a stacked outcome bar; three example cards
- Speaker notes: not directly comparable to the 36% acceptance in the CodeRabbit field study (different method, one reviewer, one project); "outdated" counted as addressed

**Transition:** "A review is one moment in a PR's life. Here is what comes before and after."

---

## Section 4: Beyond one review (2 slides, ~3 min)

### Slide 13: Triage, inbox and issue handle the rest of the PR's life
- `triage`: bot profiles for CodeRabbit, Copilot, Greptile; drafts replies, never pushes for reviewers
- `inbox`: PRs, issues, Discussions grouped by who acts next
- `issue`: need, fit and value, plus a reply draft; never posts
- "All three live after the slides"
- Visual: three cards

### Slide 14: Review many PRs at once, and only what changed since last time
- `review --bulk`: every PR waiting for you, one decision table at the end
- Follow-ups cover only the delta since your last review and verify earlier findings
- Visual: decision table mock (PR, findings, action)

**Transition:** "Every reviewer you saw today was discovered at run time. One of those places is yours."

---

## Section 5: Make it yours (4 slides, ~6 min)

### Slide 15: One core, three agents, reviewers discovered at run time
- `review/` ships native manifests for Claude Code, Codex and OpenCode
- Thin shims (under 50 lines) hand off to one harness-agnostic core
- No reviewer list in the code: project > user > bundled layers, higher replaces by name
- Visual: diagram with three shims feeding the core, and the three reviewer layers stacked beside it

### Slide 16: A reviewer is one Markdown file
- Drop `<name>.md` into `.cc-review/reviewers/` or `~/.cc-review/reviewers/`
- Frontmatter: `name`, `display_name`, `kind: prompt`, `category`
- Body: role, scope, checklist; shared preamble added automatically
- Next run: in the status table; `--only <name>` works at once
- Visual: annotated code block (team-rules or accessibility example)

### Slide 17: Wrapping an external tool takes a frontmatter block
- Greptile as the worked example
- Annotations on ~8 key lines: `kind: command`, `detect`, `auth_check`, `invoke`, `timeout_seconds`, `severity_map`, `output.format: parser`
- Parser excerpt: a few lines of jq mapping the tool's JSON to findings
- Visual: annotated frontmatter, parser excerpt below (no bullet text on the slide)

### Slide 18: Project reviewers run only after you trust them
- A reviewer edited by the change under review does not judge that change
- Project command reviewers run nothing until trusted by sha256 in `~/.cc-review/trusted-reviewers`
- Command reviewers skip untrusted fork checkouts
- Visual: small flow (project reviewer -> trusted? -> runs)

**Transition:** "Let's sum up before we check on our review."

---

## Closing (1 slide, ~1.5 min)

### Slide 19: Three takeaways
- A panel plus a skeptic beats one noisy bot
- The review closes the loop: fix, test, re-review
- Your team's rules belong in a reviewer file
- Visual: three icons

**Transition:** "Let's see what the panel found."

---

## Back to the demo (bridge, 3 slides)

### Slide B3: The results (35-45 min)
- Look for: reviewer status table, Skeptic removals, recalibrated severities, fix rounds, posting prompt
- Invite questions while walking through the report
- Visual: checklist

### Slide B4: Live: inbox, triage, issue (45-55 min)
- `inbox` on the demo repository
- `triage --pr <n>` on a PR with bot comments
- `issue <n>` on a fresh issue
- Visual: three command lines

### Slide B5: Try it this week
- Install from `rhuss/cc-rhuss-marketplace`
- Run `/review --profile quick` on your next branch
- Write one reviewer for a rule your team keeps repeating
- Links: github.com/rhuss/cc-review, docs/extras/reviewer-plugins.md; Q&A
- Visual: QR code to the repository

---

## Backup slides (not counted)

- Competitor landscape table (delivery, single vs multi, local, extensibility)
- Research numbers with sources (multi-agent and judge evidence, vendor vs independent)
- Finding schema fields, severities and `severity_map` translation at merge
- Config resolution order (CLI flags > `--config` > `--profile` > project > user > defaults) and the full flag reference for `review` and `triage`
- Cost: prompt reviewers are subagents, external tools spend credits; `quick` profile as the cheap path

---

## Notes

**Transition Points:**
- Kickoff -> Intro: "While the panel works, let's look at why we need a panel at all."
- Intro -> Get started: "Here is how you get to where I was five minutes ago."
- Get started -> Many reviewers: "So what happens after you press enter? Exactly what is running right now."
- Many reviewers -> One verdict: "Ten reviewers produce a lot of findings. Now the panel argues with itself."
- One verdict -> Beyond one review: "A review is one moment in a PR's life. Here is what comes before and after."
- Beyond one review -> Make it yours: "Every reviewer you saw today was discovered at run time. One of those places is yours."
- Make it yours -> Closing: "Let's sum up before we check on our review."
- Closing -> Demo: "Let's see what the panel found."

**Visual Opportunities:**
- B1: Section-opener image (review panel / jury bench)
- Slide 1: Big-number statistics
- Slide 3: PR lifecycle timeline with commands
- Slide 6: Pipeline flowchart (Mermaid, v-click), centerpiece
- Slide 7: Lane grid
- Slide 9: Skeptic/Calibrator diagram (Excalidraw)
- Slide 10: Per-reviewer precision bar chart
- Slide 11: Fix loop cycle (Mermaid)
- Slide 12: Outcome bar for 208 OpenShell findings, three example cards
- Slide 15: Shims -> core plus layer stack (Excalidraw)
- Slides 16/17: Annotated code blocks
- Section openers: images for "Many reviewers", "One verdict", "Make it yours"

**Time Allocation (slide block):**
- Introduction: 4.5 min (3 slides)
- Section 1, Get started: 3 min (2 slides)
- Section 2, Many reviewers: 5 min (3 slides, pipeline slide ~2.5 min)
- Section 3, One verdict: 6.5 min (4 slides)
- Section 4, Beyond one review: 3 min (2 slides)
- Section 5, Make it yours: 6 min (4 slides)
- Closing: 1.5 min (1 slide)
- **Total: 29.5 minutes (19 slides)**, ~0.5 min buffer for transitions, plus 5 bridge slides in the demo blocks

**Preparation:** see `demo-prep.md` (demo targets, checklist, fallbacks).
