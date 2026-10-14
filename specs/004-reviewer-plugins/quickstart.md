# Quickstart: Pluggable Reviewers

Validation scenarios that prove the feature end to end. Automated checks live in `tests/run.sh`; the rest are manual review runs.

## Prerequisites

- `jq`, `yq` (v4) on PATH
- cc-review core resolvable (plugin install or `.cc-review/core`)
- A git repository with at least one changed file against `main`

## 1. Automated tests

```bash
make test
```

Expected: all assertions pass. Covers discovery (valid file and directory forms, invalid frontmatter, name mismatch, reserved name, missing reference, same-layer duplicate, cross-layer override, invalid-overrides-valid fallback, precondition tokens, `{pr_number}` without PR, command detect/auth skip), severity mapping, `--only`/`--no-` set arithmetic, legacy config key mapping with warnings, and hyphenated key resolution.

## 2. Discovery on this repository

```bash
review/core/scripts/discover-reviewers.sh --core-dir review/core --project-dir . --skip-detection | jq -r '.[] | "\(.name)\t\(.layer)\t\(.kind)\t\(.status)\t\(.reason // "")"'
```

Expected: ten rows. Six bundled prompt reviewers, `goal-alignment` skipped with `requires: pr`, three bundled command reviewers `ready` (detection skipped), `gator` ready with `enabled: false`.

## 3. Drop-in prompt reviewer (US1)

```bash
mkdir -p .cc-review/reviewers
cat > .cc-review/reviewers/marker.md <<'EOF'
---
name: marker
display_name: "Marker"
kind: prompt
category: marker
---
You are the MARKER REVIEW AGENT. Report exactly one Minor finding on the first
changed file, line 1, with summary "MARKER-FINDING present" and confidence 90.
Report nothing else.
EOF
```

Run `/review --no-fix`. Expected: console table has a "Marker" row with 1 finding; `review-findings.md` contains a finding with `Source: marker` and `Category: marker`. Remove the file afterwards.

## 4. Built-in parity and legacy config (US2)

Create `.cc-review/config.yml` with:

```yaml
agents:
  test_quality: false
```

Run `/review --no-fix`. Expected: a deprecation warning naming `reviewers.test-quality`; Test Quality row shows `disabled`; the other five prompt reviewers run. Then replace with `reviewers: {test-quality: false}` and confirm no warning.

## 5. Command reviewer (US3)

```bash
mkdir -p .cc-review/reviewers/fake-tool
cat > .cc-review/reviewers/fake-tool/reviewer.md <<'EOF'
---
name: fake-tool
kind: command
category: external
detect: "true"
invoke: "sh {files}"
timeout_seconds: 5
severity_map: {major: Important}
output:
  format: json
---
EOF
```

Point `invoke` at a tiny script that prints `[{"file":"README.md","line":1,"severity":"major","description":"fake","rationale":"test"}]`. Commit the reviewer first (a reviewer the change under review adds is ignored for that run) and run `/review --no-fix` on a later change. Expected: `fake-tool` is `skipped (untrusted project command reviewer (trust with: fake-tool <sha256>))`. Add that `fake-tool <sha256>` line to `~/.cc-review/trusted-reviewers`, run `/review --only fake-tool --no-fix` again, and expect one Important finding from `fake-tool`. Change `detect` to `false`, add the new trust line the review prints, and confirm the row shows `skipped (not available)`.

## 6. Gator (US4)

```yaml
reviewers:
  gator: true
```

Run `/review --only gator --no-fix` on a branch containing an obvious reachable bug (for example an off-by-one in a loop bound). Expected: a gator finding with severity Critical or Important whose rationale names the invariant, entry point, base versus head behavior, impact, and a reproducer in the failure scenario. Confirm `review/core/reviewers/gator/reviewer.md` has no "OpenShell", "Fern", "Windows", or "ledger" mentions outside the attribution block.

## 7. Layer override (US5)

Copy `review/core/reviewers/security.md` to `.cc-review/reviewers/security.md` and change `display_name` to "Security (project)". Run `/review --only security --no-fix`. Expected: console shows "Security (project)" and notes the override; only one security reviewer runs.

## 8. Derived flags (US6)

- `/review --only correctness,security --no-fix`: only two rows completed.
- `/review --only correctness --no-correctness`: error "no reviewers remain".
- `/review --only nope`: error listing discovered names.
- `/review --no-external --no-fix`: coderabbit, copilot, codex rows `disabled`.

## 9. Init

Run `/cc-review:init`. Expected: a "Discovered reviewers" table listing all ten bundled reviewers plus any project ones, and a generated config whose `reviewers:` section uses hyphenated names and no `agents:` / `external_tools:` keys.

## 10. Harness neutrality

```bash
rg -n "ReportFindings|Agent tool" review/core/reviewers/
```

Expected: no matches. And:

```bash
rg -n "correctness\.md|coderabbit review|copilot -s|codex review|goal-alignment" review/core/commands/review.md
```

Expected: no matches (the command refers to reviewers only through discovery output).

## Validation log

### 2026-10-13

- Scenario 1 (`make test`): 187 passed, 0 failed.
- Scenario 2 (discovery on this repository, `--skip-detection`): ten rows as expected. Six bundled prompt reviewers plus `gator` (`ready`, `enabled: false`), `goal-alignment` `skipped` with `requires: pr`, three bundled command reviewers `ready` (detection skipped).
- Scenario 10 (harness neutrality): `rg -n "ReportFindings|Agent tool" review/core/reviewers/` returns no matches; `rg -n "correctness\.md|coderabbit review|copilot -s|codex review|goal-alignment" review/core/commands/review.md` returns no matches.
- Performance (plan.md goal: under one second for up to 30 reviewers): `discover-reviewers.sh --core-dir review/core --project-dir <dir with 22 fixture reviewers> --skip-detection` over the 10 bundled plus 22 project reviewers (32 total) took 0.28 to 0.59 seconds wall clock over three runs (macOS, `/usr/bin/time -p`), after batching the per-layer awk, yq, and jq calls.
- `make validate`: both plugin manifests pass (marketplace entry bumped to 1.2.0 together with the plugin manifests).
- `bash -n` passes for `discover-reviewers.sh`, `resolve-config.sh`, `detect-tools.sh`, and `tests/run.sh`; `shellcheck` is not installed on this machine, so that check was skipped.
- Scenarios 3 to 9 (live `/review` and `/cc-review:init` runs) are manual and were not executed in the pipeline; the discovery-level behavior behind each (marker reviewer, legacy key mapping, command reviewer json fixture, gator metadata, project `security.md` override, `--only`/`--no-` combinations, init table inputs) is covered by `tests/run.sh`.
