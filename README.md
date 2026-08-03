# cc-review

Multi-agent code review plugin for AI coding agents. Works with Claude Code, Codex, and OpenCode.

cc-review dispatches 6 specialized review agents against your code changes, merges and deduplicates findings across agents and external tools, then runs an autonomous fix loop to resolve Critical and Important issues before you see the report.

## Features

- **6 specialized review agents**: Correctness, Architecture & Idioms, Security, Production Readiness, Test Quality, Goal Alignment
- **Autonomous fix loop**: automatically applies fixes for Critical/Important findings, re-reviews, and repeats (up to 3 rounds by default)
- **External tool integration**: CodeRabbit, GitHub Copilot CLI, and Codex CLI findings are merged and deduplicated with agent findings
- **PR comment triage**: classify and handle bot review comments (CodeRabbit, Copilot, Devin) and human reviewer feedback
- **Spec-aware review**: pass a specification file to cross-check implementation against functional requirements
- **Multi-harness support**: thin adapter layer for Claude Code, spec-kit, and AGENTS.md-based tools (Codex, OpenCode)

## Installation

### Claude Code

Run the install script to symlink commands into your Claude Code commands directory:

```bash
# Project-local install
./adapters/claude-code/install.sh

# Global install (available in all projects)
./adapters/claude-code/install.sh --global

# Install for a specific project
./adapters/claude-code/install.sh --project-dir /path/to/project
```

This creates symlinks in `.claude/commands/` (or `~/.claude/commands/` for global) pointing to the adapter's SKILL.md files. The adapter resolves the cc-review core at runtime.

### spec-kit

Install as a spec-kit extension:

```bash
specify extension add /path/to/cc-review/adapters/speckit
```

Or symlink manually:

```bash
ln -s /path/to/cc-review/adapters/speckit ~/.specify/extensions/cc-review
```

The spec-kit adapter automatically passes spec paths, constitution hints, and output locations during the ship pipeline.

### Codex / OpenCode (AGENTS.md)

Run the install script to append the cc-review agent fragment to your AGENTS.md:

```bash
# Project-local
./adapters/agents-md/install.sh

# Global
./adapters/agents-md/install.sh --global

# Specific project
./adapters/agents-md/install.sh --project-dir /path/to/project
```

If AGENTS.md already exists and contains the cc-review section, the script exits without modification.

## Usage

### Code Review

```
/review
```

Reviews all changed files on the current branch against main. Dispatches 6 review agents, merges findings, and runs the fix loop.

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

**All review flags:**

| Flag | Description |
|------|-------------|
| `--pr <number>` | Review a specific PR's diff |
| `--spec <path>` | Specification file for compliance checking |
| `--hints <path>` | Review hints file (default: `.cc-review/review-hints.md`) |
| `--output <path>` | Output report path (default: `./review-findings.md`) |
| `--no-fix` | Skip autonomous fix loop |
| `--max-rounds <n>` | Maximum fix loop rounds (default: 3) |
| `--no-external` | Skip all external tools |
| `--no-coderabbit` | Skip CodeRabbit |
| `--no-copilot` | Skip Copilot CLI |
| `--no-codex` | Skip Codex CLI |
| `--parallel` | Run review agents in parallel |
| `--sequential` | Run review agents sequentially (default) |

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

## Configuration

Copy the template to your project or home directory:

```bash
# Project-level (takes precedence)
mkdir -p .cc-review
cp config/config-template.yml .cc-review/config.yml

# User-level (fallback)
mkdir -p ~/.cc-review
cp config/config-template.yml ~/.cc-review/config.yml
```

Resolution order: CLI flags > project config (`.cc-review/config.yml`) > user config (`~/.cc-review/config.yml`) > built-in defaults.

### Configuration options

```yaml
external_tools:
  coderabbit: true       # Enable CodeRabbit integration (default: true)
  copilot: false          # Enable Copilot CLI integration (default: false)
  codex: true             # Enable Codex CLI integration (default: true)

test_command: ""          # Auto-detected from Makefile/go.mod/package.json/pyproject.toml
test_timeout_seconds: 300

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
output_dir: "."
```

### Review Hints

Create `.cc-review/review-hints.md` in your project root to provide project-specific patterns and context to all review agents. Use this for framework-specific behaviors, known edge cases, or architectural decisions that are not apparent from the code alone.

## Architecture

cc-review separates portable review logic from harness-specific wiring:

```
core/               Harness-agnostic review engine
  agents/            6 review agent prompts + shared preamble
  commands/          Command definitions (review.md, triage.md)
  scripts/           Shell utilities (config resolution, platform detection, triage state)
  schemas/           Finding schema (JSON Schema)

adapters/            Thin wrappers (< 50 lines each)
  claude-code/       SKILL.md files + install script
  speckit/           extension.yml + spec-kit command wrappers
  agents-md/         AGENTS.md fragment + install script

config/              Default configuration template
```

Each adapter resolves the core directory at runtime and delegates to the core command files. Adapters add no review logic; they translate between the harness's command format and the core's interface. The adapter contract: resolve core path, pass through arguments, stay under 50 lines.

### Review Agents

| Agent | Scope |
|-------|-------|
| Correctness | Bugs, logic errors, null safety, resource cleanup, concurrency |
| Architecture & Idioms | Dead code, complexity, duplication, naming, YAGNI, conventions |
| Security | Injection, secrets, auth, path traversal, deserialization, rate limiting |
| Production Readiness | Resource leaks, unbounded growth, error amplification, graceful shutdown |
| Test Quality | Coverage gaps, weak assertions, edge cases, spec-anchored validation |
| Goal Alignment | Goal delivery verification, undeclared change detection, scope assessment |

All agents share a common preamble that enforces anti-sycophancy, confidence scoring (minimum 70, or 50 for Critical), structured output, and spec awareness.

### Finding Schema

Every finding follows a structured schema (`core/schemas/finding.schema.json`) with severity levels (Critical, Important, Minor, Notable), confidence scores, file locations, and resolution tracking. Findings are deduplicated across agents and external tools before reporting.

### Gate Logic

- Critical + Important = 0: **GATE PASS**
- Critical + Important > 0: enter fix loop (or fail if `--no-fix`)
- Notable findings are informational and excluded from the gate check

## License

[MIT](LICENSE)
