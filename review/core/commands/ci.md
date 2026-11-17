# Manage cc-review CI

Resolve `CC_REVIEW_CORE_DIR` as the shim describes. This command manages the
invoking target repository; it does not enable CI in cc-review's source checkout
unless that is the user's selected target. Pass arguments as individual quoted
words, never eval generated shell. Use `ci.py --help` for helper syntax.

## Inputs

`ci setup|status|update|disable|doctor [--repo owner/name] [--ref COMMIT] [--remove]`

Infer the repository from authenticated `gh repo view --json nameWithOwner` when
not explicit. Require a matching local checkout before writing files. `setup`
is interactive configuration; CI item execution is always headless. Reuse any
preferences and authorization already supplied by the user.

## Setup

1. Inspect existing `.github/workflows/cc-review.yml` and `.cc-review/ci.yml`.
   Choose an immutable 40-character cc-review commit containing the CI workflow,
   preferably the latest released CI version; verify it with GitHub API. Never
   use a moving tag/main as the generated pin. The helper refuses unmanaged
   workflow replacement and preserves existing valid config.
2. Collect missing choices: provider/model, enabled triggers/commands, identity
   (named GitHub App recommended, GITHUB_TOKEN fallback), existing label mapping,
   resource limits. Explain the fixed policy in `commands/unattended.md`.
   Run `python3 <core>/scripts/ci.py setup --root <target> --ref <commit>`.
   Adjust generated JSON-compatible YAML with validated chosen settings. The
   source helper default config is `review/config/ci.yml`.
3. Provision provider credentials without displaying values: `gh secret set
   ANTHROPIC_API_KEY --repo <repo>` or `CLAUDE_CODE_OAUTH_TOKEN`; use stdin from
   the user or a private local file. Never put secrets in arguments, config,
   chat, commits or logs. Federation uses repository variables
   CC_REVIEW_FEDERATION_RULE_ID and CC_REVIEW_ANTHROPIC_ORGANIZATION_ID; optional
   service-account/workspace variables are supported. Gateway uses
   CC_REVIEW_ANTHROPIC_BASE_URL. Bedrock uses AWS_ACCESS_KEY_ID,
   AWS_SECRET_ACCESS_KEY, optional AWS_SESSION_TOKEN secrets and CC_REVIEW_AWS_REGION.
   Vertex uses GOOGLE_CREDENTIALS JSON secret, CC_REVIEW_GOOGLE_PROJECT and
   CC_REVIEW_GOOGLE_REGION. For cloud OIDC, use the documented custom caller
   pattern and establish credentials before the base-action model step.
4. For GITHUB_TOKEN keep bot_login `github-actions[bot]`. For App identity use
   `.cc-review/github-app-manifest.json`: set a unique App name and owner URL,
   submit its JSON as the `manifest` form field to GitHub's App registration
   page (`https://github.com/settings/apps/new` or the organization's settings).
   This requires the user's browser approval; never claim it happened silently.
   The manifest redirects with a one-use `code` to localhost:8765; have the user
   provide that code or receive it with a local callback. Exchange through
   `POST /app-manifests/{code}/conversions`. Capture output only into a private
   chmod-600 temporary file. Read App ID/slug from it, pipe its pem field directly
   to `gh secret set CC_REVIEW_APP_PRIVATE_KEY`, set repository variable
   CC_REVIEW_APP_ID, and set bot_login to `<slug>[bot]`. Delete private output
   immediately. Ask the user to complete GitHub's installation page and select
   the target repository, then continue setup. Never commit the private key.
5. Inspect existing labels. Preserve the repository's scheme using config label
   mappings. Create only missing configured labels via `gh label create` with
   neutral descriptions; never rename/delete unrelated labels.
6. Review/commit/push generated files within the user's authorized setup scope.
   Run `gh workflow run cc-review.yml --repo <repo>` after the workflow is on
   the default branch (or use an explicitly selected --ref for a test branch).
   Find the exact dispatched run, watch it with `gh run watch --exit-status`,
   inspect its summary and report pass/failure with a link. A successful empty
   sweep proves wiring only; dispatch an agreed existing item number + help to
   verify status publication, then a disposable PR/issue for a paid model smoke
   test when authorized. Never claim unexecuted smoke tests passed.

## Status

Run `ci.py status --root <target> --repo <repo>`. Present enabled triggers and
commands, identity, model/provider, immutable ref, recent run URLs/conclusions,
and attention items. Report the attention scan scope (latest 30 open items).
Read-only status never changes config or posts comments.

## Doctor

Run `ci.py doctor --root <target> --repo <repo>`. It validates config, consistent
pins, secret names (never values), provider variables, labels, recent runs and
remote plugin version. Explain every failure and the next action. Inspect caller
permissions: issues/pull-requests write, checks/actions read, contents write for
fixes, id-token write for federation; repository/org policy may restrict these.
For an App, verify installation access with a freshly minted installation token
(scoped to this repository and required permissions) in CC_REVIEW_APP_TOKEN, then
run doctor again. Minting must request exactly the permissions the workflow uses;
a token mint failure identifies missing installation/grants. Check the latest
workflow's App-token step and test dispatch, rather than inventing effective
permissions from a username. Delete local token/key material afterwards.

## Update

Resolve a new immutable integration commit. Run `ci.py update --root <target>
--ref <commit>`. The helper updates both pins while retaining caller additions
and config settings. Unsupported config schema stops with an explicit migration
message; do not reset user settings to defaults. Re-run doctor and an authorized
smoke dispatch after committing/pushing.

## Disable

`ci.py disable --root <target>` sets enabled false, preventing all events,
commands, dispatches and sweeps after commit/push. With explicit `--remove`,
remove only managed workflow/config/manifest files. Keep unrelated files, labels,
secrets and App installations; explain how the owner can revoke those separately.
Report pending/running workflow runs and offer cancellation only if requested.
