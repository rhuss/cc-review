# Configuration and finding schema

<!-- Sources:
cc-review:README.md:272-286,325
cc-review:review/config/config-template.yml:1-89
cc-review:review/config/profiles/quick.yml:1
cc-review:review/config/profiles/thorough.yml:1
cc-review:review/config/profiles/ci.yml:1,12
cc-review:review/core/scripts/resolve-config.sh:43-76,132-165,190-222,237-253,256-332
cc-review:review/core/commands/review.md:4,80-88,113-122,145-151,376-385,799-804,820-837,942-946,980,809,1012-1013,1023,1032,1525-1528,1772-1778
cc-review:review/core/commands/bulk.md:112
cc-review:review/core/commands/triage.md:449,492,980-981
cc-review:review/core/reviewers/correctness.md:2-4
cc-review:review/core/reviewers/architecture.md:2-4
cc-review:review/core/reviewers/security.md:2-4
cc-review:review/core/reviewers/production.md:2-4
cc-review:review/core/reviewers/test-quality.md:2-4
cc-review:review/core/reviewers/goal-alignment.md:2-4
cc-review:review/core/reviewers/coderabbit/reviewer.md:2-6
cc-review:review/core/reviewers/copilot.md:2-6
cc-review:review/core/reviewers/codex.md:2-6
cc-review:review/core/reviewers/greptile/reviewer.md:2-6
cc-review:review/core/reviewers/gator/reviewer.md:2-6
cc-review:review/core/schemas/finding.schema.json:40-50,95-122
cc-review:review/core/agents/preamble.md:46-47
cc-review:review/core/schemas/reviewer.schema.json:3-4,29-33,40-48
-->

This page lists the cc-review configuration keys, the order in which configuration layers resolve into one effective configuration, and the fields of a finding. For the command flags that can override these settings, see the [CLI reference](cli.md).

## Configuration file

cc-review reads YAML configuration from a project file at `.cc-review/config.yml` (which takes precedence) or a user file at `~/.cc-review/config.yml`. Each is copied from `review/config/config-template.yml`, and that same template is the built-in defaults layer of the merge.

The template sets these keys:

```yaml
severity:
  min_confidence: 70
  request_changes_severities:
    - Critical
    - Important
  auto_fix: true

pr_posting:
  enabled: true
  auto_detect_pr: false
  max_inline_comments: 50
  voice_profile: "reviewer"
  recovery_dir: ".cc-review"
  ignore_authors: []

output:
  dir: "."
  verbosity: "normal"
  findings_filename: "review-findings.md"

test:
  command: ""
  timeout_seconds: 300

triage:
  bot_profiles:
    - login: "coderabbitai[bot]"
      self_resolves: true
      auto_resolve: false
    - login: "copilot[bot]"
      self_resolves: false
      auto_resolve: true
    - login: "devin-ai-integration[bot]"
      self_resolves: false
      auto_resolve: true
    - login: "greptile-apps[bot]"
      self_resolves: false
      auto_resolve: true
  codecov:
    patch_threshold: 80
    auto_remediate: true

meta_review:
  enabled: true
  min_findings: 5

interactive: true

max_fix_rounds: 3
```

Its comment block documents two more maps that it does not set, `reviewers` and `allow_untrusted_checkout`, and gives an example for `pr_posting.ignore_authors`. The examples, as they appear in the template's comments:

```yaml
# reviewers:
#   test-quality: false
#   gator: true
#   accessibility: true     # a project or user reviewer
#
# allow_untrusted_checkout:
#   codex: true
#
# pr_posting:
#   ignore_authors:
#     - k8s-ci-robot
#     - openshift-ci-robot
```

After the merge, cc-review checks the value types. An invalid `severity.auto_fix`, `pr_posting.enabled`, `pr_posting.auto_detect_pr`, `severity.min_confidence` (an integer from 0 to 100), `max_fix_rounds`, `pr_posting.max_inline_comments`, or `test.timeout_seconds` (each a positive integer) falls back to the template value with a warning. An invalid `output.verbosity` falls back to `normal`.

### Top-level keys

| Key | Shape | In the template | Purpose |
|-----|-------|-----------------|---------|
| `reviewers` | map of booleans | not set; documented in its comments | One key per discovered reviewer. A reviewer without a key uses its own default. |
| `allow_untrusted_checkout` | map of booleans | not set; documented in its comments | Lets a command reviewer run in the checkout of a pull request from a fork. |
| `severity` | map | set | Confidence threshold, gate severities, and automatic fixing. |
| `pr_posting` | map | set | How reviews and replies are posted to a pull request. |
| `output` | map | set | Where the findings report is written and how much progress is shown. |
| `test` | map | set | The test command the fix loop runs, and `test.timeout_seconds`. |
| `triage` | map | set | Bot handling and Codecov thresholds for triage. |
| `meta_review` | map | set | Whether the meta-review runs and from how many findings. |
| `interactive` | boolean | `true` | Whether cc-review asks before acting. |
| `max_fix_rounds` | integer | `3` | Maximum fix loop rounds. |

### reviewers

The template sets no `reviewers` key; its comments document the map. Reviewers are plugins discovered from `.cc-review/reviewers/` (project), `~/.cc-review/reviewers/` (user), and the bundled `core/reviewers/` directory. `reviewers.<name>: true` enables a discovered reviewer and `false` disables it. A reviewer without a key uses the `enabled` value from its own frontmatter, which defaults to `true` when the frontmatter omits it. A value that is not a boolean is removed with a warning, so the reviewer's default applies.

The bundled defaults enable every reviewer except `copilot`, `gator`, and `greptile`:

| Reviewer | Kind | Frontmatter default |
|----------|------|---------------------|
| `correctness` | prompt | `true` (not set) |
| `architecture` | prompt | `true` (not set) |
| `security` | prompt | `true` (not set) |
| `production` | prompt | `true` (not set) |
| `test-quality` | prompt | `true` (not set) |
| `goal-alignment` | prompt | `true` (not set) |
| `coderabbit` | command | `true` |
| `copilot` | command | `false` |
| `codex` | command | `true` |
| `greptile` | command | `false` |
| `gator` | prompt | `false` |

> [!NOTE]
> The legacy keys `agents.<name>` and `external_tools.<name>` are deprecated. They keep working for the migrated reviewers (`agents.test_quality` maps to `reviewers.test-quality`) and print a one-line warning that points to the new key.

### allow_untrusted_checkout

The template sets no `allow_untrusted_checkout` key; its comments document the map. Command reviewers do not run in the checkout of a pull request from a fork (bulk review, or `--pr` for a pull request that is not the current branch), because the tool could load the pull request's own agent instruction files. They are reported as `skipped (untrusted checkout)`. `allow_untrusted_checkout.<name>: true` opts one reviewer in; the default is `false`. Prompt reviewers always run. A value that is not a boolean is removed with a warning, so the reviewer does not run in an untrusted checkout.

### severity

| Key | Template value | Notes |
|-----|----------------|-------|
| `severity.min_confidence` | `70` | Findings with a lower confidence are excluded from the report. |
| `severity.request_changes_severities` | `Critical`, `Important` | The severities the gate counts. The gate passes when no finding has one of them. |
| `severity.auto_fix` | `true` | With `false`, the review does not fix without the user's explicit choice. |

### pr_posting

| Key | Template value | Notes |
|-----|----------------|-------|
| `pr_posting.enabled` | `true` | |
| `pr_posting.auto_detect_pr` | `false` | With `true` and no `--pr`, the review uses the pull request of the current branch. |
| `pr_posting.max_inline_comments` | `50` | Limit for the number of accepted inline findings, checked before posting. |
| `pr_posting.voice_profile` | `"reviewer"` | |
| `pr_posting.recovery_dir` | `".cc-review"` | Directory for the recovery file written when posting fails. |
| `pr_posting.ignore_authors` | `[]` (none) | A list of logins treated like bots by the posting check, for CI accounts that are regular GitHub users (the template comment gives `k8s-ci-robot` and `openshift-ci-robot` as examples). Before a review, thread reply, or resolution is posted, cc-review withholds it when someone other than you commented on the PR since the analysis; bots and these logins do not count. |

### output

| Key | Template value | Notes |
|-----|----------------|-------|
| `output.dir` | `"."` | Directory the findings report is written to. |
| `output.verbosity` | `"normal"` | One of `quiet` (final summary and errors), `normal` (reviewer completion status and finding counts), or `verbose` (reviewer progress, timing, intermediate results, discovery notes, and debug info). |
| `output.findings_filename` | `"review-findings.md"` | File name of the findings report in `output.dir`. `--output <path>` replaces the whole path. |

### test

| Key | Template value | Notes |
|-----|----------------|-------|
| `test.command` | `""` (empty) | When empty, the review detects the command: `make test` for a Makefile with a `test:` target, `go test ./...` for `go.mod`, `npm test` for a `package.json` with a test script, `pytest` for `pyproject.toml` or `setup.py`. |
| `test.timeout_seconds` | `300` | |

### triage

| Key | Template value | Notes |
|-----|----------------|-------|
| `triage.bot_profiles` | four entries | The template lists `coderabbitai[bot]` (`self_resolves: true`, `auto_resolve: false`), `copilot[bot]`, `devin-ai-integration[bot]`, and `greptile-apps[bot]` (each `self_resolves: false`, `auto_resolve: true`). |
| `triage.codecov.patch_threshold` | `80` | |
| `triage.codecov.auto_remediate` | `true` | |

### meta_review, interactive, and max_fix_rounds

| Key | Template value | Notes |
|-----|----------------|-------|
| `meta_review.enabled` | `true` | `--no-meta-review` sets it to `false`. |
| `meta_review.min_findings` | `5` | With fewer findings, the meta-review is skipped. |
| `interactive` | `true` | With `false`, the review shows no next-steps menu and applies its defaults, and a bulk run is unattended. |
| `max_fix_rounds` | `3` | Maximum fix loop rounds. `--max-rounds` overrides it. |

## Resolution order

cc-review merges several configuration layers into one effective configuration. A higher layer overrides a lower one key by key. The order, from highest priority to lowest:

| Priority | Layer | Where it comes from |
|----------|-------|---------------------|
| 1 (highest) | CLI flags | Flags passed on the command line (see the [CLI reference](cli.md)). |
| 2 | `--config <path>` | An explicit configuration file. |
| 3 | `--profile <name>` | A bundled profile (`quick`, `thorough`, `ci`). |
| 4 | Project config | `.cc-review/config.yml` in the git root. |
| 5 | User config | `~/.cc-review/config.yml`. |
| 6 | Built-in defaults | `review/config/config-template.yml`. |
| 7 (lowest) | Reviewer default | The reviewer's own `enabled` value. |

> [!NOTE]
> The five file layers (built-in defaults, user config, project config, profile, and `--config` file) are assembled in `resolve-config.sh` and deep-merged from lowest to highest priority, so the explicit `--config` file wins among the files. Legacy `agents.*` and `external_tools.*` keys are migrated in each layer before the merge, so layer precedence applies to them as well.

## Finding schema

Every reviewer reports findings in a common structure, validated against `finding.schema.json`. The gate counts findings by `severity`. Findings with a `confidence` below `severity.min_confidence` are dropped after each reviewer completes, before the merge.

### Severity

A finding carries one severity, ordered `Critical > Important > Minor > Notable`.

| Severity | Rank |
|----------|------|
| `Critical` | highest |
| `Important` | |
| `Minor` | |
| `Notable` | lowest |

For how severity drives the pass or fix decision, see [Gate and fix](../how-it-works/gate-and-fix.md).

### Confidence

`confidence` is an integer from 0 to 100. The reviewer instructions ask for a confidence of at least 70, or at least 50 for `Critical` findings. After each reviewer completes, the review drops every finding below `severity.min_confidence` (70 in the template), with no exception for `Critical` findings.

### Resolution and round tracking

| Field | Values or type | Meaning |
|-------|----------------|---------|
| `resolution` | `pending`, `fixed`, `unresolved` | Current resolution status. |
| `round_found` | integer (minimum 1) | Fix loop round when the finding was discovered (1 is the initial review). |

### Meta-review fields

These fields are present only when the meta-review ran.

| Field | Values or type | Meaning |
|-------|----------------|---------|
| `verdict` | `confirmed`, `weak`, `false-positive` | The Skeptic's assessment of finding validity. |
| `verdict_reasoning` | string | The Skeptic's code-cited justification for non-confirmed verdicts. |
| `calibrated_severity` | `Critical`, `Important`, `Minor`, `Notable` | The Calibrator's adjusted severity (present only when changed). |
| `calibration_reasoning` | string | The Calibrator's justification for the severity adjustment. |

For how the two critics produce these, see [Meta-review](../how-it-works/meta-review.md).

## severity_map translation at merge

A reviewer plugin declares its metadata in frontmatter validated against `reviewer.schema.json`. When a command reviewer wraps an external tool whose severity vocabulary differs from cc-review's, the reviewer translates it with a `severity_map`.

`severity_map` is an object: each key is a native severity string, and each value is one of `Critical`, `Important`, `Minor`, or `Notable`. A native value not listed in the map passes through unchanged when it is already a cc-review severity; otherwise the finding is dropped with a warning.

> [!NOTE]
> These configuration keys and schema fields were verified against cc-review <!-- guide:attr cc-review-version -->1.9.2<!-- /guide:attr -->.
