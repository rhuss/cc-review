# Review Guide: Pluggable Reviewers

**Generated**: 2026-10-13 | **Spec**: [spec.md](spec.md)

## Why This Change

Today the review command (`review/core/commands/review.md`) hard-codes its six built-in review agents and three external CLI tools (CodeRabbit, Copilot CLI, Codex CLI): their paths, prompts, detection checks, invocation commands, and output parsing all live inline in the orchestrator. Adding a new review perspective means editing core files, and the external tools follow a different code path from the prompt agents, so two dispatch models have to be maintained. There is also no way for a team or an individual to add or replace a reviewer for one project without forking the plugin.

## What Changes

Reviewers become plugins: a markdown file with YAML frontmatter (metadata) and a body (the prompt, or parsing notes for CLI tools), optionally in a directory form with supporting files. Two kinds exist, `prompt` (dispatched as a fresh-context subagent) and `command` (an external tool detected, invoked, and parsed). Reviewers are discovered on every run from three layers, project (`.cc-review/reviewers/`), user (`~/.cc-review/reviewers/`), and bundled (`core/reviewers/`), with higher layers replacing lower ones by name. The six built-in agents and the three CLI tools migrate to this format, so the review command contains no reviewer-specific knowledge afterwards. Configuration collapses `agents.*` and `external_tools.*` into `reviewers.<name>` (legacy keys keep working for one release with a deprecation warning), and CLI flags `--no-<name>` and `--only a,b` are derived from the discovered names. A `gator` reviewer ported from NVIDIA/OpenShell's principal-engineer-reviewer ships disabled by default as the first contributed plugin. The finding pipeline (dedup, meta-review, fix loop, report, PR posting) is otherwise unchanged.

Breaking changes for users: none intended. Default config keys and the config template change shape, but legacy keys and the legacy `--no-coderabbit`/`--no-copilot`/`--no-codex` flags continue to work. The finding schema's `category` field loses its enum and becomes an open identifier, which is a loosening, not a break.

## How It Works

- **Discovery script** (`review/core/scripts/discover-reviewers.sh`, new): scans bundled, then user, then project directories for `<name>.md` or `<name>/reviewer.md`, extracts frontmatter with `yq --front-matter=extract`, validates it with `jq` against the rules in `contracts/reviewer-frontmatter.md`, resolves overrides (later layer replaces earlier, invalid entries never shadow valid ones), evaluates preconditions (`pr`, `spec`, `binary:<x>`, plus `detect`/`auth_check` for command reviewers), and emits one JSON array (`contracts/discovery-output.md`) with a `status` per reviewer: ready, disabled, skipped (reason), invalid. When sourced instead of executed it provides helpers: `run_with_timeout`, `substitute_invoke`, `apply_cli_selection`, `map_severity`.
- **Review command** (`review.md`, modified): calls discovery once, stores `REVIEWERS_JSON`, applies `reviewers.<name>` config and CLI selection, then iterates ready entries. Prompt reviewers get a subagent prompt assembled as preamble + body + each `references` file under `## Reference: <path>` + review target + spec/hints + requested `context` blocks (`goals` only) + output contract. Command reviewers run through `run_with_timeout` with placeholders substituted and are parsed per their `output.format` (`json`, `delimited`, or `parser` script). Findings receive `source_agent`, `category`, and a severity mapped through `severity_map`. The same JSON drives the console table, the report header, and fix-loop re-dispatch.
- **Config resolution** (`resolve-config.sh`, modified): dotted keys converted to `yq` bracket paths so hyphenated names work; a new `resolve_config_migrate_legacy_keys` maps `agents.*` / `external_tools.*` to `reviewers.<hyphenated>` with one warning each; type validation becomes generic over `reviewers.*`.
- **Generalizations in the pipeline**: dedup honors a per-reviewer `dedup: isolated` flag instead of a by-name goal-alignment exemption; "What Went Well" aggregates a `Positive observations:` section from any prompt reviewer instead of depending on goal-alignment; `finding.schema.json` `category` becomes `^[a-z0-9-]+$`.
- **Migration**: six agent files move (`git mv`) from `core/agents/` to `core/reviewers/` with frontmatter prepended; `core/agents/` keeps the preamble and the meta-review critics. Three new `kind: command` files encode the current CodeRabbit, Copilot, and Codex handling. `detect-tools.sh` derives tool availability from discovery output. `init.md` lists discovered reviewers and emits `reviewers.*` keys.
- **Gator**: `core/reviewers/gator/reviewer.md` plus `references/findings-contract.md`, ported from OpenShell commit 5e414ea with OpenShell-specific sections removed and an Apache-2.0 attribution block. Verbatim upstream sources are kept under `specs/004-reviewer-plugins/upstream/`.
- **Testing**: new `tests/run.sh` (plain bash assertions, `make test`) covers discovery, config mapping, CLI selection helpers, and severity mapping with fixtures under `tests/fixtures/reviewers/`. Prompt dispatch is validated manually through `quickstart.md`.

tasks.md organizes this into 9 phases and 58 tasks (Setup 3, Foundational 18, then one phase per user story, then Polish 7). `review.md` is touched by 11 tasks and must be edited sequentially.

## When It Applies

**Applies when**:
- Any `/review` run: discovery happens every time, with no install or registration step.
- A project, user, or the bundled plugin provides a reviewer file in one of the three layers.
- Config uses `reviewers.<name>` or the legacy `agents.*` / `external_tools.*` keys.
- CLI flags `--no-<name>`, `--only`, `--external`, `--no-external` are used.
- `/cc-review:init` runs (it lists discovered reviewers and generates `reviewers.*` keys).
- The fix loop re-dispatches reviewers (it reuses the first-round discovery decisions).

**Does not apply when**:
- Meta-review (skeptic, calibrator): these consume findings rather than produce them and stay in the core.
- Remote plugin sources (git URLs, catalogs): deferred; discovery is filesystem-only.
- Gator's OpenShell sandbox pipeline or GitHub label state machine: out of scope; only the prompt is ported.
- Triage bot-profile configuration: unchanged; deriving profiles from command reviewer metadata is a possible follow-up.
- Per-reviewer opt-out of autonomous fixing: not offered; all plugin findings enter the fix loop under existing severity rules.

## Key Decisions

1. **Markdown with YAML frontmatter as the plugin format.** Alternatives: JSON/YAML manifests with separate prompt files, or a programmatic plugin API. Chosen because it is harness-agnostic, matches how the agents are already written, and keeps a reviewer to one file in the common case.
2. **Discovery in a shell script that emits JSON, not in command prose.** Alternatives: describe discovery inline in `review.md`, or a Python tool. Chosen so the deterministic rules (validation, overrides, preconditions) are testable and the orchestrating model only iterates a list. Mirrors the existing `resolve-config.sh` / `review.md` split. (research.md R-002, R-008)
3. **Whole-entry override across layers, no field merging.** A project `security.md` fully replaces the bundled one; an invalid higher-layer file falls back to the valid lower one with a warning. Chosen for predictability. (R-003)
4. **Preamble always applied, no opt-out.** The common preamble (anti-sycophancy, confidence scoring, output format) is the core's quality contract; plugin authors adjust conflicting instructions. Gator's "if something is good, say so" line is dropped for this reason. (Clarification 1)
5. **Explicit `references` list for supporting files, inlined after the body.** Alternatives: expose the whole plugin directory, or templating/include directives in the body. Chosen so what reaches the prompt is explicit and paths are validated at discovery time. (Clarification 2)
6. **By-name special cases replaced with metadata.** Goal-alignment's goals context block, dedup exemption, and "What Went Well" ownership become `context: [goals]`, `dedup: isolated`, and a `Positive observations:` section any prompt reviewer may emit. This is what lets `review.md` be free of reviewer names (FR-028). (Clarification 3, R-007, R-009)
7. **Hyphenated reviewer names as the universal identifier.** Used for config keys, derived flags, `source_agent`, and console rows. Required extending `resolve-config.sh` to bracket paths for `yq`. Legacy underscore keys are mapped. (R-004)
8. **Three command output formats: `json`, `delimited`, `parser`.** Alternatives: a regex field language in frontmatter, or JSON-only. Chosen to cover the three migrated tools without wrappers while leaving an escape hatch (`parser` script). (R-005)
9. **Positive observations in the subagent's final text, not in the ReportFindings tool payload.** The tool schema is harness-owned; the plugin cannot change it. (R-007)
10. **Add an automated bash test runner.** Prior features relied on manual validation only. The number of discovery rules justified `tests/run.sh` and `make test`, without adopting bats-core. (R-011)
11. **CLI precedence: `--only` overrides config enablement but not preconditions; `--no-<name>` subtracts from `--only`; empty set is an error.** (Clarification 5, FR-017, FR-017a)

## Areas Needing Attention

- **Parsing of `delimited` output is done by the orchestrating model, not by a script.** R-005 leaves `json` and `delimited` parsing to the orchestrator following the body's parsing notes; only `parser` scripts are deterministic. This matches today's behavior for the three CLI tools but means the "declared output format" is a guide rather than a hard contract. Reviewers should decide whether this is acceptable or whether `delimited` should get a shell implementation.
- **`review.md` is edited by 11 tasks across 5 phases.** The spec forbids any reviewer-specific reference in that file afterwards (SC-003, verified by `rg` in T032). The sequential editing constraint and the risk of leaving a stale reference deserve a careful final read of the whole command.
- **Legacy config mapping is "for at least one release."** No removal date or version is set. Decide whether the deprecation should name the version that drops support.
- **`--only` overriding a config-disabled reviewer** (FR-017) is consistent with CLI-over-config precedence, but it means `--only gator` dispatches a reviewer the team deliberately disabled. Confirm this is the intended ergonomics.
- **Timeouts degrade gracefully on macOS without coreutils.** `run_with_timeout` runs unbounded when neither `timeout` nor `gtimeout` exists and only logs at verbose level (R-006). A hanging command reviewer could then stall the review on a stock macOS.
- **Performance budget of under one second for 30 reviewers** relies on one `yq` call per file plus running `detect` and `auth_check` shell commands during discovery. Auth checks like `coderabbit auth status` or `gh auth status` may do network calls; the `--skip-detection` flag exists for `init` and tests but the normal review path always runs them.
- **The `category` enum is removed from `finding.schema.json`.** Anything downstream that assumed a closed category set (report grouping, triage) should be checked.
- **Reserved flag words** (`external`, `fix`, `meta-review`, `only`, `sequential`, `parallel`) are a hand-maintained list in the discovery script. Any future non-reviewer `--no-<x>` flag must be added there or a reviewer could shadow it.
- **The gator port is a judgment-heavy edit of a third-party prompt.** R-010 lists precisely what to keep and drop; reviewers should spot-check `review/core/reviewers/gator/reviewer.md` against `specs/004-reviewer-plugins/upstream/` for accidental OpenShell residue and confirm the Apache-2.0 attribution is complete (URL, commit, license).
- **Directory-form same-layer duplicates: file form wins.** This is a convention choice with a warning; an alternative would be to treat it as an error. Low stakes but worth confirming.

## Open Questions

- Should `delimited` output parsing move from orchestrator judgment into `discover-reviewers.sh` (or a sibling script) so command reviewer output handling is testable? Currently deferred to keep parity with today's behavior.
- Which release drops the legacy `agents.*` / `external_tools.*` keys and the deprecation warning?
- Auto-deriving triage bot profiles from command reviewer metadata is noted as a possible follow-up but not scheduled.

## Review Checklist

- [ ] Key decisions are justified
- [ ] Breaking changes are documented with migration guidance
- [ ] Scope matches the stated boundaries
- [ ] Success criteria are achievable
- [ ] No unstated assumptions
- [ ] No file under `review/core/reviewers/` names a harness tool (`ReportFindings`, `Agent`)
- [ ] `review/core/commands/review.md` contains no reviewer names, prompts, or invocation commands after migration (SC-003)
- [ ] Legacy keys and legacy `--no-coderabbit`/`--no-copilot`/`--no-codex` flags still work with a warning
- [ ] Harness shims stay under 50 lines and add no review logic
- [ ] Gator plugin carries upstream URL, commit, and Apache-2.0 notice; no OpenShell-specific instructions remain
- [ ] `make test` passes and covers discovery, config mapping, CLI selection, and severity mapping

---

<!-- Code phase sections are appended below this line by the phase-manager command -->
