# Code Review: Pluggable Reviewers

**Spec:** specs/004-reviewer-plugins/spec.md (with contracts/ and data-model.md)
**Branch:** 004-reviewer-plugins (base: main)
**Date:** 2026-10-13
**Reviewer:** Claude (speckit-spex-gates-review-code, speckit-spex-deep-review-run)
**Invocation:** quality-gate (ship pipeline, autonomous)

## Compliance Summary

**Overall Score: 96.9% (63 of 65 items compliant, 2 minor deviations, 0 missing)**

| Group | Compliant | Total | Score |
|-------|-----------|-------|-------|
| Functional requirements (FR-001 to FR-033, with a/b items) | 38 | 39 | 97.4% |
| Edge cases | 17 | 18 | 94.4% |
| Success criteria (SC-001 to SC-008) | 8 | 8 | 100% |
| **Total** | **63** | **65** | **96.9%** |

The score was computed on the tree after fix round 2 and rechecked after fix round 3; the fix rounds changed no compliance status. Evidence below cites the current tree.

## Functional Requirements

| Req | Status | Implementation / notes |
|-----|--------|------------------------|
| FR-001 file form | Compliant | `discover-reviewers.sh` `_discover_scan_layer` enumerates `<name>.md`; body split by awk into `body_file` |
| FR-002 directory form | Compliant | `<name>/reviewer.md` enumeration; `gator/`, `coderabbit/` ship in this form |
| FR-003 metadata fields and defaults | Compliant | `CC_REVIEW_VALIDATE_JQ` record defaults (display_name, category, enabled, requires, severity_map, dedup); tests in `test_discovery_valid_file_form` |
| FR-003a references, context | Compliant | validator checks list types and `goals` as the only context block (`ctx-bad` test) |
| FR-003b inline references, containment | Compliant | `_discover_check_relative` rejects absolute, `..`, symlinked final component and symlinked parents (including dash-prefixed parents); review.md Prompt Construction inlines `## Reference:` blocks |
| FR-004 command fields and placeholders | Compliant | detect, auth_check, invoke, timeout_seconds (default 120), output json/delimited/parser; unknown `{word}` placeholders rejected. Extra: `{files}` input is one path per line so paths with spaces stay whole |
| FR-004a `{pr_number}` without PR | Compliant | skipped `requires: pr` even in block scalars and with `--skip-detection` (tests) |
| FR-005 name pattern and match | Compliant | `invalid name` / `name does not match file or directory name`; control-character names rejected before framing |
| FR-006 harness-free bodies, core assembles prompt | Compliant | review.md Prompt Construction order: preamble, body, references, target, spec, hints, goals, output contract |
| FR-006a preamble always applied | Compliant | no opt-out field exists; gator dropped its praise instruction |
| FR-006b positive_observations aggregated | **Deviation (minor)** | Realized as a `Positive observations:` text section in each prompt reviewer's final output (review.md Step 3 and 7.5j), not a structured list in ReportFindings, which has no such field. Aggregation into "What Went Well" works without a reviewer name. Spec evolution candidate |
| FR-007 precondition tokens | Compliant | `pr`, `spec`, `binary:<name>`; unknown token skipped with warning (tests) |
| FR-008 three layers, precedence | Compliant | bundled, user, project scanned in order; later valid entries overwrite |
| FR-009 override, no merge, fallback | Compliant | `overrides` field, " (project override)" console suffix; invalid higher layer never shadows (fallback warning); name-keyed updates in review.md now skip invalid twins |
| FR-010 validation warnings name file and reason | Compliant | one `Warning: skipping reviewer <path>: <reason>` per invalid file |
| FR-011 discovery every run | Compliant | review.md Step 2 runs the script unconditionally; no registry |
| FR-012 zero valid reviewers stops | Compliant | review.md `VALID_COUNT` guard; discovery failure exits 1 with the cause |
| FR-013 `reviewers.<name>` with frontmatter default | Compliant | review.md Reviewer Enablement; contract cli-and-config.md places template defaults above frontmatter, documented in docs/reviewer-plugins.md |
| FR-014 legacy keys mapped with warning | Compliant | `resolve_config_migrate_legacy_keys` per layer before merge; underscore to hyphen; init migrates an existing config before merging |
| FR-015 `--no-<name>`, `--only`, unknown errors | Compliant | `apply_cli_selection`; unknown name lists discovered names once; invalid-only name reports its reason |
| FR-016 `--no-external` / `--external` | Compliant | command kinds only (tests) |
| FR-017 CLI over config, not over preconditions | Compliant | `--only` revives `disabled`, never `skipped`/`invalid` (tests) |
| FR-017a `--only` minus `--no-` | Compliant | empty result errors "no reviewers remain" |
| FR-018 profiles and template use `reviewers.*` | Compliant | `test_config_template_and_profiles_use_reviewers_keys` |
| FR-019 parallel fresh-context dispatch | Compliant | review.md Prompt Reviewer Dispatch: one Agent call per ready prompt entry in a single response; `--sequential` |
| FR-020 command invocation, auth, timeout, parsing | Compliant | per-entry tool call, `substitute_invoke`, `run_with_timeout` (timeout, gtimeout, perl with process-group kill), stdout-only parsing |
| FR-021 source_agent, category, severity_map | Compliant | review.md Step 4 normalization, `map_severity` exact lookup with pass-through |
| FR-022 failures never block | Compliant | subagent error, timeout, exit, parse error (parser non-zero exit included) marked failed |
| FR-023 every reviewer listed with status | Compliant | review.md Step 8 table and findings report "Reviewers completed" line |
| FR-024 fix loop reuses set | Compliant | review.md fix loop step 6 re-dispatches the same READY sets without re-discovery |
| FR-025 meta-review unchanged, dedup honors `dedup` | Compliant | Step 4 rules 4 and 5 key on `dedup`, not names |
| FR-026 six bundled prompt reviewers | Compliant | `review/core/reviewers/*.md`; goal-alignment declares `requires: [pr]`, `context: [goals]`, `dedup: isolated`, positive observations pass |
| FR-027 coderabbit, copilot, codex bundled | Compliant | Detection and default enablement preserved. CodeRabbit parsing moved to a `parser` script because the shipping CLI prints JSON lines, not `=============` blocks (the spec Assumption allows the parser fallback). Codex auth check now `codex login status` |
| FR-028 no reviewer names in review.md | Compliant | `rg -w` for all ten reviewer names in review.md returns nothing |
| FR-029 init lists reviewers, emits `reviewers.*` | Compliant | init.md Step 1 table (layer, kind, enabled, preconditions) and Step 3 config |
| FR-030 gator directory form, disabled, ported | Compliant | `gator/reviewer.md` `enabled: false`, persona and calibration kept, OpenShell specifics removed, `references: [references/findings-contract.md]` |
| FR-031 evidence contract | Compliant | findings-contract.md lists all nine items; evidence goes into `failure_scenario`, stored as the finding's rationale |
| FR-032 gator severity_map | Compliant | Critical, Warning to Important, Suggestion to Minor |
| FR-033 attribution | Compliant | Attribution section with upstream URL and Apache-2.0 notice |

## Edge Cases

| Edge case | Status | Evidence |
|-----------|--------|----------|
| Malformed metadata (YAML, name, kind) | Compliant | `badyaml`, `noname`, unknown kind tests; siblings stay ready |
| Name pattern / mismatch | Compliant | `Upper`, `mismatch` tests |
| Same name twice in one layer | Compliant | file form wins, warning (`dup` test) |
| Directory without reviewer.md ignored | Compliant | `[ -f "$entry/reviewer.md" ] || continue`; `orphan-dir` fixture |
| Empty prompt body | Compliant | `empty prompt body` test |
| Reference outside dir or missing | Compliant | `missing-ref`, `dotdot-ref`, symlink tests |
| `context: [goals]` without PR | Compliant | `ctx-only` stays ready; block omitted |
| `--only a,b --no-a` / `--only a --no-a` | Compliant | selection tests |
| Command without invoke or output | Compliant | `cmd-noinvoke`, `cmd-nooutput` tests |
| Reserved names | Compliant | `fix.md` reserved-name test |
| No reviewers discovered | Compliant | review.md FR-012 stop; script prints `[]` and removes its directory |
| All disabled or skipped | Compliant | review.md "no reviewers to run" listing |
| Unknown precondition token | Compliant | `unknown-req` test |
| Severity map value outside scheme | **Deviation (minor)** | The reviewer is rejected at discovery (`invalid severity_map value`) instead of its findings being dropped at merge time. Stricter and earlier; spec evolution candidate |
| Native severity missing from a non-identity map | Compliant | `map_severity` pass-through or drop with warning |
| Invalid user reviewer shadowing bundled | Compliant | fallback warning test |
| Unrecognized fields | Compliant | verbose `Note:` test |
| Fix loop re-dispatch | Compliant | same sets reused (FR-024) |

## Success Criteria

| SC | Status | Evidence |
|----|--------|----------|
| SC-001 one file, no core change | Compliant | project `marker.md` fixture discovered and ready |
| SC-002 default dispatch set unchanged | Compliant | six prompt reviewers plus CodeRabbit and Codex when available, Copilot disabled; goal-alignment again sees the current branch's PR |
| SC-003 no reviewer references in review.md | Compliant | verified by `rg` |
| SC-004 harness-agnostic reviewers | Compliant (inspection) | bodies contain no harness tool names (test); shims for Claude Code, Codex, OpenCode delegate to the core |
| SC-005 invalid file never aborts | Compliant | discovery exit 0 with invalid entries; framing-breaking names rejected per file |
| SC-006 legacy keys same decisions | Compliant | cross-layer legacy precedence tests |
| SC-007 gator finding with invariant and base/head | Compliant (inspection) | evidence contract requires both; live run not performed |
| SC-008 derived flags for contributed reviewers | Compliant | `apply_cli_selection` is name-agnostic; works from zsh via the helper subcommand |

## Extra Features (not in spec)

- **Bounded detection**: `detect` and `auth_check` run under `CC_REVIEW_DETECT_TIMEOUT` (15 s) with reason `detection timed out`. Helpful; add to spec.
- **Timeout backends**: perl fallback with process-group handling and busybox exit normalization. Helpful (FR-020 needs a bound on stock macOS).
- **Helper subcommand**: `discover-reviewers.sh helper <fn>` so helpers run under bash when the harness shell is zsh. Helpful.
- **Dependency probes**: jq 1.6 and yq 4.18 dialect checks with a named error. Helpful.

## Spec Evolution Candidates

Resolved on 2026-10-13 by spec evolution during verification (spec Changelog). Compliance after evolution: 65 of 65.

- FR-006b: name the `Positive observations:` text section as the realization of `positive_observations`.
- Edge case "severity map outside the scheme": describe discovery-time rejection.
- Assumption on `delimited` sufficing for the three CLIs is wrong for CodeRabbit (JSON lines); contracts/reviewer-frontmatter.md still shows the delimited CodeRabbit example.
- FR-004: state that the core passes changed files one per line to the substitution.

---

# Deep Review Report

**Gate Outcome: PASS** (0 Critical and 0 Important open after fix round 3)
**Rounds:** 3 fix rounds across three review passes (commits 280ba23, 71cbc66, 1b911ab)
**cc-review delegation:** not detected (no cc-review extension); the built-in six-perspective review ran.

## Review Passes

| Pass | Tree reviewed | Reviewers |
|------|---------------|-----------|
| 1 (initial) | implementation after checkpoint 2 | correctness, architecture, security, production, test quality agents; CodeRabbit; Codex failed (usage limit) |
| 2 (after round 1) | 280ba23 | correctness, security, production agents; CodeRabbit |
| 3 (verification) | 71cbc66 | correctness, architecture, security, production, test quality agents; CodeRabbit; Codex failed (usage limit); then a combined re-review agent and CodeRabbit on the round 3 diff |

Goal Alignment was skipped in every pass: no PR exists for the branch.

## Summary

| Severity | Found | Fixed | Remaining |
|----------|-------|-------|-----------|
| Critical | 3 | 3 | 0 |
| Important | 29 | 29 | 0 |
| Minor | 74 | 61 | 13 |

Important "Fixed" includes 1 finding closed by a documented design decision (see below).

Per-pass breakdown:

| Severity | Pass 1 found | Pass 2 found | Pass 3 found | Fixed | Remaining |
|----------|--------------|--------------|--------------|-------|-----------|
| Critical | 1 | 0 | 2 | 3 | 0 |
| Important | 9 | 5 | 15 | 28, plus 1 closed by a documented design decision | 0 |
| Minor | 37 | 7 | 30 | all but those listed under Remaining | 13 |
| Notable | 6 | 4 | 7 | n/a | captured |

Pass 3 counts are after deduplication (52 raw) and include the round 3 re-review (1 Important, 4 Minor including CodeRabbit). Pass 1 Important "template lists every bundled reviewer, so frontmatter `enabled` is dead for bundled names" was not changed: contracts/cli-and-config.md defines the order "template defaults > reviewer enabled frontmatter" and FR-018 requires the template to carry `reviewers.*` keys. The consequence for user or project overrides of a bundled name is now documented in docs/reviewer-plugins.md.

## Agent Table (pass 3)

| Agent | Found | Fixed | Remaining | Status |
|-------|-------|-------|-----------|--------|
| Correctness | 7 | 6 | 1 | completed |
| Architecture and Idioms | 11 | 6 | 3 (+2 Notable) | completed |
| Security | 5 | 2 | 2 (+1 Notable) | completed |
| Production Readiness | 14 | 11 | 2 (+1 Notable) | completed |
| Test Quality | 11 | 10 | 0 (+1 Notable) | completed |
| Goal Alignment | 0 | 0 | 0 | skipped (no PR) |
| CodeRabbit (external) | 4 | 4 | 0 | completed |
| Copilot (external) | 0 | 0 | 0 | skipped (CLI not installed) |
| Codex (external) | 0 | 0 | 0 | failed (usage limit) |
| Round 3 re-review | 6 | 4 | 0 (+2 Notable) | completed |
| Test Suite (regression) | 0 | 0 | 0 | passed every round |

Duplicates across agents were merged (counted once, under the first reporter). MVP: Production Readiness (14 findings).

## Findings Fixed

### Pass 1 (fix round 1, 280ba23)

- **Critical, production**: on macOS `/bin/bash` 3.2 the body directory path was mangled, so every reviewer was invalid. Fixed with `mktemp -d`.
- **Important, security**: predictable `$TMPDIR/cc-review-reviewers.<pid>` directory (symlink plant, deletion of victim files). Fixed with `mktemp -d` and scoped cleanup.
- **Important, security**: `references` and `parser` symlinks escaped the plugin directory. Fixed with physical containment checks.
- **Important, correctness**: `{files}` glob-expanded bracketed paths. Fixed with `set -f`.
- **Important, production**: no time bound on stock macOS. Fixed with the perl backend and a visible warning.
- **Important, production**: presence-only `yq` check made every reviewer "malformed" under Python yq. Fixed with a dialect probe.
- **Important, production**: tool stderr was parsed as findings. Fixed by separating stdout and stderr into files.
- **Important, production**: unbounded `detect`/`auth_check`. Fixed with a 15 s bound.
- **Important, test quality**: legacy keys lost cross-layer precedence. Fixed by migrating per layer, with tests.
- Minor fixes: discovery exit code checked, `MAIN_BRANCH` fallback, dedup honoring `dedup: isolated`, all-digit names, empty `display_name`, `${VAR}` not a placeholder, jq `--args` key arrays, yq `strenv` assignments, vacuous tests, `rg` dependency in tests, filter-mismatch exit code, body files under the test TMPDIR.

### Pass 2 (fix round 2, 71cbc66)

- **Important, correctness**: the Step 2 EXIT trap replaced the config cleanup trap. Chained in round 2; the trap was removed entirely in round 3.
- **Important, production**: the CodeRabbit reviewer declared a delimited format that the shipping CLI never prints, so every run yielded zero findings. Fixed with a directory-form reviewer and a jq parser for the JSON-lines output, with a fixture test.
- **Important, production**: yq 4.18/4.19 failed the probe. Fixed by passing `-` explicitly.
- **Important, production**: parsers ran under `bash` despite the executable-bit contract. Fixed by running them through their shebang.
- **Important, security**: a dash-prefixed symlinked directory bypassed containment (`dirname` treated it as an option). Fixed with parameter expansion.
- Minor fixes: locale-independent base-branch check, uppercase placeholder typos, busybox exit 143, final jq assembly failure, unsafe-invoke branch, newline basenames, perl process-group kill, dash/empty base branch, empty dotted config keys, perl test guarded to macOS. Three failing tests resolved: the newline test pattern also matched `ctx-only` (test fixed); the ordering assertion followed the new file-before-directory order within a group, which the contract leaves open (test fixed); the base-branch message assertion followed the broader new message (test fixed).

### Pass 3 (fix round 3, 1b911ab)

- **Critical, correctness and production**: review.md looped over `$(jq -c '.[]')`, which word-split each command reviewer's JSON, so no command reviewer was ever invoked. Fixed: one tool call per entry, selected by index.
- **Critical, production**: the EXIT trap deleted the body files as soon as the Step 2 block's shell exited, before Step 3 read them. Fixed: no trap; explicit removal at the end and at every early stop (review.md and init.md).
- **Important, correctness**: invalid entries sharing a name with a valid one were changed by name-keyed updates, so `--only` could dispatch an entry with no body. Fixed with `.status != "invalid"` filters and de-duplicated names.
- **Important, correctness**: init's merge let generated `reviewers.*` keys shadow a user's legacy keys. Fixed by migrating a copy first.
- **Important, correctness**: helpers sourced into a zsh harness shell broke `--only a,b` and `{files}`. Fixed with a `helper` subcommand that runs under bash.
- **Important, correctness**: goal-alignment needed `--pr` although main used the current branch's PR. Fixed with `PR_CONTEXT_NUMBER`.
- **Important, architecture**: the docs' json-format example needed field renaming that the json format never performs. Fixed with a correct json example plus a parser example.
- **Important, architecture**: gator was told to fill a `rationale` field that the prompt output contract lacks. Fixed: evidence goes into `failure_scenario`, stated as the stored rationale.
- **Important, security**: a changed file named `--pre=...`, or one path containing spaces, became tool options. Fixed: one path per line, dash-prefixed paths passed as `./-...`.
- **Important, production**: 120 s CodeRabbit bound was shorter than real runs (188 s measured). Raised to 540 s, below the 600 s per-call limit, with background execution when a bound exceeds the limit (round 3 re-review follow-up).
- **Important, production**: the perl backend orphaned the tool on a group kill or TERM. Fixed: perl leaves the caller's group and forwards TERM/INT/HUP.
- **Important, production and CodeRabbit**: the parser returned `[]` for empty, error or truncated streams (false clean). Fixed: exit non-zero without a `complete` event or with `error`/`action_required`.
- **Important, production**: all command reviewers ran in one block, beyond the harness call limit. Fixed: per-entry calls, run alongside the prompt subagents.
- **Important, test quality**: the perl process-group test was vacuous, tab and directory-name rejection were untested, and the parser's line extraction read numbers from the comment body. Fixed with grandchild and TERM tests, new name fixtures, header-only location parsing and a locations fixture (mutation-checked).
- Minor fixes: control-character names, CDPATH, guarded `shopt`, whole-string key validation, CodeRabbit `trivial`/`none`, Codex `codex login status` and P0-P3 map, failure reasons carry the last stderr line, unquoted git paths, `--only` on an invalid-only name names the reason, busybox/locale/mktemp/noexec/probe/restore tests, stale review.md references, profile comments, standalone guide, CLAUDE.md structure, discovery contract body-file and helper sections.

## Remaining Findings

No Critical or Important finding remains. Minor findings left open:

- **Minor, correctness**: the fallback warning names the layer processed so far, not the effective one (bundled valid, user invalid, project valid prints "falling back to the bundled version"). Cosmetic; deferred.
- **Minor, architecture**: callers derive the body directory from `body_file` instead of discovery reporting it (review.md and init.md duplicate the expression). Works; a `body_dir` field is a follow-up.
- **Minor, architecture**: `detect_command_reviewers` round-trips discovery JSON through the legacy colon format for init only. Works; cleanup deferred.
- **Minor, architecture**: contracts/reviewer-frontmatter.md and the spec Assumption still show CodeRabbit as `delimited`. Spec artifact; listed under Spec Evolution Candidates.
- **Minor, architecture**: shim argument lists are maintained in three places, `external_rationale` in the finding schema is unused, `parallel` is still a reserved name, and detect-tools.sh duplicates platform/test detection (pre-existing). Deferred cleanups.
- **Minor, security**: `%q` emits `$'...'` for non-ASCII names, which breaks if a plugin wraps `{files}` in single quotes. The docs now say not to quote `{files}`; no bundled reviewer uses it.
- **Minor, security**: discovery runs `detect`/`auth_check` for reviewers later disabled by config or `--no-external`. Plugin shell is trusted by the spec's model; captured as a Notable idea.
- **Minor, production**: a very large `{files}` list can exceed the Linux single-argument limit (E2BIG). No bundled reviewer uses `{files}`.
- **Minor, production**: Copilot's prompt asks it to run `git diff` without granting shell tools in `-p` mode. Copilot is disabled by default and not installed here, so this is unverified.
- **Minor, production**: four distinct frontmatter failures share the reason "frontmatter missing or malformed". Deferred.

## Notable Observations

Captured to brainstorm/idea-inbox.md: reviewer schema single source, goals report-section contract, command finding path validation, deterministic command output parsing, timeout process-group detach. Earlier passes' Notables (detect for disabled reviewers, positive observations as text, reserved list duplication) are covered by the entries above or by Spec Evolution Candidates.

## Post-Fix Spec Coverage

Fix round 3 removed code (the EXIT traps and the command-reviewer `for` loop). Each requirement those blocks served is still implemented: body-file cleanup by explicit removal (review.md Step 2 stops, Step 8; init.md Step 5), command invocation by per-entry calls (FR-020, FR-022), fix-loop reuse of the ready sets (FR-024). All 39 functional requirements verified after the fix loop.

## Test Suite Results

| Round | Command | bash 5.3 | /bin/bash 3.2 | Status |
|-------|---------|----------|---------------|--------|
| 1 | make test | 254 passed | 254 passed | passed |
| 2 | make test | 279 passed | 279 passed | passed |
| 3 | make test | 309 passed | 308 passed | passed |

The bash 3.2 run skips one assertion that needs bash 5.2's `patsub_replacement`. `make validate` passed for the marketplace and plugin manifests after every round.

## Layer Comparison

The pipeline state holds no checkpoint finding counts, so no layer comparison is shown.
