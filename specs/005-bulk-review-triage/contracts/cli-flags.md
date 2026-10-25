# Contract: CLI Flags for Bulk Mode

Applies to `review` and `triage` (all harness shims pass these through verbatim).

| Flag | Commands | Value | Meaning |
|---|---|---|---|
| `--bulk` | review, triage | none | Switch to bulk mode |
| `--all-open` | review | none | Selector: all open non-draft PRs |
| `--search <query>` | review, triage | GitHub search query | Selector: query within current repo, open PRs |
| `--limit <n>` | review, triage | positive integer, default 10 | Cap on processed PRs |
| `--unattended` | review, triage | none | No prompts; fixed policy |
| `--resume [<run-id>]` | review, triage | optional run id | Continue an unfinished run; implies `--bulk`. The next argument is taken as the run id only if it matches `^[0-9]{8}-[0-9]{6}-(review\|triage)(-[0-9]+)?$`. With no unfinished run: `--unattended` starts a new run using the other flags; deferred prints `No unfinished <command> run to resume.` and stops. |

## Validation (all errors stop before any PR is touched)

| Condition | Error text (prefix `Error:`) |
|---|---|
| `--bulk` with `--pr` | `--bulk and --pr cannot be combined; --pr names a single PR` |
| `--all-open` with `--search` | `--all-open and --search are mutually exclusive` |
| `--all-open` on triage | `--all-open is not supported by triage; bulk triage always selects your own PRs` |
| `--limit` not a positive integer | `--limit must be a positive integer, got '<v>'` |
| `--search` with `repo:`, `org:`, `user:`, `is:closed`, `is:merged`, `state:` | `--search may not contain '<qualifier>'; bulk mode always uses open PRs of the current repository` |
| `--spec` (bulk review and bulk triage) or `--output` (bulk review) | `--<flag> is not supported with --bulk` |
| bulk flags (`--all-open`, `--search`, `--limit`, `--unattended`) without `--bulk`/`--resume` | `--<flag> requires --bulk` |
| `--resume` with selector/per-PR flags while an unfinished run exists | `--resume continues run <id> with its recorded options; remove <flags>` |
| `--resume --unattended` on a deferred run, or `--resume` without `--unattended` on an unattended run (non-interactive context) | `run <id> was started in <mode> mode` |
| `--resume <id>` unknown | `no unfinished <command> run '<id>'; unfinished runs: <ids or "none">` |

## Pass-through flag table (FR-002)

See spec FR-002. Summary: `--config`, `--profile` apply to every PR in both commands. Reviewer selection, `--no-meta-review`, `--max-rounds`, `--hints`, `--sequential`, `--parallel` apply to every PR in review. `--no-fix` removes the "apply fixes" action. `--idea-inbox` (triage) is offered once after the decision step. `--no-coverage-fix` is accepted with no effect. Config `interactive: false` means `--unattended`.

## Reserved reviewer names

`bulk`, `all-open`, `search`, `limit`, `unattended`, `resume` are added to `CC_REVIEW_RESERVED_NAMES` (`discover-reviewers.sh`) and to `reviewer.schema.json`.
