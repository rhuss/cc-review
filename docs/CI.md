# Unattended GitHub Actions

Use `cc-review:ci setup` in the repository you want to automate. It generates a
small caller workflow and `.cc-review/ci.yml`, helps configure provider secrets,
labels and identity, then dispatches a smoke test once the workflow is available
on GitHub. `status`, `doctor`, `update` and `disable` manage the installation.

The integration runs in your repository with your model account. There is no
hosted cc-review service or shared API key. The reusable entry point is
`rhuss/cc-review/.github/workflows/cc-review.yml@<commit>`; setup pins both that
reference and its `integration_ref` input to the same immutable commit. Choose a
commit containing the new CI files. The prepare/finalize helper is `ci/action.yml`.

## Events and commands

Default events are PR opened/synchronized, issue opened, new item comments, a
six-hour sweep and manual dispatch. Follow-up PR pushes select bot triage and
review. The independent switches in `triggers` and `commands` can disable each
path; `enabled: false` stops all of them. A manual dispatch with no number runs a
bounded sweep; a number plus operation targets one item. Fix is comment-only.

Supported whole-comment commands:

| Command | Target | Effect |
|---|---|---|
| `/cc-review review` | PR | COMMENT review at the observed head |
| `/cc-review triage` | PR | Reply to bot threads and resolve verified addressed concerns |
| `/cc-review assess` | Issue | Assessment reply and mapped triage labels |
| `/cc-review fix` | Same-repository PR | Propose file changes and push a child commit after policy checks |
| `/cc-review help` | Either | Show command help in the sticky status |

Current repository write, maintain or admin permission is required by default.
`command_permissions` may additionally allow read or triage permission for other
commands; fix always requires a writer. The runtime rechecks permission and the
original comment before publication. Commands are acknowledged with an eyes
reaction. Shell suffixes, quoted examples and multi-command comments do not run.

## Unattended policy

Reviews use COMMENT, never approval or request changes. Pending or failed checks
withhold review/fix publication. Triage touches bot reviewer threads only; human
threads appear under needs attention. Assessment never closes or assigns issues.
Fixes require a writer's explicit comment, an unchanged same-repository head and
successful existing checks. Changes are committed through the GitHub data API,
without executing project code; a non-force ref update rejects competing pushes.
Fix proposals are limited to existing regular, non-hidden files and bounded
content. Code tests are **not** executed by this entry point: reviewers must not
claim otherwise. A pushed fix runs the repository's ordinary CI; inspect those
checks before merging and request another fix or apply a manual change if they
fail. There is no automatic rollback or repeated fix loop.

Single-item core commands also accept `--unattended`: `review --pr 7
--unattended`, `triage --pr 7 --unattended`, and `issue 42 --unattended`. Review
and triage reuse the bulk fixed policy on an explicit one-item selector. Issue
assessment uses the guarded assessment publisher and your authenticated posting
identity. Interactive invocations retain their draft/approval flows.

The CI analysis is proposal-only. It receives bounded diff/conversation evidence,
the bundled review perspectives or need/fit guidance, bounded default-branch
project guidance, and the unattended policy. Fix evidence additionally contains
the current contents of up to 20 changed regular files.
It has no tools, GitHub token, question tool, shell, network or project execution.
The deterministic publisher checks the structured proposal before any mutation.
When supplied evidence is insufficient to verify a fix or thread, it requests
maintainer attention. This intentionally limits conclusions to collected evidence.

## Forks and configuration trust

The workflow checks out only the default branch configuration and the pinned
cc-review integration. It never checks out a PR head. Automatic fork events
publish guidance to request review from a writer. An authorized `/cc-review
review` reads fork diff data through the API; it cannot execute fork code. Fork
triage and fixes are refused. Events authored by the configured bot are ignored.

A single updated bot status comment records per-operation state and run links.
Only markers authored by the configured identity are trusted. Completion is
keyed to the review head, triage head/thread activity, or issue body/conversation.
Self-authored status/result updates do not invalidate their own evidence.
Publication markers recover a review/reply posted before a later step failed.
All entry points use the same per-item concurrency group. Active/current complete
operations are skipped by sweeps; abandoned running markers expire after the
configured timeout plus five minutes. GitHub Actions may coalesce pending jobs
in a concurrency group; later sweeps recover unfinished operations.

## Identity

`GITHUB_TOKEN` is the simplest setup. Keep `identity.bot_login:
github-actions[bot]`. The caller requests contents/issues/pull-requests write and
checks/actions read. Organization policy must permit these workflow permissions.
GITHUB_TOKEN writes generally do not trigger new workflows; use a GitHub App if
fix pushes must trigger ordinary CI.

A named GitHub App is recommended for a reusable bot identity across repositories.
Setup generates a manifest with scoped permissions. GitHub's browser registration
and installation approvals remain user steps. The one-time manifest code is
exchanged privately; only the App ID (repository variable CC_REVIEW_APP_ID) and
private key (CC_REVIEW_APP_PRIVATE_KEY secret) are retained. Set bot_login to the
App slug plus `[bot]`. The worker requests a repository-scoped installation token,
with contents read except during an authorized fix. Doctor can verify installation
access with a freshly minted token in CC_REVIEW_APP_TOKEN; request the workflow's
permissions during minting to verify the App grant. Never put keys/tokens in chat,
source or command arguments.

## Model providers

Set `model` to the provider's model identifier and `provider` to the selected path.
The generated caller passes the following names through to the pinned
[claude-code-action base action](https://github.com/anthropics/claude-code-action/tree/d5f7970ae232b6039636a16ea7f251e58e814f38/base-action).

| Provider | Secrets | Repository variables |
|---|---|---|
| `anthropic` | ANTHROPIC_API_KEY | — |
| `oauth` | CLAUDE_CODE_OAUTH_TOKEN | — |
| `federation` | — | CC_REVIEW_FEDERATION_RULE_ID, CC_REVIEW_ANTHROPIC_ORGANIZATION_ID; optional CC_REVIEW_ANTHROPIC_SERVICE_ACCOUNT_ID, CC_REVIEW_ANTHROPIC_WORKSPACE_ID |
| `gateway` | ANTHROPIC_API_KEY | CC_REVIEW_ANTHROPIC_BASE_URL |
| `bedrock` | AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, optional AWS_SESSION_TOKEN | CC_REVIEW_AWS_REGION |
| `vertex` | GOOGLE_CREDENTIALS (JSON) | CC_REVIEW_GOOGLE_PROJECT, CC_REVIEW_GOOGLE_REGION |

Federation requires id-token write, already declared in the caller. For cloud
OIDC instead of AWS/Google credential secrets, customize a copy of the reusable
workflow to establish cloud identity immediately before its model step. The
`ci/action.yml` prepare and finish phases remain usable around that step. Preserve
the no-PR-checkout, no-model-tools, no-GitHub-token and always-finalize boundaries.
Custom caller additions survive `ci update` when it bumps the two version pins.

Supply secrets with `gh secret set` using stdin or a private local file. Doctor
reads secret names only. Vertex credential files use mode 600 and are removed in
an always-run cleanup step. Provider values never enter item snapshots or prompts.

## Limits and failures

Defaults: 10 sweep items, 30 model turns, 15 model minutes per item and 100,000 diff
bytes. Config validation bounds these to 100 items, 100 turns, 60 minutes and
1,000,000 diff bytes. A sweep's processed-item limit is separate from the bounded
API scan. Oversized, missing-patch or truncated evidence is withheld. No prompt
or permission request can suspend an item: a missing/malformed structured outcome,
model timeout or denied operation becomes needs attention with a remedy. An API
outage that prevents status publication is visible as a failing workflow and step
summary; inspect the run and retry. Manual cancellation may leave a running marker
until its expiry.

Common remedies:

- Failed/pending checks: fix or wait for those checks, then rerun the command.
- Changed head/conversation: rerun against current evidence.
- Missing credentials, labels or permissions: run `cc-review:ci doctor` and follow
  its specific setting/secret/grant instructions.
- Human threads or insufficient current-code evidence: inspect and handle them
  as a maintainer.
- Fork event: have a writer post `/cc-review review`.
- Model/tool/result failure: inspect the linked run and retry; raise a bounded
  resource setting only when the item requires it.

Status/doctor show recent runs and attention markers from the latest 30 open
items. Disable sets enabled false; `disable --remove` removes only managed
workflow/config/manifest files. Labels, secrets and App installations remain for
the owner to revoke if desired.

## Validation

`python3 -B tests/test_ci.py` exercises routing, provenance, freshness, publisher
restrictions, replay and installation using offline fixtures. `make test` runs
the repository suite, `make validate` checks manifests, and actionlint checks the
reusable workflow and generated caller. Paid provider execution, browser App
registration and installation access require a real configured repository; the
setup smoke dispatch reports what it actually tested.
