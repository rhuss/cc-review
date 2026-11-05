# cc-review Guide: specification

Status: draft for the author's approval (plan approval gate). Source id `cc-review`, pinned at
`rhuss/cc-review@v1.4.0` (commit 37efe88). Format gfm, rigor standard, cc-prose present. No
internal part. Every factual sentence on a page must trace to a pinned-source location; this spec
lists the source hints the plan will turn into page tasks.

## Intent and the why

cc-review is a multi-agent code review plugin for AI coding agents (Claude Code, Codex, OpenCode).
This guide takes two readers from zero to productive: a **Developer** who runs reviews on their own
changes and pull requests, and a **Plugin author** who adds their own reviewer. It also explains
**how cc-review works** (the panel, the skeptic/calibrator, the gate and fix loop, the reviewer
discovery model), so a reader understands the machine, not just the commands. The conceptual arc
mirrors the project's own presentation.

## Why (the overview card)

The start page carries this card. Each factual sentence names its pinned source; a slot without a
source is flagged under open questions.

| Slot | Content | Source |
|---|---|---|
| Problem | Running a single AI reviewer over a change tends to produce many low-signal comments, and running several review tools by hand is tedious; there is no one filtered verdict, with the obvious issues already fixed, before you push or open a PR. | `cc-review:README.md:3-6,12` |
| Outcome | The reader can run a panel of focused review agents plus external tools over a change, have their findings merged and de-duplicated, filtered by a skeptic and a calibrator, and the Critical and Important issues fixed and re-reviewed, arriving at one report. | `cc-review:README.md:3-6,9-13` |
| Components: cc-review | cc-review is a plugin that dispatches a set of specialized code-review agents against your changes, merges and de-duplicates their findings together with external tools, then runs an autonomous fix loop before you see the report. | `cc-review:README.md:3-6` |
| Components: Claude Code / Codex / OpenCode | The three AI coding agents ("harnesses") cc-review plugs into; each reads its own plugin manifest and ignores the others. | `cc-review:README.md:3,23-61` (own source not pinned, see open questions) |
| Components: CodeRabbit / GitHub Copilot / Codex CLI / Greptile | External code-review command-line tools cc-review can run as "command reviewers" and fold into the same report. | `cc-review:README.md:12,374-378` (own source not pinned) |
| Fit | cc-review ships one harness-agnostic core with a thin manifest and shim per harness; the core holds no reviewer list and discovers reviewers from three layers (project, user, bundled), a higher layer replacing a lower one by name. | `cc-review:README.md:329-362`, `cc-review:review/core/scripts/discover-reviewers.sh:717-766` |
| Why this combination | Running several focused reviewers and external tools locally, before you push, and filtering them down to one verdict gives higher signal than a single bot and catches problems across vendors. | `cc-review:README.md:5,12` |
| Status and limits | cc-review is at version v1.4.0; the external CLIs are optional and Greptile spends credits each run; the meta-review skeptic currently rarely removes a finding outright. | baseline attr `cc-review-commit-short` / v1.4.0, `cc-review:review/core/reviewers/greptile/reviewer.md:43-53`, `cc-review:review/core/agents/meta-skeptic.md:17-26` |

Component definitions pass the four tests of `overview-contract.md`: each says what the thing does
for the reader, avoids self-reference, uses known words, and cites the product's own source. The
three harnesses and the four external tools are defined from cc-review's own README (the integrating
source) because the intake pinned only the cc-review repository; see open questions.

## Goals, non-goals, anti-goals

- **Goals.** A Developer can install cc-review on their harness and run review, triage, inbox, and
  issue; a Plugin author can add a prompt reviewer and wrap an external tool; both readers understand
  the pipeline and the reviewer model. Every statement is verified against the pinned source.
- **Non-goals.** Contributing to cc-review's own internals or development process; a full spec-kit
  tutorial (named and linked, not taught); exhaustive coverage of every flag beyond the reference.
- **Anti-goals.** Stating any behavior the pinned source does not show; printing measured numbers as
  if they were code-verified facts; leaking the private project paths that live in the measurement
  data; using an em dash or en dash.

## Persona journeys

- **Developer (`user`).** Lands on the start page, goes to *Using cc-review*, installs on their
  harness, runs a first review and reads the report and gate, then triages PR comments, checks the
  repository inbox, assesses an issue, and scales up to bulk and follow-up reviews. Dips into *How it
  works* to understand what the pipeline did, and into *Reference* for flags and config.
- **Plugin author (`author`).** Lands on the start page, reads *How it works* to understand the
  reviewer model, then goes to *Extending cc-review*: the architecture and discovery layers, writing
  a prompt reviewer, wrapping an external tool as a command reviewer, and the trust model. Uses
  *Reference* for the finding schema and config.

## Page list

Paths are under `docs/` (gfm). Each page starts with a source block; task pages use the why-then-
steps-then-`Check:` shape; the start page and section overviews follow `overview-contract.md`.

### Overview (concepts)

1. **`docs/README.md` (start page).** The Why card as prose: outcome first, then what cc-review is,
   then one-sentence definitions of the harnesses and the external tools, then how the parts fit
   (core plus per-harness manifests plus the three discovery layers) with the core-and-layers
   diagram, why run them together, status and limits, and where to go next per persona plus the
   baseline note. Sources as in the Why card.

### Using cc-review (technical, Developer)

2. **`docs/using/index.md` (section overview, persona entry).** One paragraph on what the Developer
   achieves here, then the page list. Follows the overview-contract opening. Source:
   `cc-review:README.md:73-131`.
3. **`docs/using/install.md`.** Why install as a plugin; install on Claude Code (marketplace add +
   install, or `make install`), Codex (marketplace add + install), OpenCode (`install.sh`); optional
   spec-kit extension; prerequisites (jq, mikefarah yq, gh authenticated, Python 3.9+); a verify
   `Check`. Sources: `cc-review:README.md:21-71,102,121`, `cc-review:review/opencode/install.sh:1-32`,
   `cc-review:review/core/scripts/discover-reviewers.sh:666-680`,
   `cc-review:review/.claude-plugin/plugin.json:1-20`.
4. **`docs/using/review.md`.** Why review before you push; run `/review` (branch vs main), `--pr N`
   (own worktree), the `quick`/`thorough`/`ci` profiles, key flags (`--no-fix`, `--no-external`,
   `--only`, `--spec`); how to read the report and the gate (Critical + Important = 0 passes); bulk
   review (`--bulk`) and follow-up reviews (only the delta since your last review) in brief. Sources:
   `cc-review:README.md:125-252`, `cc-review:review/core/commands/review.md:916-926`,
   `cc-review:review/config/profiles/quick.yml`, `.../thorough.yml`, `.../ci.yml`.
5. **`docs/using/triage.md`.** Why triage PR comments; run `/triage` and `/triage --pr N`; bot vs
   human handling; what triage will and will not do (drafts replies, never pushes a reviewer fix);
   coverage remediation. Sources: `cc-review:README.md:191-252`,
   `cc-review:review/core/commands/triage.md:1-15,456-546,887-949`.
6. **`docs/using/inbox-and-issue.md`.** Why a repository inbox and issue assessment; run `/inbox`
   (who acts next, flags) and `/issue N` (need, fit, value, reply draft); both are read-only.
   Sources: `cc-review:README.md:75-123,106-123`, `cc-review:review/core/commands/inbox.md:1-34,94-123`,
   `cc-review:review/core/commands/issue.md:1-21,75-83`.

### How it works (concepts)

7. **`docs/how-it-works/index.md` (section overview).** The big idea in one paragraph: a panel of
   focused reviewers, two critics that filter the findings, and a fix loop that closes the gate, then
   the page list. Sources: `cc-review:README.md:3-6,329-391`.
8. **`docs/how-it-works/pipeline.md`.** The six stages end to end: discover, dispatch in parallel,
   merge and de-duplicate, meta-review, gate and fix, report; what a prompt reviewer and a command
   reviewer are at dispatch. Shows the **review pipeline** diagram. Sources:
   `cc-review:review/core/commands/review.md:226-353,632-770,784-792,793-914,916-1050,1051-1138`.
9. **`docs/how-it-works/reviewers.md`.** The six lanes and their "stay in your lane" role gates; the
   shared preamble rules (judge what was built not intended, no git log or plan docs, confidence
   >= 70 or 50 for Critical, no praise, zero findings is valid); the external command reviewers and
   the opt-in gator persona with its evidence contract. Sources:
   `cc-review:review/core/reviewers/correctness.md:9-15` (and the other five lane files),
   `cc-review:review/core/agents/preamble.md:22-55`,
   `cc-review:review/core/reviewers/gator/reviewer.md:1-13,159-166`,
   `cc-review:review/core/reviewers/gator/references/findings-contract.md:1-57`.
10. **`docs/how-it-works/meta-review.md`.** The two critics: the Skeptic refutes each finding
    (confirmed / weak / false-positive) and the Calibrator checks severity and cross-reviewer
    contradictions, with the more conservative verdict winning; the de-dup rule (same file,
    overlapping lines, same category, keep the stronger, record `also_reported_by`); why it is gated
    by a minimum finding count. Shows the **two critics** diagram. Sources:
    `cc-review:review/core/agents/meta-skeptic.md:17-55`,
    `cc-review:review/core/agents/meta-calibrator.md:17-90`,
    `cc-review:review/core/commands/review.md:784-792,793-889`.
11. **`docs/how-it-works/gate-and-fix.md`.** The gate (Critical + Important = 0 passes; Minor and
    Notable never block) and the fix loop (fix bottom-up, run tests, a failing test becomes a
    Critical regression finding, re-review only the modified files, up to three rounds); follow-up
    reviews that verify earlier concerns and converge without re-raising nits. Shows the **fix loop**
    (as part of the pipeline diagram, or a small inline sequence). Sources:
    `cc-review:review/core/commands/review.md:916-1050`, `cc-review:README.md:139-143,386-390`.
12. **`docs/how-it-works/results.md` (pending the author's metrics decision).** How well it works, as
    measured, clearly dated: outcomes on the public NVIDIA/OpenShell pull requests (208 inline
    findings over 20 public PRs, 77 verified fixed, about 56% addressed) linked to those public PRs,
    and the maintainer's local aggregate (Critical and Important fixed at a high rate), with the
    candid limit that the skeptic removes few findings outright. Presented as measurements, not
    code-verified facts, under a recorded ruling. Sources: public PR URLs (`url:`),
    `input:data-openshell-findings` and `input:data-local-reports` as measurement evidence (see open
    questions; this is the one page that needs a sourcing decision).

### Extending cc-review (technical, Plugin author)

13. **`docs/extending/index.md` (section overview + architecture, persona entry).** What the author
    achieves here; the architecture: one core, three harness manifests and shims, reviewers
    discovered at run time from three layers with precedence. Shows the **core and layers** diagram.
    Sources: `cc-review:README.md:329-362`,
    `cc-review:review/core/scripts/discover-reviewers.sh:717-778`,
    `cc-review:review/.claude-plugin/plugin.json:1-20`, `cc-review:review/.codex-plugin/plugin.json:1-11`.
14. **`docs/extending/prompt-reviewer.md`.** Why a reviewer is one Markdown file; the frontmatter
    (`name`, `display_name`, `kind: prompt`, `category`) and body (role, scope, checklist); the shared
    preamble added at dispatch; where to drop it (`.cc-review/reviewers/` or `~/.cc-review/`); seeing
    it in the next run and `--only <name>`. A worked example. Sources:
    `cc-review:README.md:309-323`, `cc-review:docs/reviewer-plugins.md` (frontmatter + prompt
    sections), `cc-review:review/core/schemas/reviewer.schema.json`.
15. **`docs/extending/command-reviewer.md`.** Why wrap an external tool; the `kind: command` block
    (`detect`, `auth_check`, `invoke`, `timeout_seconds`, `severity_map`, `output.format`) with
    Greptile as the worked example and a parser excerpt. Sources:
    `cc-review:review/core/reviewers/greptile/reviewer.md:1-53`,
    `cc-review:review/core/reviewers/greptile/parse.sh`, `cc-review:docs/reviewer-plugins.md`
    (command reviewers), `cc-review:review/core/schemas/reviewer.schema.json:40-54`.
16. **`docs/extending/trust-and-config.md`.** The trust model: a project reviewer edited by the
    change under review does not judge that change; a project command reviewer runs nothing until
    trusted by sha256 in `~/.cc-review/trusted-reviewers`; command reviewers skip untrusted fork
    checkouts; and enabling or disabling reviewers through config (`reviewers.<name>`), `--only`, and
    `--no-<name>`. Sources: `cc-review:review/core/scripts/discover-reviewers.sh:124-173,516-614`,
    `cc-review:review/core/commands/review.md:325-333`, `cc-review:docs/reviewer-plugins.md:19-31`,
    `cc-review:README.md:268-307`.

### Reference (reference)

17. **`docs/reference/index.md` (section overview).** What the reference holds; one paragraph plus
    the list. Source: `cc-review:README.md:254-391`.
18. **`docs/reference/cli.md`.** Every flag for `review`, `triage`, `inbox`, and `issue`, and the
    `quick`/`thorough`/`ci` profiles, as tables. Sources: `cc-review:README.md:163-252,90-98,110-115`,
    `cc-review:review/config/profiles/*.yml`.
19. **`docs/reference/config-and-schema.md`.** Configuration options and the resolution order (CLI >
    `--config` > `--profile` > project > user > defaults > reviewer default); the finding schema
    (severities Critical/Important/Minor/Notable, confidence, resolution) and `severity_map`
    translation at merge. Sources: `cc-review:README.md:254-307`,
    `cc-review:review/core/scripts/resolve-config.sh:117-222`,
    `cc-review:review/core/schemas/finding.schema.json:40-127`,
    `cc-review:review/core/schemas/reviewer.schema.json:40-54`.

## Diagrams

All three follow the diagrams skill and the guide palette; every label and arrow is a claim with a
source in the diagram's claims file. Diagram tasks run before the pages that show them.

- **review-pipeline** (`docs/how-it-works/pipeline.md`): the six stages discover -> dispatch (parallel)
  -> merge -> meta-review -> gate and fix -> report, with the fix loop arrow back to dispatch.
  Entities and sources from `cc-review:review/core/commands/review.md` stage ranges.
- **two-critics** (`docs/how-it-works/meta-review.md`): the merged findings flowing through the
  Skeptic and the Calibrator into one verdict. Sources `meta-skeptic.md`, `meta-calibrator.md`,
  `review.md:869-889`.
- **core-and-layers** (`docs/README.md` and `docs/extending/index.md`): the three harness shims
  feeding one core, beside the project/user/bundled reviewer layers. Sources `README.md:329-362`,
  `discover-reviewers.sh:717-778`.

## Experimental content

None. `baseline.yaml` has no change requests.

## Internal part

None. `internal.enabled: false`. The measurement data is public (NVIDIA/OpenShell) or the
maintainer's local aggregate; no confidential terms or patterns are configured.

## Open questions (for the approval gate)

1. **Measured results (page 12).** The source-verification model needs a pinned source for every
   fact, forbids `input:` citations on shareable pages, and there is no internal part. The measured
   numbers have no code source: per-reviewer precision is not even in the registered data (the `aq`
   field is empty), and the local-reports data holds private paths. Options: (A) drop page 12 and
   keep *How it works* qualitative; (B) keep page 12 as a dated "measurements" page with the public
   OpenShell PRs as `url:` sources and the local aggregate attributed under a recorded ruling; (C)
   keep only the public OpenShell outcomes via PR links and drop the local numbers. The plan assumes
   (B) with a ruling, pending the author's choice.
2. **Harness and external-tool own sources.** The intake pinned only the cc-review repository, so the
   harnesses (Claude Code, Codex, OpenCode) and the external tools are defined from cc-review's own
   README, not their own sources (a deviation from FR-043 the author accepted). The pages will link
   the official docs. Confirm this is acceptable, or add their sources.
3. **Diagram count.** Three diagrams add three diagram tasks with manual verification. Confirm all
   three, or fewer.
4. **Scope size.** Nineteen pages plus three diagrams at standard rigor is a large run (about
   nineteen page reviews plus three diagram reviews plus a final review). The author may prefer fast
   rigor, a trimmed page list, or fewer diagrams.
