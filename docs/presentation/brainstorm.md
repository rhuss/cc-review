# Brainstorming: cc-review: many reviewers, one verdict

**Date**: 2026-11-04
**Status**: Research complete, ready for outline

**Note**: No `presentation-config.md` yet. Run `/slidev:frame` to set duration, audience level and slide count before the outline.

---

## Abstract & Commitments

**Status**: No abstract yet; to be developed after the outline.

**Request (from the presenter)**: A tutorial for developers who want to use cc-review for their reviews. Cover its features, the review flow, how it works internally, what makes it special (multiple perspectives), how to extend it, how to add a new reviewer, and how to install it.

**Key commitments**:
1. Explain what cc-review is and which commands it offers (review, triage, inbox, issue)
2. Show the review flow end to end, from changed files to report and PR posting
3. Explain the multi-perspective design and why it beats a single reviewer
4. Open the hood: discovery, dispatch, merge, meta-review, gate, fix loop
5. Walk through adding a reviewer (prompt and command form)
6. Show installation for Claude Code, Codex and OpenCode

**Tone**: Hands-on developer tutorial. Real commands, real files, real output. Light on theory, one or two live demos.

**Initial angle**: "One AI reviewer is a single opinion. cc-review runs a panel, then makes the panel argue with itself before you see anything."

---

## Research Summary

### Local Materials

**Files reviewed**: README.md, CLAUDE.md, docs/reviewer-plugins.md, docs/standalone-guide.md (outline), review/core/commands/review.md (steps), review/core/agents/{preamble,meta-skeptic,meta-calibrator}.md, review/core/reviewers/{correctness.md, coderabbit/, greptile/}, review/config/profiles/, brainstorm/00-overview.md, review-findings.md (real report of PR #5), git history.

**What cc-review is**
- Multi-agent code review plugin for AI coding agents: Claude Code, Codex, OpenCode (plus an optional spec-kit extension).
- One distributable directory (`review/`) with a native manifest per harness; each harness ignores the others' manifests.
- Commands: `review` (code review + fix loop), `triage` (handle PR review comments), `inbox` (what waits for you in a repo), `issue` (assess a new issue, draft a maintainer reply), `init` (generate config).
- History: first commit 2026-08-03, 50 commits, current release v1.4.0. Grew out of the spex deep-review gate (spex still ships `deep-review` with the same 6 agents).

**The review flow (`review.md`, steps 1 to 8)**
1. Determine changed files (branch vs main, or `--pr N`; a PR on another branch is checked out into its own worktree under `.cc-review/pr-worktrees/`)
2. Discover reviewers (three layers), apply config, CLI flags, preconditions and tool detection
3. Dispatch all enabled reviewers in parallel: prompt reviewers as fresh-context subagents, command reviewers as external CLIs with timeouts
4. Merge and deduplicate (same file, overlapping lines, same category; keep longer description, record `also_reported_by`, take higher severity)
5. Meta-review: Skeptic and Calibrator run in parallel (skipped below 5 findings by default)
6. Gate check: Critical + Important = 0 passes; Notable never blocks
7. Autonomous fix loop: fix Critical/Important bottom-up per file, run tests (test failures become Critical "regression" findings), re-review only modified files, up to 3 rounds
8. Report (`review-findings.md`), optional PR posting after approval, console summary

**Multiple perspectives**
- Six built-in prompt reviewers, each with a role gate ("YOU ARE NOT RESPONSIBLE FOR ... Stay in your lane"): Correctness, Architecture & Idioms, Security, Production Readiness, Test Quality, Goal Alignment.
- Opt-in Gator: principal-engineer persona ported from NVIDIA OpenShell, with an evidence contract for blocking findings.
- Four external command reviewers: CodeRabbit CLI (on), Codex CLI (on), Copilot CLI (off), Greptile CLI (off, spends credits).
- Shared preamble for every prompt reviewer: anti-sycophancy, distrust of comments and commit messages, isolation (no git log, no plan docs: "judge what was built, not what was intended"), confidence >= 70 (>= 50 for Critical), every finding needs file, line, impact and concrete fix.
- Goal Alignment reads the PR description and linked issues and checks need and fit (shared criteria with `issue`).

**Meta-review (the "one verdict" part)**
- Skeptic: adversarial, assumes findings are wrong until code proves them right; reads 20+ lines of context; verdict confirmed, weak, or false-positive (removed).
- Calibrator: severity proportionality, contradictions between reviewers (CONTRA-N), per-agent precision and signal-to-noise scores.
- Conflict rule: if Skeptic confirms but Calibrator downgrades, the more conservative verdict wins. Weak findings drop one severity level.
- Failure of either critic is non-fatal: findings pass through unchanged with a warning.

**Internals**
- Harness-agnostic core (`review/core/`); command shims (SKILL.md, under 50 lines) only resolve the core directory and pass arguments.
- No hard-coded reviewer list: `discover-reviewers.sh` scans project (`.cc-review/reviewers/`), user (`~/.cc-review/reviewers/`) and bundled layers; higher layer replaces by name.
- Finding schema (JSON Schema) with severity Critical/Important/Minor/Notable; each reviewer's `severity_map` translates native severities exactly once, at merge.
- Config resolution: CLI flags > `--config` > `--profile` > project > user > built-in defaults > reviewer's `enabled`.
- Profiles: `quick` (correctness + security, 1 round), `thorough` (everything incl. Greptile), `ci`.
- Review hints: `.cc-review/review-hints.md` feeds project knowledge to every reviewer.

**Extending: adding a reviewer**
- Prompt reviewer: one Markdown file, five lines of frontmatter (`name`, `display_name`, `kind: prompt`, `category`) plus a prompt body. Discovered on the next run, preamble prepended, listed in the console summary. `--only accessibility` works immediately.
- Directory form: `<name>/reviewer.md` plus `references` inlined into the prompt (Gator uses it for its findings contract).
- Command reviewer: `detect`, optional `auth_check`, `invoke` template (`{base_branch}`, `{files}`, `{pr_number}`), `timeout_seconds`, `severity_map`, `output.format` = `json`, `delimited` or `parser`.
- Worked case: Greptile (added in v1.4.0): 17-line frontmatter plus a jq parser that maps `path/startLine/endLine/body/suggestion` to findings and anchors removed-line comments at the hunk start.
- Safety: a project reviewer edited by the change under review does not judge that change; project command reviewers run nothing until trusted by sha256 in `~/.cc-review/trusted-reviewers`; command reviewers are skipped in untrusted fork checkouts.

**Beyond a single review**
- `triage`: classifies PR threads as bot or human, bot profiles (`self_resolves`, `auto_resolve`) for CodeRabbit, Copilot, Greptile; author vs reviewer triage; never pushes for reviewer triage.
- Bulk mode: `review --bulk` reviews every PR waiting for you, each in its own worktree and fresh prep worker, then one decision table; `--unattended --resume` for scheduled jobs.
- Incremental follow-ups: second review of a PR only covers the delta since your last trusted review, verifies prior findings explicitly, and can conclude "no outstanding material concerns".
- `inbox`: read-only view of PRs, issues and Discussions grouped by who acts next.

**Real numbers available (dogfooding)**
- PR #5 review (repository inbox): 10 reviewers discovered, 9 completed; 33 findings, 12 fixed over 3 rounds; 6 Important, 5 fixed. Example finding: Discussions in non-answerable categories always flagged "uncertain" (correctness, confidence 95, fixed).
- Agent quality table from a real run: correctness precision 1.00, production 0.90, architecture 0.85 (8 findings), test-quality 0.60 (7 findings). Good material for "the panel grades itself".

### Web Research

**Caveat**: most performance numbers below are vendor-reported. The independent evidence (arXiv field studies) mostly documents how noisy review bots are. Pricing for Greptile, Qodo, Graphite and Bugbot comes from conflicting aggregators; re-check before putting it on a slide.

#### Competitor landscape (Nov 2026)

| Tool | Delivery | Single vs multi | Local pre-push | Extensibility |
|---|---|---|---|---|
| CodeRabbit | PR bot, CLI, IDE | Review + verification agents, 50+ linters | Yes (CLI, staged/unstaged) | Path instructions |
| GitHub Copilot review | PR bot, IDE, gh CLI | Single agentic reviewer (effort levels) | IDE yes | `copilot-instructions.md`, `AGENTS.md`, skills |
| Greptile | PR bot, CLI | Not verified | Committed only | `greptile.json`, `.greptile/rules.md` |
| OpenAI Codex | CLI `/review`, cloud | Single agent, P0/P1 only on GitHub | Yes | `AGENTS.md` review rules |
| Claude Code Review (managed) | GitHub App | Agent team + verification + ranking | No | `REVIEW.md`, `CLAUDE.md` |
| Claude `/code-review` (local) | CLI skill | Subagent (internals undocumented) | Yes, incl. uncommitted | `CLAUDE.md` |
| Qodo 2.0 / PR-Agent | PR bot, CLI, IDE | Expert agents + judge | Likely | Rules config |
| Graphite Agent | PR bot | Not verified | Not verified | Custom rules |
| Cursor Bugbot | PR bot, Cursor | Was 8 passes + majority vote + validator | Yes | `.cursor/BUGBOT.md` |

**Positioning gap**: every competitor runs one vendor's reviewer. Few run locally before push. None combines reviewers from several vendors under one dedup and meta-review. cc-review runs CodeRabbit, Codex, Copilot and Greptile *as panel members* next to its own lanes, and the reviewer set is user-extensible Markdown.

#### Evidence for multiple perspectives
- Cursor Bugbot: 8 parallel passes with shuffled diff order, majority vote, validator; resolution rate 52% to over 70% (vendor). [cursor.com/blog/building-bugbot](https://cursor.com/blog/building-bugbot)
- Anthropic Code Review: agent team + verification; PRs with substantive comments 16% to 54%, under 1% findings marked incorrect (vendor). [claude.com](https://claude.com/resources/articles/code-review)
- Cubic: specialized micro-agents cut false positives 51% at equal recall (vendor). [cubic.dev](https://cubic.dev/blog/learnings-from-building-ai-agents)
- CodeX-Verify: 4 specialized agents, accuracy 32.8% to 72.4% (small sample, n=29). [arXiv 2511.16708](https://arxiv.org/abs/2511.16708v3)
- Qodo 2.0: experts + judge, F1 60.1% on own benchmark (vendor). [qodo.ai](https://www.qodo.ai/blog/introducing-qodo-2-0/)

#### Evidence on noise and trust (independent)
- CodeRabbit field study: 31,073 reviews in 239 repos; 36.4% accepted, 56.3% rejected, false positives the main reason. [arXiv 2607.03316](https://arxiv.org/abs/2607.03316)
- 16 AI review Actions, ~22k comments: AI comments addressed 0.9% to 19.2% vs ~60% for human comments (verify in full paper). [arXiv 2508.18771](https://arxiv.org/abs/2508.18771)
- Beko (ICSE 2025): 73.8% of comments resolved, but PR closure time rose from 5h52m to 8h20m. [arXiv 2412.18531](https://arxiv.org/abs/2412.18531)
- More bot comments per PR means lower average relevance. [arXiv 2604.24450](https://www.emergentmind.com/papers/2604.24450)
- Stack Overflow 2025: 46% distrust AI accuracy; 66% cite "almost right, but not quite".

#### Evidence for judge / verification passes
- HubSpot Sidekick: judge agent filters comments; >80% thumbs-up (vendor). [product.hubspot.com](https://product.hubspot.com/blog/automated-code-review-the-6-month-evolution)
- Proposer + LLM ranker: fix rejection rate 55% to 48%. [arXiv 2309.12938](https://arxiv.org/pdf/2309.12938)
- Benchmark claims (Martian Code Review Bench) shift month to month; not neutral numbers.

**Takeaway for the talk**: the industry converged on "several focused passes + a skeptical filter" because single bots are noisy. cc-review applies the same pattern across vendors, locally, and lets you add panel members.

---

## Key Themes & Messages

1. **A panel beats a single reviewer**: specialized lanes plus external tools find different things; dedup keeps the noise down.
2. **Trust through adversarial filtering**: the meta-review argues with the findings before you see them; precision is measured per reviewer.
3. **Review that closes the loop**: findings are fixed, tests rerun, and only modified files re-reviewed, up to three rounds.
4. **Extensible by Markdown**: a new reviewer is one file; an external tool is a frontmatter block plus an optional parser.
5. **Runs where you work**: the same core in Claude Code, Codex and OpenCode; local before push, then PR posting, triage and inbox after.

**Primary message**: cc-review gives every change a panel of focused reviewers and a skeptic that filters them, and you can add your own reviewer with one Markdown file.

**Supporting messages**:
1. Install in two commands and run `/review` on any branch.
2. The pipeline is transparent: every reviewer shows as completed, disabled, skipped or failed, and every removed finding is logged with a reason.
3. Your team's knowledge belongs in a reviewer or in review hints, not in your head.

**Call to action**: Install from `rhuss/cc-rhuss-marketplace`, run `/review --profile quick` on your next branch, then write one project reviewer for a rule your team keeps repeating in PR comments.

---

## Visual Opportunities

**Diagrams**
- Review pipeline: changed files -> discover -> parallel fan-out (6 prompt + N command) -> merge/dedup -> Skeptic || Calibrator -> gate -> fix loop -> report/PR. (Mermaid flowchart; centerpiece)
- Fix loop cycle: fix -> test -> re-review modified files -> gate, max 3 rounds. (Mermaid)
- Three discovery layers stacked (project > user > bundled) with override by name. (Excalidraw)
- Meta-review: Skeptic and Calibrator side by side, conflict rule "conservative wins". (Excalidraw)
- Harness architecture: Claude Code / Codex / OpenCode shims -> one core. (Mermaid or Excalidraw)
- Command reviewer anatomy: detect -> auth_check -> invoke -> parse -> severity_map. (Mermaid sequence)

**Code / screenshots**
- Annotated reviewer file (accessibility example, 5-line frontmatter).
- Greptile `reviewer.md` frontmatter next to `parse.sh`.
- Console summary of a real run (reviewer status table).
- Excerpt of `review-findings.md` (summary table + one finding).
- Agent quality score table.

**Data**
- Findings found/fixed/remaining from PR #5 (bar chart or table).
- Per-agent precision (bar chart).

---

## Rough Structure Ideas

**Opening (~10%)**
- Hook: one AI reviewer is one opinion, and often a noisy one. Field data: 56% of CodeRabbit suggestions rejected, mostly false positives (arXiv 2607.03316). Show a bot comment flood vs a calibrated cc-review summary.
- Positioning slide: landscape table reduced to "single vendor / cloud / PR-only" vs cc-review "multi-vendor panel / local first / extensible".
- What cc-review is in one slide.
- Command overview: all five commands with one line each, and where they sit in a PR's life (before push, on the PR, after feedback, across the repo):
  - `review`: multi-reviewer code review with fix loop (branch, `--pr`, `--bulk`, follow-ups)
  - `triage`: handle bot and human comments on a PR (author or reviewer side)
  - `inbox`: what waits for you in a repository, grouped by who acts next
  - `issue`: assess a new issue for need and fit, draft a maintainer reply
  - `init`: generate config, list discovered reviewers and their state

**Main content (~80%)**
- Section 1, Get started: install (marketplace / Codex / OpenCode), first `/review`, `--pr`, profiles, key flags. Demo 1.
- Section 2, The flow: pipeline diagram, report anatomy, gate, fix loop, PR posting.
- Section 3, Many perspectives: six lanes + preamble rules + external tools; dedup; meta-review Skeptic and Calibrator; agent scores.
- Section 4, Under the hood: harness shims -> core, discovery layers, finding schema, config resolution.
- Section 5, Beyond one review: triage (bot profiles, author vs reviewer side), issue assessment, inbox, plus bulk mode and incremental follow-ups for `review`.
- Section 6, Extend it (slides only, no live demo): how to write a prompt reviewer in one file (accessibility or "team rules" example), command reviewer with Greptile as the worked example, trust model.

**Closing (~10%)**
- Recap of the three takeaways, call to action, links, Q&A.

---

## Raw Notes & Ideas

- Demo safety: seed a tiny repo with a known bug (missing nil check + leaked file handle) so the demo is fast and deterministic; use `--only correctness,security --no-external` to keep it under a minute or two.
- Pre-record the full-panel run (external tools take ~200 s for Greptile) and show the report instead of waiting live.
- Cost honesty: each prompt reviewer is a subagent; a full run with external tools costs real tokens and credits. `quick` profile is the cheap path. Consider a slide with rough token cost if measured numbers exist.
- "Stay in your lane" quote from a reviewer prompt makes a nice slide.
- The preamble's isolation rule ("judge what was built, not what was intended") is a memorable line.
- Question to answer: does the meta-review really cut false positives? Collect removed-finding counts from a few real runs before the talk.
- Open question for the audience: should critics see the source agent (bias) or not (from brainstorm #04).
- Mention spec-aware review (`--spec`) briefly for spex users.

---

## References

**Local sources**
- README.md
- docs/reviewer-plugins.md
- docs/standalone-guide.md
- review/core/commands/review.md
- review/core/agents/preamble.md, meta-skeptic.md, meta-calibrator.md
- review/core/reviewers/ (correctness.md, coderabbit/, greptile/, gator/)
- review/config/profiles/
- brainstorm/00-overview.md
- review-findings.md (PR #5 report)

**Web sources** (best five)
- CodeRabbit field study: https://arxiv.org/abs/2607.03316
- AI vs human comment addressing: https://arxiv.org/abs/2508.18771
- Building a better Bugbot: https://cursor.com/blog/building-bugbot
- Anthropic Code Review: https://claude.com/resources/articles/code-review
- HubSpot Sidekick judge agent: https://product.hubspot.com/blog/automated-code-review-the-6-month-evolution

**Keywords researched**: AI code review competitor landscape; multi-agent / ensemble LLM code review; false positives and review-bot noise; LLM-as-judge verification

---

## Next Steps

1. Review this brainstorm document
2. Run `/slidev:frame` to set duration, audience level and slide count
3. Run `/slidev:outline` to create the structured outline
4. Develop slides from the outline

---

## Dogfooding Evidence (collected 2026-11-04)

Raw data: `data/openshell-findings-labeled.jsonl` (per-finding outcomes), `data/local-reports-aggregate.json` (local report parse).

**NVIDIA/OpenShell (public PRs)**: 30 cc-review reviews on 20 PRs, 208 inline findings.
- Addressed 64% (133): 77 fixed and verified, 40 fixed per author, 16 outdated by code change
- Moved to follow-up 8%, resolved without reply 13%, no response yet 13% (mostly reviews from Oct 28 / Nov 2), withdrawn 1.4%, rejected 0.5%
- Excluding no-response: 73% addressed, 82% addressed or deferred
- By severity: Important 87% addressed (34/39), Minor 66%, Notable 19% (informational)
- 29 findings deliberately held back at the posting step across 7 runs; 7 runs failed the gate
- Examples: #5082 double percent-decoding of OTLP headers (codex); #5083 credentials in startup log (security); #4789 mismatched trace IDs, CodeRabbit silent in the same run (gator)

**Local reports (140 with summary tables, 2026-03-29 to 2026-11-03; 133 from the spex deep-review predecessor)**
- Critical + Important fixed: 547 of 670 (82%); Minor 36%
- Meta-review (6 reports, 128 findings): 0 removed as false positive, 17 recalibrated (13%, all downward where stated), 10 weak verdicts, 1 contradiction
- 17% of findings reported by more than one reviewer; CodeRabbit 72 unique findings, Codex 14
- Mean precision (Calibrator): correctness 0.90, production 0.90, architecture 0.87, security 0.87, gator 0.85, codex 0.78, goal-alignment 0.74, coderabbit 0.67 (n=1), test-quality 0.65

**Open question for a follow-up brainstorm**: the Skeptic never removes findings, while the Calibrator scores some lanes at 0.65 precision. Candidate improvements: blind refutation, reachability proof for "confirmed", cross-vendor second skeptic, labeled eval set from OpenShell outcomes and held-back findings.
