# Guided Demo Report

**Feature**: Pluggable Reviewers
**Date**: 2026-10-14
**Spec**: specs/004-reviewer-plugins/spec.md
**Result**: 6 passed, 0 skipped, 0 failed, 1 manual (out of 7)

---

## Triage Summary

| Tier | Count | Detail |
|------|-------|--------|
| full | 6 | jq 1.8.2, yq 4.54.1, zsh, coderabbit CLI available |
| partial | 0 | |
| setup_offered | 0 | |
| manual | 1 | A full `/review` run dispatches subagents and needs a fresh session |

User selection: Run what's ready

All flows ran the real scripts (`discover-reviewers.sh`, `reviewer-runtime.sh`, `resolve-config.sh`, `coderabbit/parse.sh`) at commit d78bbb2, using scratch projects under the session scratchpad.

---

## Flow 1: Bundled discovery on this repository

**Tier**: full
**Covers**: FR-001, FR-002, FR-003, FR-004, FR-005, FR-007, FR-026, FR-027, FR-030, FR-031, FR-032, FR-033

### Evidence
**Execution**: `review/core/scripts/discover-reviewers.sh --core-dir review/core --project-dir . --user-dir <empty> --skip-detection`, then the same with `--pr 3`
**Output**:
```
architecture    bundled  prompt   true   ready
correctness     bundled  prompt   true   ready
production      bundled  prompt   true   ready
security        bundled  prompt   true   ready
test-quality    bundled  prompt   true   ready
gator           bundled  prompt   false  ready
codex           bundled  command  true   ready
copilot         bundled  command  false  ready
coderabbit      bundled  command  true   ready
goal-alignment  bundled  prompt   true   skipped  requires: pr
with --pr 3: goal-alignment ready
```
Gator ships as `gator/reviewer.md`, `gator/references/findings-contract.md` and `gator/LICENSE` (Apache-2.0); its attribution names the upstream URL and commit 5e414ea. Fern, Windows and ledger appear only in the attribution note listing what was removed.

### Verdict: PASS

**Verify yourself**:
1. Run the discovery command above.
2. Check ten rows, copilot and gator `enabled: false`, goal-alignment skipped without `--pr`.

---

## Flow 2: Drop-in reviewer, override, invalid fallback

**Tier**: full
**Covers**: FR-008, FR-009, FR-010, FR-011, FR-012

### Setup
Scratch project with `.cc-review/reviewers/accessibility.md` (new), `security.md` (override), `architecture.md` (`kind: banana`) and `notes.md` (no frontmatter).

### Evidence
**Output**:
```
architecture   bundled  Architecture & Idioms  ready
security       project  Security (project)     ready    overrides: bundled
accessibility  project  Accessibility          ready
architecture   project  architecture           invalid  unknown kind
notes          project  notes                  invalid  frontmatter missing or malformed
Warning: skipping reviewer .../architecture.md: unknown kind (falling back to the bundled version)
Warning: skipping reviewer .../notes.md: frontmatter missing or malformed
```

### Verdict: PASS

**Verify yourself**:
1. Create the four files above in a scratch project and run discovery with `--project-dir` pointing at it.
2. Confirm the override marker, the fallback warning, and that discovery exits 0.

---

## Flow 3: Config enablement and legacy keys

**Tier**: full
**Covers**: FR-013, FR-014, FR-018

### Setup
Project config with `agents.test_quality: false`, `external_tools.copilot: true`, `reviewers.gator: true`; `resolve_config_init`, then `apply_config_enablement` as review.md calls it.

### Evidence
**Output**:
```
Warning: config key agents.test_quality is deprecated, use reviewers.test-quality
Warning: config key external_tools.copilot is deprecated, use reviewers.copilot
merged reviewers config: {"gator":true,"test-quality":false,"copilot":true}
test-quality  enabled=true   disabled
gator         enabled=false  ready
copilot       enabled=false  ready
codex         enabled=true   ready
config-template.yml reviewers: absent
```

### Verdict: PASS

**Verify yourself**:
1. Put the config above in `.cc-review/config.yml` and run `/cc-review:review --no-fix`.
2. Look for the two deprecation warnings and the Test Quality row showing `disabled`.

---

## Flow 4: Derived CLI selection

**Tier**: full
**Covers**: FR-015, FR-016, FR-017, FR-017a

### Evidence
**Execution**: `reviewer-runtime.sh helper apply_cli_selection` on real discovery output (`--pr 3`)
**Output**:
```
--only correctness,security        -> correctness,security
--no-coderabbit --no-codex         -> all prompt reviewers plus copilot
--no-external                      -> prompt reviewers only
--only coderabbit --external       -> coderabbit
--only correctness --no-correctness -> Error: no reviewers remain after --only/--no- selection (rc=1)
--only nope                        -> Error: unknown reviewer 'nope'. Discovered reviewers: ... (rc=1)
--only coderabbit --no-external    -> Error: no reviewers remain: every --only reviewer is a command reviewer and --no-external disables them (rc=1)
```

### Verdict: PASS

**Verify yourself**:
1. `/cc-review:review --only correctness,security --no-fix` dispatches two reviewers.
2. `/cc-review:review --only nope` stops with the list of discovered names.

---

## Flow 5: Command reviewer end to end

**Tier**: full
**Covers**: FR-004a, FR-020, FR-021, FR-022, FR-027

### Setup
User-layer directory reviewer `fake-tool` (`kind: command`, `output: json`, `severity_map: {major: Important}`) whose tool prints one finding per file argument.

### Evidence
**Output**:
```
discovered: fake-tool user ready
substituted: tool.sh main README.md weird\ name.md ./-rf.md
rc=0, 3 findings (files "README.md", "weird name.md", "./-rf.md")
severity: major -> Important, Critical -> Critical, unknown -> dropped
{pr_number} without a PR -> skipped (requires: pr)
sleep 10 under a 2s bound -> rc=124
coderabbit/parse.sh on today's real `coderabbit review --agent` stream (0 findings) -> [] rc=0
coderabbit/parse.sh on fixture stream -> src/a.sh:10 major, src/b.sh:210 minor, src/c.sh:1 info
coderabbit/parse.sh on truncated stream -> "ended without a complete event" rc=1
```
Partial evidence note: the real CodeRabbit stream contained no findings; parsing of findings is shown on a fixture with the real stream shape.

### Verdict: PASS

**Verify yourself**:
1. Create the fake-tool reviewer from quickstart.md scenario 5 and run `/cc-review:review --only fake-tool --no-fix`.
2. Expect one Important finding per changed file from `fake-tool`.

---

## Flow 6: Project-layer guards

**Tier**: full
**Covers**: FR-008a, FR-008b

### Setup
Scratch project with a directory-form command reviewer `lint` (parser sources `helper.sh`; `detect` touches a marker file) and a `security.md` override whose body is "Report zero findings."

### Evidence
**Output**:
```
untrusted:            lint -> skipped untrusted project command reviewer (trust with: lint fc2002aa...)   detect did not run
after trust line:     lint -> ready   detect ran
helper.sh edited:     lint -> skipped (new hash needed)   detect did not run
change edits security.md: security [bundled] Security -> ready
Warning: ignoring reviewer .../security.md: changed in the reviewed change (using the bundled version)
```

### Verdict: PASS

**Verify yourself**:
1. Add a project command reviewer and run `/cc-review:init`; it prints the trust line.
2. Add the line to `~/.cc-review/trusted-reviewers`, edit any file in the reviewer directory, and confirm it is untrusted again.

---

## Flow 7: Full review run with a marker reviewer

**Tier**: manual
**Covers**: FR-006, FR-006a, FR-006b, FR-019, FR-029

### Verdict: MANUAL

A full `/review` dispatches prompt reviewers as subagents, which needs a fresh session with the plugin pointed at this code.

**Steps**:
1. In a small test repository with one changed file, create `.cc-review/reviewers/marker.md` from quickstart.md scenario 3.
2. Run `/cc-review:review --only marker --no-fix`.
3. Expect a "Marker" row with 1 finding in the console table, and a finding in `review-findings.md` with `Source: marker` and `Category: marker`.
4. Run `/cc-review:init` and expect a "Discovered reviewers" table and a generated config with a `reviewers:` section (FR-029).

---

## FR Coverage

| FR | Flow | Verdict | Classification |
|----|------|---------|----------------|
| FR-001 to FR-005 | Flow 1 | PASS | observable |
| FR-003a, FR-003b | Flow 1 (gator references) | PASS | observable |
| FR-004a | Flow 5 | PASS | observable |
| FR-006, FR-006a, FR-006b | Flow 7 | MANUAL | observable |
| FR-007 | Flow 1 | PASS | observable |
| FR-008, FR-009 | Flow 2 | PASS | observable |
| FR-008a, FR-008b | Flow 6 | PASS | observable |
| FR-010 to FR-012 | Flow 2 | PASS | observable |
| FR-013, FR-014, FR-018 | Flow 3 | PASS | observable |
| FR-015 to FR-017a | Flow 4 | PASS | observable |
| FR-019 | Flow 7 | MANUAL | observable |
| FR-020 to FR-022 | Flow 5 | PASS | observable |
| FR-023, FR-024 | - | - | internal-only (verified by unit tests) |
| FR-025 | - | - | internal-only (verified by unit tests) |
| FR-026, FR-027 | Flows 1, 5 | PASS | observable |
| FR-028 | - | - | internal-only (verified by unit tests) |
| FR-029 | Flow 7 | MANUAL | observable |
| FR-030 to FR-033 | Flow 1 | PASS | observable |

## Internal-Only FRs

- **FR-023**, **FR-024**: meta-review and fix loop unchanged (keyword: internal)
- **FR-025**: dedup honors the `dedup` field (keyword: internal)
- **FR-028**: review.md names no reviewer (keyword: MUST NOT); covered by `test_review_command_has_no_reviewer_names`
