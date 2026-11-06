---
# Presentation Framing Configuration
# Generated: 2026-11-04

# Core Parameters
session_minutes: 60 # whole session: live demo + slides + Q&A
duration_minutes: 30 # slide block, presented while the live review runs (27 min content + 3 min buffer)
time_per_slide_seconds: 90
target_slide_count: 18 # slide block only
slide_count_range: [15, 21]
demo_bridge_slides: 5 # B1 title, B2 kickoff, B3 results, B4 live commands, B5 try it (not counted)
# Audience
audience: "Developers"
skill_level: "intermediate"
context: "internal"
# Style
style: "technical"
theme: "seriph"
visuals: "full" # diagrams plus images for section openers
# Timing Details
opening_slides: 3
opening_time_seconds: 90
content_slides: 14
content_time_seconds: 90
closing_slides: 1
closing_time_seconds: 90
backup_slides_recommended: 3-5
balance:
  boxes:
    palette: default
    roles:
      main: '#3b82f6'
      risk: '#f97316'
      context: '#64748b'
      takeaway: '#8b5cf6'
# Calculation Notes
# Formula: (duration × 60) / time_per_slide = target_slides
# (27 × 60) / 90 = 18 slides, plus 3 min buffer for the pipeline slide and transitions
# Flexibility: ±20% = 15-21 slides
---

# Presentation Scope

**Working Title**: cc-review: many reviewers, one verdict

## Session Format

The slides are embedded in a one hour live demo. A real review is started at the beginning and runs in the background while the slides are presented; its results are shown afterwards, followed by the other commands live.

| Time | Block | Content |
|------|-------|---------|
| 0-5 min | Demo: kickoff | Title slide, start a full-panel review (`/review --pr <n> --profile thorough`), show the reviewer status table appearing |
| 5-35 min | Slides | ~18 slides while the review runs (pacing below) |
| 35-45 min | Demo: results | Console summary, `review-findings.md`, meta-review removals and calibrations, fix loop rounds, PR posting |
| 45-55 min | Demo: more commands | `inbox`, `triage`, `issue` live |
| 55-60 min | Wrap-up | Call to action, links, Q&A |

**Timing constraint**: the review started at minute 5 must be finished by minute 35. A thorough run with external tools and up to three fix rounds can take longer; pick a PR of suitable size and do a dry run beforehand to measure. Preparation, demo targets and fallbacks are in `demo-prep.md`.

## Duration & Pacing

- **Slide block**: 30 minutes
- **Time per slide**: ~90 seconds (intermediate developers, technical content)
- **Target slides**: 18 (range 15-21), plus 5 demo bridge slides; ~3 min buffer
- **Backup slides**: 3-5 (config resolution, finding schema, trust model details, competitor table, research numbers)

## Audience

- **Who**: Developers who use AI coding agents daily (Claude Code, Codex, OpenCode)
- **Skill level**: Intermediate; no need to explain plugins, slash commands or subagents
- **Context**: Internal presentation
- **Expectations**: How to use cc-review on their own reviews, why the multi-reviewer design is worth it, how to add a reviewer for their team's rules

## Style Preferences

- **Style**: Technical/Developer, code-focused with syntax highlighting
- **Slidev theme**: seriph
- **Visual richness**: Diagrams (pipeline, fix loop, discovery layers, meta-review, harness architecture) plus images for section openers

## Structure Guidance

Distribution for the 30 minute slide block:
- **Opening** (~2 slides): why one AI reviewer is not enough, what cc-review is, command overview
- **Main content** (~14 slides): getting started, review flow, many perspectives and meta-review, under the hood, beyond one review (short, since inbox/triage/issue are demoed live afterwards), extending with your own reviewer
- **Closing** (~2 slides): takeaways, hand-over to the results demo
- **Wrap-up after the demo** (bridge slide): call to action, links, Q&A

Notes for the outline:
- The "Beyond one review" section (triage, issue, inbox) is shown live in the 45-55 minute block, so the slides only introduce it (one or two slides) and set up what the demo will show.
- Adding a reviewer is explained on slides only (no live demo): where the file goes, the frontmatter, the prompt body, the command form, and how it shows up in the next run.

## Research Basis

- **Timing default**: 90 seconds per slide for technical content (MIT CommLab, TED research)
- **Cognitive load**: Max 6 elements per slide (Miller's Law)
- **One idea per slide**: Single clear message
- **Accessibility**: 18pt+ fonts, 4.5:1 contrast (WCAG AA)

## Next Steps

1. Review this framing
2. Create outline with `/slidev:outline`
3. Generate slides with `/slidev:generate`
