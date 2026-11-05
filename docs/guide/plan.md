# cc-review Guide Implementation Plan

> **For agentic workers:** this plan is executed by the `/guide:create` controller via
> superpowers:subagent-driven-development, one task per page or diagram. Each page task follows
> `page-procedure.md`; each diagram task follows the `guide:diagrams` skill. Steps are not restated
> here. Rigor for this run is **fast**: no per-task reviews; a single whole-guide review at the end.

**Goal:** A source-verified GitHub-Markdown guide to cc-review for a Developer and a Plugin author,
covering install, the four commands, configuration, the theory and algorithms, and extending it.

**Architecture:** gfm adapter under `docs/`, navigation in `docs/README.md` and `docs/SUMMARY.md`.
Five sections (Overview, Using cc-review, How it works, Extending cc-review, Reference), two personas
(Developer `user`, Plugin author `author`), three Excalidraw diagrams. Every fact cites the pinned
source `cc-review` at `rhuss/cc-review@v1.4.0` (commit 37efe88).

**Spec:** `docs/guide/spec.md`.

## Global Constraints

- Guide: "cc-review Guide", format `gfm`, rigor `fast`, cc-prose present (write with the section voice
  profiles and run the prose check; this run has no voice profiles configured, so use the built-in
  styles concepts/technical/reference and still run `prose:check`).
- Baseline (captured 2026-11-05); every statement is verified at this commit, never at a branch head:

  | id | repo | ref | commit |
  |---|---|---|---|
  | cc-review | rhuss/cc-review | v1.4.0 | 37efe889dec45f580b8f33307790701d71cab74a |

- Baseline values available to pages (never type versions or commits): `cc-review-commit`,
  `cc-review-commit-short`, `cc-review-blob`, `cc-review-tree`, `cc-review-repo`, `baseline-date`.
  In gfm these are generated regions `<!-- guide:attr <name> -->VALUE<!-- /guide:attr -->`, rewritten
  by `make site`; they never go inside a code listing.
- Change requests documented as experimental: none.
- Personas and their entry pages: `user` (Developer) -> `docs/using/index.md`; `author` (Plugin
  author) -> `docs/extending/index.md`.
- Sections and voices: overview/concepts, using/technical, how-it-works/concepts, extending/technical,
  reference/reference.
- Every page starts with a source block after the title; entries are `cc-review:<path>[:<lines>]`,
  `url:<url>`, or (internal pages only) `input:<input-id>`. Facts without a pinned source stay out of
  the page. A navigation-only page carries `<!-- guide: no-sources -->`.
- Inputs are hints, never proof. Registered inputs: presentation-outline, presentation-slides, readme,
  docs-reviewer-plugins, docs-standalone-guide, docs-speckit-guide, data-local-reports,
  data-openshell-findings, brainstorm-overview, brainstorm-reviewer-abstraction,
  brainstorm-meta-reviewer, brainstorm-reviewer-plugins, brainstorm-review-convergence,
  brainstorm-skeptic-fp. No input is confidential.
- Shareable pages never contain confidential terms (none configured), nor the private absolute paths
  that appear in `data-local-reports` (for example any `/Users/.../` path), nor links into `internal/`.
- No em dash or en dash characters in any file.
- gfm format rules: GitHub Markdown; source block and expectations as HTML comments; baseline values
  as generated regions (never in listings); GitHub alerts for admonitions (NOTE/TIP/IMPORTANT/
  WARNING/CAUTION); experimental labels as IMPORTANT alerts after an `<a id>` anchor (none here);
  diagrams linked to their full-size SVG `[![alt](assets/diagrams/<name>.svg)](assets/diagrams/<name>.svg)`;
  pages under `docs/` with the order in `docs/SUMMARY.md` (keep `docs/README.md` in sync).
- Admonitions: only NOTE, TIP, IMPORTANT, WARNING, CAUTION with their fixed meanings.
- Task pages: a why-paragraph, numbered steps with copy-paste commands, `Check:` lines with
  expectations.
- The start page and the section overview pages follow `overview-contract.md`: why before how, the
  spec's `## Why` card as their content, every product defined from its own source (here the harnesses
  and external tools are defined from cc-review's README and linked to their official docs, an accepted
  deviation), and the cold-reader test as their review gate.
- Diagrams follow the diagrams skill. Every label, arrow, and frame is a claim with a source in the
  diagram's claims file (`diagrams/<name>.claims.yaml`). Palette: platform gray
  (`#e9ecef`/`#495057`), governance orange (`#ffe8cc`/`#e8590c`), admin red (`#ffe3e3`/`#c92a2a`),
  user blue (`#d0ebff`/`#1971c2`); text and legends `#495057`.
- Run every command from the guide project root with path arguments; never `cd` into `.guide/cache/`.
- Containers: `podman`, never `docker`. Python packages: `uv`, never pip.
- Commit messages end with the trailer `Assisted-By: 🤖 Claude Code`. The controller does not push
  (the author did not opt into pushes).
- RULING (measured results): the measured numbers are not code-verifiable. On `docs/how-it-works/results.md`
  only, aggregate figures recomputed from the registered data inputs are allowed, presented as dated
  measurements (not facts), attributed in prose to their data file, with public NVIDIA/OpenShell PR
  outcomes cited as `url:` sources. Per-reviewer precision scores are omitted (absent from the data).
  No private path from `data-local-reports` ever appears. This page may cite `input:` evidence in its
  source block as the one documented exception, kept honest by the final review.

## Review Focus

Checked once at the final whole-guide review (fast rigor has no per-task reviews):

- A component on the start page defined by its container or by a repository path, not by what it does
  (cold-reader test, `overview-contract.md`).
- A measured number on `results.md` stated as a fact rather than a dated measurement, or any private
  `/Users/...` path leaking from the measurement data.
- A command flag or default on a page that the pinned source does not show (invented units/advice).
- A cross-reference or diagram image link that does not resolve (warning-level build fails).
- An em dash or en dash slipping in through generated or pasted text.

---

### Task 1: diagram review-pipeline

- **Diagram:** `review-pipeline`, exported to `docs/assets/diagrams/review-pipeline.svg`.
- **Shows:** the six pipeline stages left to right with a fix-loop return arrow.
- **Entities and palette:** six stage boxes in platform gray (`#e9ecef`/`#495057`): Discover,
  Dispatch (parallel), Merge and de-dup, Meta-review, Gate and fix, Report; the Meta-review box tinted
  governance orange (`#ffe8cc`/`#e8590c`); the Gate tinted admin red (`#ffe3e3`/`#c92a2a`); a user
  blue (`#d0ebff`/`#1971c2`) return arrow from Gate and fix back to Dispatch labeled "fix, test,
  re-review (<= 3 rounds)". Legend text `#495057`.
- **Shown on:** `docs/how-it-works/pipeline.md`.
- **Source hints (claims file):** `cc-review:review/core/commands/review.md:226-353` (discover),
  `:632-770` (dispatch), `:784-792` (merge/dedup), `:793-914` (meta-review), `:916-1050` (gate+fix),
  `:1051-1138` (report).

### Task 2: diagram two-critics

- **Diagram:** `two-critics`, exported to `docs/assets/diagrams/two-critics.svg`.
- **Shows:** merged findings passing through two critics into one verdict.
- **Entities and palette:** "Merged findings" input box platform gray; two critic boxes in governance
  orange: "Skeptic (refute: confirmed / weak / false-positive)" and "Calibrator (severity +
  contradictions)"; output "One verdict (conservative wins)" in user blue. Text `#495057`.
- **Shown on:** `docs/how-it-works/meta-review.md`.
- **Source hints:** `cc-review:review/core/agents/meta-skeptic.md:17-55`,
  `cc-review:review/core/agents/meta-calibrator.md:17-90`,
  `cc-review:review/core/commands/review.md:869-889`.

### Task 3: diagram core-and-layers

- **Diagram:** `core-and-layers`, exported to `docs/assets/diagrams/core-and-layers.svg`.
- **Shows:** three harness shims feeding one core, beside the three reviewer discovery layers.
- **Entities and palette:** three shim boxes (Claude Code, Codex, OpenCode) in user blue feeding a
  central "Harness-agnostic core" box in platform gray; to the side a stack of three layers in
  governance orange, top to bottom "project `.cc-review/reviewers/`", "user `~/.cc-review/reviewers/`",
  "bundled `review/core/reviewers/`", with a "higher replaces by name" label. Text `#495057`.
- **Shown on:** `docs/README.md` and `docs/extending/index.md`.
- **Source hints:** `cc-review:README.md:329-362`,
  `cc-review:review/core/scripts/discover-reviewers.sh:717-778`,
  `cc-review:review/.claude-plugin/plugin.json:1-20`, `cc-review:review/.codex-plugin/plugin.json:1-11`.

### Task 4: page docs/README.md (start page)

- **Page:** `docs/README.md`. **Persona:** both. **Voice:** concepts. **Internal:** no.
- **Follows `overview-contract.md`** (start page shape; the spec's `## Why` card is the content).
- **Outline:** outcome first (what the reader gets, the problem it solves); one-sentence definitions of
  cc-review, the three harnesses, and the four external tools (each by function, linked to official
  docs); how the parts fit (core + per-harness manifests + the three discovery layers) with the
  **core-and-layers** diagram; why run them together; status and limits; where to go next per persona;
  the baseline note.
- **Facts + source hints:** the Why-card rows of the spec. Component own-source: cc-review
  `cc-review:README.md:3-6`; harnesses `cc-review:README.md:3,23-61` + official doc URLs; external
  tools `cc-review:README.md:12,374-378`; fit `cc-review:README.md:329-362` +
  `cc-review:review/core/scripts/discover-reviewers.sh:717-766`.
- **Content rules (guide-rules.yaml):**
  - glob `docs/README.md` require: `\]\(using/index\.md\)`, `\]\(extending/index\.md\)`,
    `\]\(how-it-works/index\.md\)`, `assets/diagrams/core-and-layers\.svg`, `guide:attr cc-review-commit-short`.
  - forbid: `—`, `–`.

### Task 5: page docs/using/index.md (section overview, persona entry)

- **Page:** `docs/using/index.md`. **Persona:** user. **Voice:** technical. **Internal:** no.
- **Follows `overview-contract.md`** (section overview opening paragraph, then the page list).
- **Outline:** what the Developer achieves in this section, then links to install, review, triage,
  inbox-and-issue.
- **Facts + source hints:** `cc-review:README.md:73-131`.
- **Content rules:** glob `docs/using/index.md` require: `\]\(install\.md\)`, `\]\(review\.md\)`,
  `\]\(triage\.md\)`, `\]\(inbox-and-issue\.md\)`; forbid: `—`, `–`.

### Task 6: page docs/using/install.md

- **Page:** `docs/using/install.md`. **Persona:** user. **Voice:** technical. **Internal:** no.
- **Outline:** why install as a plugin; prerequisites (jq 1.6+, mikefarah yq 4.18+, authenticated gh,
  Python 3.9+); install on Claude Code (marketplace add + install, or `make install`), Codex
  (marketplace add + install), OpenCode (`install.sh`); optional spec-kit extension; a verify `Check`.
- **Facts + source hints:** `cc-review:README.md:21-71,102,121`,
  `cc-review:review/opencode/install.sh:1-32`,
  `cc-review:review/core/scripts/discover-reviewers.sh:666-680`,
  `cc-review:review/.claude-plugin/plugin.json:1-20`.
- **Content rules:** glob `docs/using/install.md` require: `^#`, `jq`, `yq`, `\bgh\b`, `Python`,
  `install\.sh`, `(?m)^Check:`; require_order: `marketplace add`, `plugin install`, `install\.sh`;
  forbid: `—`, `–`.

### Task 7: page docs/using/review.md

- **Page:** `docs/using/review.md`. **Persona:** user. **Voice:** technical. **Internal:** no.
- **Outline:** why review before you push; `/review` (branch vs main), `/review --pr N` (own worktree),
  the `quick`/`thorough`/`ci` profiles, the key flags (`--no-fix`, `--no-external`, `--only`,
  `--spec`); how to read the report and the gate (Critical + Important = 0 passes); a brief on bulk
  (`--bulk`) and follow-up reviews. Point to How it works for the mechanism.
- **Facts + source hints:** `cc-review:README.md:125-252`,
  `cc-review:review/core/commands/review.md:916-926` (gate),
  `cc-review:review/config/profiles/quick.yml`, `.../thorough.yml`, `.../ci.yml`.
- **Content rules:** glob `docs/using/review.md` require: `/review`, `--pr`, `quick`, `thorough`,
  `ci`, `Critical`, `Important`, `(?m)^Check:`; forbid: `—`, `–`, `/Users/`.

### Task 8: page docs/using/triage.md

- **Page:** `docs/using/triage.md`. **Persona:** user. **Voice:** technical. **Internal:** no.
- **Outline:** why triage PR comments; `/triage`, `/triage --pr N`; bot vs human handling; triage
  drafts replies and never pushes a reviewer fix; coverage remediation in brief.
- **Facts + source hints:** `cc-review:README.md:191-252`,
  `cc-review:review/core/commands/triage.md:1-15,456-546,887-949`.
- **Content rules:** glob `docs/using/triage.md` require: `/triage`, `--pr`, `bot`, `(?m)^Check:`;
  forbid: `—`, `–`.

### Task 9: page docs/using/inbox-and-issue.md

- **Page:** `docs/using/inbox-and-issue.md`. **Persona:** user. **Voice:** technical. **Internal:** no.
- **Outline:** why a repository inbox and issue assessment; `/inbox` (who acts next, key flags) and
  `/issue N` (need, fit, value, reply draft); both are read-only and never post.
- **Facts + source hints:** `cc-review:README.md:75-123`,
  `cc-review:review/core/commands/inbox.md:1-34,94-123`,
  `cc-review:review/core/commands/issue.md:1-21,75-83`.
- **Content rules:** glob `docs/using/inbox-and-issue.md` require: `/inbox`, `/issue`, `read-only`,
  `(?m)^Check:`; forbid: `—`, `–`.

### Task 10: page docs/how-it-works/index.md (section overview)

- **Page:** `docs/how-it-works/index.md`. **Persona:** both. **Voice:** concepts. **Internal:** no.
- **Follows `overview-contract.md`** (section overview opening).
- **Outline:** the big idea in one paragraph (a panel of focused reviewers, two critics that filter,
  a fix loop that closes the gate), then links to pipeline, reviewers, meta-review, gate-and-fix,
  results.
- **Facts + source hints:** `cc-review:README.md:3-6,329-391`.
- **Content rules:** glob `docs/how-it-works/index.md` require: `\]\(pipeline\.md\)`,
  `\]\(reviewers\.md\)`, `\]\(meta-review\.md\)`, `\]\(gate-and-fix\.md\)`, `\]\(results\.md\)`;
  forbid: `—`, `–`.

### Task 11: page docs/how-it-works/pipeline.md

- **Page:** `docs/how-it-works/pipeline.md`. **Persona:** both. **Voice:** concepts. **Internal:** no.
- **Outline:** the six stages end to end (discover, dispatch in parallel, merge and de-duplicate,
  meta-review, gate and fix, report); what a prompt reviewer and a command reviewer are at dispatch.
  Shows the **review-pipeline** diagram.
- **Facts + source hints:**
  `cc-review:review/core/commands/review.md:226-353,632-770,784-792,793-914,916-1050,1051-1138`.
- **Content rules:** glob `docs/how-it-works/pipeline.md` require: `assets/diagrams/review-pipeline\.svg`,
  `[Dd]iscover`, `[Dd]ispatch`, `[Mm]erge`, `[Mm]eta-review`, `[Gg]ate`, `[Rr]eport`; forbid: `—`, `–`.

### Task 12: page docs/how-it-works/reviewers.md

- **Page:** `docs/how-it-works/reviewers.md`. **Persona:** both. **Voice:** concepts. **Internal:** no.
- **Outline:** the six lanes and their "stay in your lane" role gates; the shared preamble rules (judge
  what was built not intended, no git log or plan docs, confidence >= 70 or 50 for Critical, no praise,
  zero findings is valid); the external command reviewers and the opt-in gator persona with its
  evidence contract.
- **Facts + source hints:** `cc-review:review/core/reviewers/correctness.md:9-15`,
  `architecture.md:9-17`, `security.md:9-17`, `production.md:9-17`, `test-quality.md:9-17`,
  `goal-alignment.md:1-21`, `cc-review:review/core/agents/preamble.md:22-55`,
  `cc-review:review/core/reviewers/gator/reviewer.md:1-13,159-166`,
  `cc-review:review/core/reviewers/gator/references/findings-contract.md:1-57`.
- **Content rules:** glob `docs/how-it-works/reviewers.md` require: `Correctness`, `Security`,
  `stay in your lane` (case-insensitive via `[Ss]tay in your lane`), `confidence`, `gator`;
  forbid: `—`, `–`.

### Task 13: page docs/how-it-works/meta-review.md

- **Page:** `docs/how-it-works/meta-review.md`. **Persona:** both. **Voice:** concepts. **Internal:** no.
- **Outline:** the two critics (Skeptic refutes each finding -> confirmed/weak/false-positive;
  Calibrator checks severity and cross-reviewer contradictions; the more conservative verdict wins);
  the de-dup rule (same file, overlapping lines, same category, keep the stronger, record
  `also_reported_by`); why it is gated by a minimum finding count. Shows the **two-critics** diagram.
- **Facts + source hints:** `cc-review:review/core/agents/meta-skeptic.md:17-55`,
  `cc-review:review/core/agents/meta-calibrator.md:17-90`,
  `cc-review:review/core/commands/review.md:784-792,793-889`.
- **Content rules:** glob `docs/how-it-works/meta-review.md` require: `assets/diagrams/two-critics\.svg`,
  `Skeptic`, `Calibrator`, `also_reported_by`; forbid: `—`, `–`.

### Task 14: page docs/how-it-works/gate-and-fix.md

- **Page:** `docs/how-it-works/gate-and-fix.md`. **Persona:** both. **Voice:** concepts. **Internal:** no.
- **Outline:** the gate (Critical + Important = 0 passes; Minor and Notable never block) and the fix
  loop (fix bottom-up, run tests, a failing test becomes a Critical regression finding, re-review only
  modified files, up to three rounds); follow-up reviews that verify earlier concerns and converge
  without re-raising nits.
- **Facts + source hints:** `cc-review:review/core/commands/review.md:916-1050`,
  `cc-review:README.md:139-143,386-390`.
- **Content rules:** glob `docs/how-it-works/gate-and-fix.md` require: `Critical`, `Important`,
  `Notable`, `3` , `re-review`; forbid: `—`, `–`.

### Task 15: page docs/how-it-works/results.md (measured; under the RULING)

- **Page:** `docs/how-it-works/results.md`. **Persona:** both. **Voice:** concepts. **Internal:** no.
- **Outline:** how well it works, as dated measurements (not code facts): public NVIDIA/OpenShell
  outcomes (208 inline findings over 20 public PRs, 77 verified fixed, about 56% addressed) linked to
  the public PRs; the maintainer's local aggregate (Critical and Important fixed at a high rate) as of
  the measurement date; the candid limit that the skeptic removes few findings outright. State every
  number as "measured on <date>", attribute it in prose to its data file, and never print a private
  path.
- **Facts + source hints:** `url:https://github.com/NVIDIA/OpenShell/pull/5082` (and the other public
  PRs), `input:data-openshell-findings`, `input:data-local-reports` (measurement evidence, per the
  RULING); qualitative skeptic limit from `cc-review:review/core/agents/meta-skeptic.md:17-26`.
- **Content rules:** glob `docs/how-it-works/results.md` require: `[Mm]easured`, `OpenShell`, `208`,
  `pull/`; forbid: `—`, `–`, `/Users/`.

### Task 16: page docs/extending/index.md (section overview + architecture, persona entry)

- **Page:** `docs/extending/index.md`. **Persona:** author. **Voice:** technical. **Internal:** no.
- **Follows `overview-contract.md`** (section overview opening).
- **Outline:** what the author achieves here; the architecture (one core, three harness manifests and
  shims, reviewers discovered at run time from three layers with precedence). Shows the
  **core-and-layers** diagram; links to prompt-reviewer, command-reviewer, trust-and-config.
- **Facts + source hints:** `cc-review:README.md:329-362`,
  `cc-review:review/core/scripts/discover-reviewers.sh:717-778`,
  `cc-review:review/.claude-plugin/plugin.json:1-20`, `cc-review:review/.codex-plugin/plugin.json:1-11`.
- **Content rules:** glob `docs/extending/index.md` require: `assets/diagrams/core-and-layers\.svg`,
  `\]\(prompt-reviewer\.md\)`, `\]\(command-reviewer\.md\)`, `\]\(trust-and-config\.md\)`,
  `project`, `bundled`; forbid: `—`, `–`.

### Task 17: page docs/extending/prompt-reviewer.md

- **Page:** `docs/extending/prompt-reviewer.md`. **Persona:** author. **Voice:** technical. **Internal:** no.
- **Outline:** why a reviewer is one Markdown file; the frontmatter (`name`, `display_name`,
  `kind: prompt`, `category`) and body (role, scope, checklist); the shared preamble added at dispatch;
  where to drop it (`.cc-review/reviewers/` or `~/.cc-review/reviewers/`); seeing it in the next run
  and `--only <name>`. A worked example; a `Check`.
- **Facts + source hints:** `cc-review:README.md:309-323`,
  `cc-review:docs/reviewer-plugins.md` (frontmatter + prompt sections),
  `cc-review:review/core/schemas/reviewer.schema.json`.
- **Content rules:** glob `docs/extending/prompt-reviewer.md` require: `kind: prompt`, `frontmatter`,
  `--only`, `(?m)^Check:`; forbid: `—`, `–`.

### Task 18: page docs/extending/command-reviewer.md

- **Page:** `docs/extending/command-reviewer.md`. **Persona:** author. **Voice:** technical. **Internal:** no.
- **Outline:** why wrap an external tool; the `kind: command` block (`detect`, `auth_check`, `invoke`,
  `timeout_seconds`, `severity_map`, `output.format`) with Greptile as the worked example and a parser
  excerpt; a `Check`.
- **Facts + source hints:** `cc-review:review/core/reviewers/greptile/reviewer.md:1-53`,
  `cc-review:review/core/reviewers/greptile/parse.sh`,
  `cc-review:docs/reviewer-plugins.md` (command reviewers),
  `cc-review:review/core/schemas/reviewer.schema.json:40-54`.
- **Content rules:** glob `docs/extending/command-reviewer.md` require: `kind: command`, `detect`,
  `invoke`, `severity_map`, `(?m)^Check:`; forbid: `—`, `–`.

### Task 19: page docs/extending/trust-and-config.md

- **Page:** `docs/extending/trust-and-config.md`. **Persona:** author. **Voice:** technical. **Internal:** no.
- **Outline:** the trust model (a project reviewer edited by the change under review does not judge that
  change; a project command reviewer runs nothing until trusted by sha256 in
  `~/.cc-review/trusted-reviewers`; command reviewers skip untrusted fork checkouts); enabling or
  disabling reviewers via config (`reviewers.<name>`), `--only`, and `--no-<name>`.
- **Facts + source hints:** `cc-review:review/core/scripts/discover-reviewers.sh:124-173,516-614`,
  `cc-review:review/core/commands/review.md:325-333`, `cc-review:docs/reviewer-plugins.md:19-31`,
  `cc-review:README.md:268-307`.
- **Content rules:** glob `docs/extending/trust-and-config.md` require: `trusted-reviewers`, `sha256`,
  `--no-`, `reviewers:`; forbid: `—`, `–`.

### Task 20: page docs/reference/index.md (section overview)

- **Page:** `docs/reference/index.md`. **Persona:** both. **Voice:** reference. **Internal:** no.
- **Follows `overview-contract.md`** (brief section overview opening).
- **Outline:** what the reference holds, then links to cli and config-and-schema.
- **Facts + source hints:** `cc-review:README.md:254-391`.
- **Content rules:** glob `docs/reference/index.md` require: `\]\(cli\.md\)`,
  `\]\(config-and-schema\.md\)`; forbid: `—`, `–`.

### Task 21: page docs/reference/cli.md

- **Page:** `docs/reference/cli.md`. **Persona:** both. **Voice:** reference. **Internal:** no.
- **Outline:** every flag for `review`, `triage`, `inbox`, `issue`, and the `quick`/`thorough`/`ci`
  profiles, as tables. Reference voice: table-heavy, skip the prose check.
- **Facts + source hints:** `cc-review:README.md:163-252,90-98,110-115`,
  `cc-review:review/config/profiles/quick.yml`, `.../thorough.yml`, `.../ci.yml`.
- **Content rules:** glob `docs/reference/cli.md` require: `--pr`, `--bulk`, `--only`, `--spec`,
  `quick`, `thorough`, `ci`; forbid: `—`, `–`.

### Task 22: page docs/reference/config-and-schema.md

- **Page:** `docs/reference/config-and-schema.md`. **Persona:** both. **Voice:** reference. **Internal:** no.
- **Outline:** configuration options and the resolution order (CLI > `--config` > `--profile` >
  project > user > defaults > reviewer default); the finding schema (severities Critical/Important/
  Minor/Notable, confidence, resolution) and `severity_map` translation at merge. Table-heavy.
- **Facts + source hints:** `cc-review:README.md:254-307`,
  `cc-review:review/core/scripts/resolve-config.sh:117-222`,
  `cc-review:review/core/schemas/finding.schema.json:40-127`,
  `cc-review:review/core/schemas/reviewer.schema.json:40-54`.
- **Content rules:** glob `docs/reference/config-and-schema.md` require: `resolution`, `--profile`,
  `Critical`, `Important`, `Minor`, `Notable`, `severity_map`; forbid: `—`, `–`.

## Self-review notes

- Spec coverage: every section and page in `spec.md` maps to a task (Tasks 4-22); every diagram maps to
  Tasks 1-3; the measured-results decision (option B) is Task 15 under the RULING.
- Ordering: diagrams (1-3) precede the pages that embed them (pipeline/meta-review/README/extending).
- Fast rigor: no per-task reviews; the Review Focus list is the final-review checklist.
- Deviations recorded: harnesses and external tools defined from cc-review's README + official links
  (no own-source pin); measured results under the RULING in Global Constraints.
