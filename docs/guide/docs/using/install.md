# Install cc-review

<!-- Sources:
cc-review:README.md:23
cc-review:README.md:29-38
cc-review:README.md:44-50
cc-review:README.md:56-61
cc-review:README.md:65-71
cc-review:README.md:102
cc-review:README.md:121
cc-review:review/core/scripts/discover-reviewers.sh:666-680
cc-review:review/.claude-plugin/plugin.json:1-20
-->

cc-review ships as one plugin directory (`review/`) that carries a native manifest for each supported harness: Claude Code, Codex, and OpenCode. Each harness reads only its own manifest and ignores the others, so installing the plugin once registers the cc-review commands with the harness you use. Install it in the harness you already run.

> [!NOTE]
> This guide's command examples use Claude Code syntax (`/cc-review:review`). On Codex use `$review`; on OpenCode use `/review`. See [Invoking cc-review across harnesses](../reference/invocation.md).

## Prerequisites

cc-review needs a few command-line tools. Install these before you add the plugin:

- **`jq` 1.6 or newer.** Reviewer discovery and the inbox and issue commands use it.
- **mikefarah `yq` 4.18 or newer.** Reviewer discovery parses reviewer frontmatter with it. The Python `yq` and `yq` v3 use a different syntax and make every reviewer look malformed, so install the mikefarah build.
- **`awk`.** Reviewer discovery uses it alongside `jq` and `yq`.
- **`gh`, authenticated.** The inbox and issue commands call the GitHub CLI for the selected repository.
- **Python 3.9 or newer.** The inbox and issue commands run on it.

## Install on Claude Code

Claude Code installs cc-review through its plugin system. From a local clone of the repository, register it as a marketplace and install the plugin:

```bash
claude plugin marketplace add /path/to/cc-review
claude plugin install cc-review@cc-review-plugin-development
```

This registers the local marketplace and installs the plugin. The `/cc-review:review`, `/cc-review:triage`, `/cc-review:inbox`, and `/cc-review:issue` commands become available immediately.

> [!TIP]
> From a local clone you can run `make install` instead. It registers the marketplace and installs the plugin in one step.

## Install on Codex

Codex uses the same plugin commands. From a local clone, register the marketplace and install the plugin:

```bash
codex plugin marketplace add /path/to/cc-review
codex plugin install cc-review@cc-review-plugin-development
```

The `review`, `triage`, `inbox`, and `issue` skills are then discovered from `review/skills/`.

## Install on OpenCode

OpenCode reads its commands from a directory inside your project. Run the install script from a local clone and point it at the project you want to review:

```bash
/path/to/cc-review/review/opencode/install.sh --project-dir .
```

This copies the cc-review commands to `.opencode/plugins/cc-review/` in your project.

Check: the plugin directory exists in your project after the script runs.

```bash
ls .opencode/plugins/cc-review/
```
<!-- expect: exit 0 -->

## Install the spec-kit extension (optional)

> [!NOTE]
> This step is only for projects that use cc-spex. Skip it otherwise.

Add cc-review as a spec-kit extension from a local clone:

```bash
specify extension add /path/to/cc-review/speckit
```

The spec-kit adapter then passes spec paths, constitution hints, and output locations during the ship pipeline.

## Duplicate command entries

If a harness lists each cc-review command twice, you most likely have more than one copy of the plugin installed. List the installed plugins (`claude plugin list` in Claude Code), uninstall every copy except the current one, then reinstall from your local clone.

> [!NOTE]
> These steps were verified against cc-review <!-- guide:attr cc-review-version -->1.4.0<!-- /guide:attr -->.
