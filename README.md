# cc-review

Multi-agent code review plugin for AI coding agents. Works with Claude Code, Codex, and OpenCode.

cc-review dispatches a set of specialized reviewers against your code changes, merges and deduplicates findings across reviewers and external tools, then runs an autonomous fix loop to resolve Critical and Important issues before you see the report.

## Features

- **6 built-in review agents**: Correctness, Architecture & Idioms, Security, Production Readiness, Test Quality, Goal Alignment
- **Pluggable reviewers**: add your own reviewer by dropping one markdown file into `.cc-review/reviewers/`; no core changes needed. See [docs/reviewer-plugins.md](docs/reviewer-plugins.md)
- **Autonomous fix loop**: automatically applies fixes for Critical/Important findings, re-reviews, and repeats (up to 3 rounds by default)
- **External tool integration**: CodeRabbit, GitHub Copilot CLI, and Codex CLI run as command reviewers; their findings are merged and deduplicated with agent findings
- **Gator reviewer (opt-in)**: a pragmatic principal-engineer review persona ported from NVIDIA OpenShell, with an evidence contract for every blocking finding
- **PR comment triage**: classify and handle bot review comments (CodeRabbit, Copilot, Devin) and human reviewer feedback
- **Repository inbox**: see relevant PRs, issues, and Discussions grouped by who acts next, with evidence and suggested actions
- **Spec-aware review**: pass a specification file to cross-check implementation against functional requirements
- **Multi-harness support**: thin adapter layer for Claude Code, spec-kit, and AGENTS.md-based tools (Codex, OpenCode)

## Installation

cc-review ships as a single plugin directory (`review/`) with native manifests for Claude Code, Codex, and OpenCode. Each harness reads its own manifest and ignores the others.

### Claude Code

Install via the Claude Code plugin system:

```bash
# From a local clone
claude plugin marketplace add /path/to/cc-review
claude plugin install cc-review@cc-review-plugin-development

# Or use the Makefile shortcut
make install
```

This registers the local marketplace and installs the plugin. The `/review`, `/triage`, and `/inbox` commands become available immediately.

### Codex

Install via the Codex plugin system:

```bash
# From a local clone (register as local marketplace)
codex plugin marketplace add /path/to/cc-review
codex plugin install cc-review@cc-review-plugin-development
```

The `review`, `triage`, and `inbox` skills are discovered from `review/skills/`.

### OpenCode

Install the OpenCode commands into your project:

```bash
# From a local clone
/path/to/cc-review/review/opencode/install.sh --project-dir .
```

This copies cc-review commands to `.opencode/plugins/cc-review/` in your project.

### spec-kit (optional)

Install as a spec-kit extension for projects using cc-spex:

```bash
specify extension add /path/to/cc-review/speckit
```

The spec-kit adapter automatically passes spec paths, constitution hints, and output locations during the ship pipeline.

## Usage

### Repository Inbox

Run the `inbox` command or skill through your coding agent:

```text
inbox
inbox --type pr
inbox --type issue,discussion --limit 20
inbox --repo owner/repo --since 2026-10-01
```

The inbox explains what needs your attention in one repository. It includes your own items, assignments, review requests (including team requests), mentions, and conversations you commented on or reviewed, including participation outside cc-review.

Results appear under **Needs your attention**, **Waiting on others**, and **No current action**. Each entry explains why it appears, links to supporting activity, and suggests a next step. Inferred or uncertain responsibility is labeled. PR suggestions can point to review or triage; issues and Discussions get a suggested next step with a conversation link. The report is read-only, and follow-up actions remain suggestions.

| Option | Behavior |
|--------|----------|
| `--repo owner/name` | Select a repository explicitly, including outside a checkout. Default follows the invoking `gh` repository context. |
| `--type pr,issue,discussion` | Select any combination; repeat to combine selections. Default: all three types. |
| `--limit N` | Select the most recently updated items per type, from 1 to 100. Default: 10 per type. |
| `--since YYYY-MM-DD` | Filter every selected type by its last update. |
| `--help` | Show collector options without contacting GitHub. |

By default, PRs and issues are open, including draft PRs, with no recency cutoff. Discussions cover the last 90 days of activity, including answered and closed conversations. An explicit `--since` replaces that window and applies to all selected types.

The report states its scope and coverage. Discovery is bounded to 100 matches per relevance reason, and long bodies and conversations are shortened. Reached limits, missing context, failed sources, and disabled or inaccessible Discussions are shown explicitly. Participation or a recent update alone does not mean you owe a response.

The inbox requires Python 3.9+ and `gh` authenticated for the selected repository. It uses the existing plugin installation and works independently of a spec-kit ship pipeline.

### Code Review

```
/review
```

Reviews all changed files on the current branch against main. Dispatches every enabled reviewer, merges findings, and runs the fix loop.

```
/review --pr 42
```

Reviews the diff of a specific PR.

```
/review --spec specs/feature/spec.md
```

Cross-checks implementation against a specification file. The goal alignment agent verifies each functional requirement (FR-NNN) is implemented.

```
/review --no-fix --no-external
```

Skip the autonomous fix loop and external tool integration. Produces a report only.

```
/review --only security,gator
```

Dispatch only the named reviewers. Any discovered reviewer name works here and in `--no-<name>`.

**All review flags:**

| Flag | Description |
|------|-------------|
| `--pr <number>` | Review a specific PR's diff |
| `--spec <path>` | Specification file for compliance checking |
| `--hints <path>` | Review hints file (default: `.cc-review/review-hints.md`) |
| `--output <path>` | Output report path (default: `./review-findings.md`) |
| `--config <path>` | Explicit config file |
| `--profile <name>` | Profile preset (`quick`, `thorough`, `ci`) |
| `--no-fix` | Skip autonomous fix loop |
| `--max-rounds <n>` | Maximum fix loop rounds (default: 3) |
| `--no-external` / `--external` | Disable or enable all command (external tool) reviewers |
| `--no-<reviewer>` | Skip one reviewer by name (for example `--no-codex`, `--no-test-quality`) |
| `--only <reviewer,...>` | Dispatch only the listed reviewers (overrides config, not preconditions) |
| `--no-meta-review` | Skip the skeptic/calibrator meta-review pass |
| `--sequential` | Run reviewers one at a time (default: parallel) |
| `--parallel` | Run reviewers in parallel (the default; accepted for compatibility) |
| `--bulk` | Review several PRs in one run (see Bulk Mode below) |
| `--all-open` | Bulk: select every open PR |
| `--search <query>` | Bulk: select the open PRs matching a GitHub search |
| `--limit <n>` | Bulk: at most this many PRs (default: 10) |
| `--unattended` | Bulk: no questions, apply the fixed policy |
| `--resume [<run-id>]` | Bulk: continue an unfinished run |

With `--pr` on a branch other than the PR's own, the PR is checked out into a separate worktree under `.cc-review/pr-worktrees/` and reviewed there, so your working tree stays as it is.

### PR Comment Triage

```
/triage
```

Fetches PR review threads, classifies them as bot or human, and handles each according to its triage profile.

```
/triage --pr 42
```

Triage comments on a specific PR.

```
/triage --spec specs/feature/spec.md
```

Triage with spec context for assessing whether suggestions align with requirements.

**All triage flags:**

| Flag | Description |
|------|-------------|
| `--pr <number>` | Target PR number |
| `--spec <path>` | Specification file for context |
| `--no-coverage-fix` | Skip automatic coverage remediation |
| `--idea-inbox <path>` | File for capturing out-of-scope ideas |
| `--bulk`, `--search`, `--limit`, `--unattended`, `--resume` | Triage several of your PRs in one run (see Bulk Mode below) |

### Bulk Mode

```
/review --bulk
```

Reviews the open PRs that request your review, plus PRs you reviewed with cc-review that got new commits since. Each PR is analyzed in its own worktree, and at the end you get one table to decide per PR: post the review, apply the suggested fixes (your own PRs only), post a short "no findings" note, or skip.

```
/review --bulk --search 'label:needs-review' --limit 5
/review --bulk --all-open
```

Pick the PRs with a GitHub search, or take every open PR. Drafts and PRs already reviewed at their current head are skipped.

```
/triage --bulk
```

Triages your own open PRs that have unresolved threads. Bot suggestions that cc-review judges valid are fixed in a prepared commit and every bot comment gets a drafted reply; you approve the pushes and replies in one table and answer human comments in the same step.

```
/review --bulk --resume --unattended
```

Continues an unfinished run, or starts a new one, without asking anything. This is the form for scheduled jobs. Unattended reviews are posted as plain comments, no code is changed, and human comments in triage are left for you.

Run state and reports live in `.cc-review/bulk/<run-id>/` (git-ignored); `state.md` shows the progress. See the [standalone guide](docs/standalone-guide.md#bulk-review-and-triage) for the details.

## Configuration

Copy the template to your project or home directory:

```bash
# Project-level (takes precedence)
mkdir -p .cc-review
cp review/config/config-template.yml .cc-review/config.yml

# User-level (fallback)
mkdir -p ~/.cc-review
cp review/config/config-template.yml ~/.cc-review/config.yml
```

Resolution order: CLI flags > `--config` > `--profile` > project config (`.cc-review/config.yml`) > user config (`~/.cc-review/config.yml`) > built-in defaults > the reviewer's own `enabled` default.

### Configuration options

```yaml
reviewers:                # one key per discovered reviewer; omit a key to use the reviewer's default
  correctness: true
  architecture: true
  security: true
  production: true
  test-quality: true
  goal-alignment: true
  coderabbit: true        # command reviewer (CodeRabbit CLI)
  copilot: false          # command reviewer (Copilot CLI)
  codex: true             # command reviewer (Codex CLI)
  gator: false            # opt-in principal-engineer reviewer

test:
  command: ""             # Auto-detected from Makefile/go.mod/package.json/pyproject.toml
  timeout_seconds: 300

triage:
  bot_profiles:
    - login: "coderabbitai[bot]"
      self_resolves: true
      auto_resolve: false
    - login: "copilot[bot]"
      self_resolves: false
      auto_resolve: true
  codecov:
    patch_threshold: 80
    auto_remediate: true

max_fix_rounds: 3
output:
  dir: "."
```

The legacy keys `agents.<name>` and `external_tools.<name>` are deprecated. They keep working for the migrated reviewers (`agents.test_quality` maps to `reviewers.test-quality`) and print a one-line warning pointing to the new key.

### Adding a reviewer

Create `.cc-review/reviewers/<name>.md` with a short frontmatter and a prompt body:

```markdown
---
name: accessibility
display_name: "Accessibility"
kind: prompt
category: accessibility
---
You are the ACCESSIBILITY REVIEW AGENT. ...
```

The reviewer is discovered on the next run, dispatched alongside the built-ins with the common preamble prepended, and shown in the console summary. Reviewers in `~/.cc-review/reviewers/` follow you across projects; a project reviewer with the same name as a bundled one replaces it. External tools are `kind: command` reviewers with `detect`, `invoke`, and an output format declaration. The full format is documented in [docs/reviewer-plugins.md](docs/reviewer-plugins.md).

### Review Hints

Create `.cc-review/review-hints.md` in your project root to provide project-specific patterns and context to all review agents. Use this for framework-specific behaviors, known edge cases, or architectural decisions that are not apparent from the code alone.

## Architecture

cc-review separates portable review logic from harness-specific wiring. The `review/` directory is a single distributable plugin that contains native manifests for all three major AI coding agent harnesses:

```
review/                  Plugin directory (distributable)
  .claude-plugin/        Claude Code plugin manifest
  .codex-plugin/         Codex plugin manifest
  skills/                Command shims (Claude Code and Codex)
  opencode/              OpenCode commands + install script
  core/                  Harness-agnostic review engine
    reviewers/           Bundled reviewer plugins (6 prompt, 3 command, gator)
    agents/              Shared preamble + meta-review critics (skeptic, calibrator)
    commands/            Command definitions (review.md, init.md, triage.md)
    scripts/             Shell utilities (reviewer discovery, config resolution, platform detection)
    schemas/             Finding and reviewer frontmatter schemas (JSON Schema)
  config/                Default configuration template and profiles

speckit/                 Optional spec-kit extension (separate distribution)
```

Each harness reads its own manifest and command directory. Command shims resolve the core directory at runtime and delegate to the core command files. Shims add no review logic; they translate between the harness's discovery mechanism and the core's interface.

### Reviewer Discovery

The review command holds no list of reviewers. `core/scripts/discover-reviewers.sh` scans three layers on every run and emits the reviewers to dispatch; `core/scripts/reviewer-runtime.sh` holds the helpers that apply enablement, CLI selection and tool detection to that list:

| Layer | Path | Precedence |
|-------|------|------------|
| project | `.cc-review/reviewers/` | highest |
| user | `~/.cc-review/reviewers/` | middle |
| bundled | `core/reviewers/` | lowest |

A higher layer replaces a lower one by name, except that a project reviewer edited by the change under review is ignored for that run, and a project `kind: command` reviewer runs nothing until you trust it in `~/.cc-review/trusted-reviewers` (see `docs/reviewer-plugins.md`). Each reviewer is `kind: prompt` (dispatched as a fresh-context subagent with the common preamble prepended) or `kind: command` (an external tool run with a timeout and parsed per its declared output format). Preconditions (`requires: [pr]`, `binary:<name>`), detection results, and config enablement decide which reviewers run; every discovered reviewer appears in the console summary as completed, disabled, skipped, or failed.

### Bundled Reviewers

| Reviewer | Kind | Default | Scope |
|----------|------|---------|-------|
| Correctness | prompt | on | Bugs, logic errors, null safety, resource cleanup, concurrency |
| Architecture & Idioms | prompt | on | Dead code, complexity, duplication, naming, YAGNI, conventions |
| Security | prompt | on | Injection, secrets, auth, path traversal, deserialization, rate limiting |
| Production Readiness | prompt | on | Resource leaks, unbounded growth, error amplification, graceful shutdown |
| Test Quality | prompt | on | Coverage gaps, weak assertions, edge cases, spec-anchored validation |
| Goal Alignment | prompt | on (needs PR) | Goal delivery verification, undeclared change detection, scope assessment |
| CodeRabbit | command | on | CodeRabbit CLI findings |
| Copilot | command | off | GitHub Copilot CLI findings |
| Codex | command | on | Codex CLI findings |
| Gator | prompt | off | Principal-engineer review (pragmatism, user empathy, security) with an evidence contract; ported from NVIDIA OpenShell |

All prompt reviewers share a common preamble that enforces anti-sycophancy, confidence scoring (minimum 70, or 50 for Critical), structured output, and spec awareness.

### Finding Schema

Every finding follows a structured schema (`core/schemas/finding.schema.json`) with severity levels (Critical, Important, Minor, Notable), confidence scores, file locations, and resolution tracking. Findings are deduplicated across reviewers before reporting; a reviewer's `severity_map` translates its native severities into this scheme.

### Gate Logic

- Critical + Important = 0: **GATE PASS**
- Critical + Important > 0: enter fix loop (or fail if `--no-fix`)
- Notable findings are informational and excluded from the gate check

## License

[MIT](LICENSE)
