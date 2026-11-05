# CLI reference

<!-- Sources:
cc-review:README.md:163-189
cc-review:README.md:213-221
cc-review:README.md:90-98
cc-review:README.md:108-121
cc-review:review/config/profiles/quick.yml:1-25
cc-review:review/config/profiles/thorough.yml:1-26
cc-review:review/config/profiles/ci.yml:1-30
-->

Every flag for the four cc-review commands, and what each bundled profile sets. The tables reproduce the flag descriptions from the project README at the pinned version. For how to use these commands, see [Review your changes](../using/review.md), [Triage pull request comments](../using/triage.md), and [Inbox and issue assessment](../using/inbox-and-issue.md).

## review

Flags for the `/cc-review:review` command.

| Flag | Description |
|------|-------------|
| `--pr <number>` | Review a specific PR's diff |
| `--full` | Force full PR scope, including already-reviewed bulk candidates; retains draft/filter exclusions |
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
| `--bulk` | Review several PRs in one run |
| `--all-open` | Bulk: select every open PR |
| `--search <query>` | Bulk: select the open PRs matching a GitHub search |
| `--limit <n>` | Bulk: at most this many PRs (default: 10) |
| `--unattended` | Bulk: no questions, apply the fixed policy |
| `--resume [<run-id>]` | Bulk: continue an unfinished run |

> [!NOTE]
> With `--pr` on a branch other than the PR's own, the PR is checked out into a separate worktree under `.cc-review/pr-worktrees/` and reviewed there, so your working tree stays as it is.

## triage

Flags for the `/cc-review:triage` command.

| Flag | Description |
|------|-------------|
| `--pr <number>` | Target PR number |
| `--spec <path>` | Specification file for context |
| `--no-coverage-fix` | Skip automatic coverage remediation |
| `--idea-inbox <path>` | File for capturing out-of-scope ideas |
| `--bulk`, `--search`, `--limit`, `--unattended`, `--resume` | Triage several of your PRs in one run |

## inbox

Options for the `inbox` command.

| Option | Behavior |
|--------|----------|
| `--repo owner/name` | Select a repository explicitly, including outside a checkout. Default follows the invoking `gh` repository context. |
| `--type pr,issue,discussion` | Select any combination; repeat to combine selections. Default: all three types. |
| `--limit N` | Select the most recently updated items per type, from 1 to 100. Default: 10 per type. |
| `--since YYYY-MM-DD` | Filter every selected type by its last update. |
| `--help` | Show collector options without contacting GitHub. |

By default, PRs and issues are open, including draft PRs, with no recency cutoff. Discussions cover the last 90 days of activity, including answered and closed conversations. An explicit `--since` replaces that window and applies to all selected types.

## issue

Arguments and options for the `issue` command. The command takes an issue target as a number or a full issue URL.

| Argument or option | Behavior |
|--------------------|----------|
| `<number>` | Issue number to assess (for example `issue 42`) |
| `<url>` | Full issue URL to assess |
| `--repo owner/name` | Assess the issue in an explicitly named repository |
| `--help` | Show the command options |

> [!NOTE]
> Issue assessment works on GitHub.com only, requires an explicit issue target, and rejects pull requests.

## Profiles

Three bundled profiles preset which reviewers run and how strict the gate is. Select one with `--profile <name>`. The tables below show exactly what each profile file sets; a setting a profile does not list keeps the base configuration default.

### Reviewers each profile enables

| Reviewer | `quick` | `thorough` | `ci` |
|----------|---------|------------|------|
| correctness | yes | yes | yes |
| architecture | no | yes | yes |
| security | yes | yes | yes |
| production | no | yes | yes |
| test-quality | no | yes | yes |
| goal-alignment | no | yes | yes |
| coderabbit | no | yes | yes |
| copilot | no | yes | yes |
| codex | no | yes | yes |
| greptile | no | yes | no |
| gator | no | no | no |

> [!NOTE]
> The `quick` profile also leaves user and project reviewers at their own enabled default; use `--only` for a strict allowlist. The `ci` profile disables greptile because it spends Greptile credits on every run.

### Thresholds, output, and fix loop

| Setting | `quick` | `thorough` | `ci` |
|---------|---------|------------|------|
| `severity.min_confidence` | 70 | 80 | 70 |
| `severity.request_changes_severities` | Critical | Critical, Important, Minor | Critical, Important |
| `severity.auto_fix` | true | true | true |
| `output.verbosity` | quiet | normal | verbose |
| `max_fix_rounds` | 1 | 5 | 3 |
| `pr_posting.enabled` | not set | not set | false |
| `interactive` | not set | not set | false |

> [!NOTE]
> These flags and profiles were verified against cc-review <!-- guide:attr cc-review-version -->1.4.0<!-- /guide:attr -->.
