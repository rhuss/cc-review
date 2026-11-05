# Trust and configuration

<!-- Sources:
cc-review:docs/reviewer-plugins.md:19-31
cc-review:review/core/scripts/discover-reviewers.sh:124-173
cc-review:review/core/scripts/discover-reviewers.sh:175-203
cc-review:review/core/scripts/discover-reviewers.sh:516-539
cc-review:review/core/scripts/discover-reviewers.sh:587-614
cc-review:review/core/scripts/discover-reviewers.sh:616-618
cc-review:review/core/commands/review.md:76
cc-review:review/core/commands/review.md:307-310
cc-review:review/core/commands/review.md:323
cc-review:review/core/commands/review.md:325-333
cc-review:review/core/commands/init.md:35
cc-review:review/core/commands/init.md:88-99
cc-review:review/config/config-template.yml:5-29
cc-review:README.md:268-307
-->

The project reviewer layer is read from the checkout being reviewed, so whoever authors a change also controls those files. Discovery applies a trust model so a change cannot steer or exploit its own review. Once you understand that model, the second half of this page covers how you turn reviewers on and off, in config and per run. For how reviewers themselves are written, see [Write a prompt reviewer](prompt-reviewer.md) and [Write a command reviewer](command-reviewer.md).

## The trust model

Three guards protect a review from the change under review.

**A reviewer the change edits does not judge it.** When a project reviewer's file is part of the change under review, discovery ignores that reviewer for this run. The guard covers the reviewer's `.md`, any file of its plugin directory, a reference it declares, and its parser. The bundled or user reviewer of the same name runs instead, and a reviewer the change adds is listed as `skipped (changed in the reviewed change)`. A new or edited project reviewer takes effect for every later change, once it is committed and is no longer part of a diff.

**Project command reviewers need your trust.** A `kind: command` reviewer in `.cc-review/reviewers/` runs shell commands (`detect`, `auth_check`, `invoke`, and its parser) with your credentials. cc-review runs none of them until you trust that reviewer by its sha256 hash in `~/.cc-review/trusted-reviewers`. Until then it shows as `skipped (untrusted project command reviewer (trust with: <name> <sha256>))`. The hash covers the reviewer file, or for a directory-form reviewer every file in its directory (its parser and any helper the parser sources), so any edit to those files needs a new trust line. A reviewer directory that holds a symlink is never trusted. The trust file is read only from your home directory, and a trust file placed inside the project under review is ignored with a warning, since the change could otherwise trust its own reviewers. Project prompt reviewers, and every reviewer in the user and bundled layers, need no trust.

**Command reviewers skip an untrusted fork checkout.** When the tree under review is a cross-repository (fork) pull request's code, cc-review marks it as an untrusted checkout. This happens for an isolated PR checkout and for a bulk worker reviewing a fork PR. Because an external tool run inside that checkout could load the PR's own agent instruction files (`AGENTS.md` and the tool's own instruction files in the repository), command reviewers do not run there by default. Each one that is still ready becomes `skipped (untrusted checkout)`. Prompt reviewers still run, and neither `--only` nor `--external` overrides the skip. Opt a single command reviewer back in with `allow_untrusted_checkout.<name>: true` in config.

## Trust a project command reviewer

A project command reviewer is skipped until you vouch for the exact version in the checkout. You do that by adding one line, the reviewer's name and its current sha256 hash, to your home trust file. cc-review generates that line for you so you never compute the hash by hand.

1. **List the trust line.** Run `/cc-review:init` (or any review). Discovery reports each untrusted project command reviewer together with the line that trusts its current version:

   ```text
   Untrusted project command reviewers run nothing until you trust them. To trust the current version, add these lines to ~/.cc-review/trusted-reviewers:
   lint-service 3f1c...e9a0
   ```

2. **Add the line to your trust file.** Copy each `<name> <sha256>` line into `~/.cc-review/trusted-reviewers`, one per line. Blank lines and lines beginning with `#` are ignored, so you can annotate the file:

   ```text
   # ~/.cc-review/trusted-reviewers: <name> <sha256>, one per line
   lint-service 3f1c...e9a0
   ```

3. **Re-run the review.** Discovery now matches the hash, so the reviewer's `detect` and `auth_check` probes run and it moves from untrusted to ready (or to a detection-based status such as `not available`). Any later edit to the reviewer or its parser changes the hash, so the reviewer returns to untrusted until you add the new line.

> [!CAUTION]
> Trusting a command reviewer lets the project run commands with your credentials. `/cc-review:init` prints the trust lines but never adds them for you. Add a line only after you have inspected the reviewer and everything it runs. Keep all of that inside the reviewer's own directory, because a script `invoke` or the parser calls from elsewhere in the repository is not covered by the hash.

Check: the trust file holds a reviewer name and a 64-character sha256 digest on one line.

```bash
grep -Eq '^[a-z0-9-]+ [0-9a-f]{64}$' ~/.cc-review/trusted-reviewers && echo trusted
```
<!-- expect: contains "trusted" -->

## Enable or disable reviewers

Every discovered reviewer runs by default except the ones whose own frontmatter ships disabled (among the bundled set, copilot, gator, and greptile). Turn any reviewer on or off for a whole project in config, or override the set for a single run with flags.

1. **Set a config key.** In `.cc-review/config.yml` (project) or `~/.cc-review/config.yml` (user), give each reviewer you want to change a `reviewers.<name>` key:

   ```yaml
   reviewers:
     security: false     # turn a bundled reviewer off
     gator: true         # turn an opt-in reviewer on
   ```

   A reviewer without a key keeps the `enabled` default from its own frontmatter.

2. **Override for one run with flags.** Flags beat config and apply after discovery:

   - `/cc-review:review --only correctness,security` runs only the named reviewers. `--only` re-enables a config-disabled reviewer, but never a reviewer that discovery skipped or marked invalid.
   - `/cc-review:review --no-security` subtracts one reviewer from the run. `--no-<name>` for an invalid reviewer prints a warning and the review continues.
   - `/cc-review:review --no-external` drops every external command reviewer at once.

The resolution order settles conflicts: CLI flags win over `--config`, then `--profile`, then project config, then user config, then the built-in defaults, then each reviewer's own `enabled` default.

Check: the config template you copy documents the `reviewers` key.

```bash
grep 'Enable or disable any discovered reviewer' review/config/config-template.yml
```
<!-- expect: contains "reviewers" -->

> [!NOTE]
> This page was verified against cc-review <!-- guide:attr cc-review-version -->1.4.0<!-- /guide:attr -->.
