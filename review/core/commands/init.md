---
name: init
description: Initialize cc-review configuration by discovering reviewers, detecting tools and generating .cc-review/config.yml
argument-hint: "[--interactive]"
---

# Init

Generate a `.cc-review/config.yml` configuration file by auto-detecting the project environment.

## Prerequisites

The command shim already resolved the cc-review core directory (the directory that contains `commands/init.md`); set `CC_REVIEW_CORE_DIR` to that absolute path at the top of every shell block of this command, since the harness may run each block in a new shell. Resolve `CORE_DIR` first, then source the helper scripts exactly once:

```bash
# $0 names this file only when the command file itself is executed; in a
# harness-run block it is the shell (zsh, bash), so it is a fallback only.
if [ -n "${CC_REVIEW_CORE_DIR:-}" ] && [ -f "$CC_REVIEW_CORE_DIR/commands/init.md" ]; then
  CORE_DIR="$CC_REVIEW_CORE_DIR"
else
  case "$0" in
    */commands/init.md) CORE_DIR="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)" ;;
    *) echo "Error: cc-review core directory unknown; set CC_REVIEW_CORE_DIR to the core path the shim resolved" >&2; exit 1 ;;
  esac
fi
export CC_REVIEW_CORE_DIR="$CORE_DIR"
source "$CORE_DIR/scripts/resolve-config.sh"
source "$CORE_DIR/scripts/detect-tools.sh"
```

## Step 1: Detect Environment

### Reviewers

Discover every reviewer plugin (bundled, user, project layers). Discovery runs the `detect` and `auth_check` commands of command reviewers, so this also detects the external tools. Project-layer command reviewers run nothing until the user trusts them in `~/.cc-review/trusted-reviewers` (never a file inside the project):

```bash
GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
REVIEWER_BODY_DIR=$(mktemp -d "${TMPDIR:-/tmp}/cc-review-reviewers.XXXXXX")
if ! REVIEWERS_JSON=$("$CORE_DIR/scripts/discover-reviewers.sh" \
  --core-dir "$CORE_DIR" \
  --project-dir "${GIT_ROOT:-$PWD}" \
  --trust-file "$HOME/.cc-review/trusted-reviewers" \
  --body-dir "$REVIEWER_BODY_DIR"); then
  echo "Error: reviewer discovery failed (see the message above); init cannot continue." >&2
  rm -rf "$REVIEWER_BODY_DIR"
  exit 1
fi
echo "REVIEWER_BODY_DIR=$REVIEWER_BODY_DIR"
```

Record `REVIEWER_BODY_DIR` (Interactive Mode reads the first body line from it; do not tie it to a shell `EXIT` trap, the harness may run each block in a new shell) and remove it in Step 5, or before stopping when the user cancels.

A non-zero exit means a missing dependency (`jq` 1.6+, `yq` v4, `awk`); its stderr names the cause. Show discovery warnings (invalid reviewers) to the user. Then print the discovered reviewers table, one row per entry (valid or not), in discovery order:

```
Discovered reviewers:
| Name           | Layer   | Kind    | Enabled | Preconditions           |
|----------------|---------|---------|---------|-------------------------|
| {name}         | {layer} | {kind}  | {enabled} | {precondition status} |
```

The Preconditions column is derived from the entry's status and reason:
- `ready` → `ok`
- `skipped` with a reason starting with `requires:` → the reason plus ` (not now)`, for example `requires: pr (not now)`
- `skipped` with a reason starting with `not available` or `not authenticated` → the reason verbatim (it may carry the last line the check printed, such as `not authenticated: token expired`)
- `skipped` with reason `detection timed out` or `authentication check timed out` → the reason verbatim; the tool's state is unknown, never report it as installed
- `skipped` with a reason starting with `untrusted project command reviewer` → `untrusted (see below)`
- `skipped` with any other reason → the reason verbatim
- `invalid` → `invalid: {reason}` (Enabled shows `-`)

Append ` (overrides {overrides})` to the Layer value when the entry's `overrides` field is set.

Read the command reviewer availability for Step 4 directly from the discovery JSON:

```bash
printf '%s' "$REVIEWERS_JSON" | jq -r '.[] | select(.kind == "command" and .status != "invalid")
  | "\(.name): " + (if .status == "ready" then "installed"
      elif (.reason | startswith("not authenticated")) or .reason == "authentication check timed out" then "installed, " + .reason
      elif (.reason | startswith("not available")) then "not found"
      elif .reason == "detection timed out" then "unknown (detection timed out)"
      elif (.reason | startswith("untrusted project command reviewer")) then "untrusted"
      else .reason end)'
```

Print one `Warning: <name> is installed but not authenticated` line (with the detail after the colon, if any) for every entry whose reason starts with `not authenticated`.

List the untrusted project command reviewers with the line that trusts each one's current version:

```bash
UNTRUSTED=$(printf '%s' "$REVIEWERS_JSON" | jq -r '.[] | select(.status == "skipped" and ((.reason // "") | startswith("untrusted project command reviewer")))
  | .reason | capture("trust with: (?<line>[^)]*)").line')
if [ -n "$UNTRUSTED" ]; then
  echo "Untrusted project command reviewers run nothing until you trust them. To trust the current version, add these lines to ~/.cc-review/trusted-reviewers:"
  printf '%s\n' "$UNTRUSTED"
fi
```

Show these lines to the user as they are; do not add them to the trust file on the user's behalf, since trusting a reviewer lets the project run commands with the user's credentials. Any edit to the reviewer file or its parser changes the hash and needs a new line.

Compute each reviewer's effective enabled value for the generated config: `true` for entries with `status: ready` whose `enabled` is true, `false` for entries whose `enabled` is false, and `false` for command reviewers that are skipped with a reason starting with `not available`. Reviewers skipped for other reasons (for example `requires: pr`, a timed-out check, or an untrusted project command reviewer) keep their `enabled` value since those conditions are evaluated per run. Invalid entries get no key. The config template sets no `reviewers` keys, so this section is the only place the generated config records enablement.

### Test Command

```bash
TEST_CMD=$(detect_test_command)
```

### Platform

```bash
PLATFORM=$(detect_platform)
```

## Step 2: Build Config

Generate a YAML config from the detections. Start from the default template structure and override detected values. The `reviewers:` section lists every discovered valid reviewer (bundled, user, and project) with its effective enabled value from Step 1; never emit `agents:` or `external_tools:` keys:

```yaml
reviewers:
  <name>: <effective enabled>   # one line per discovered reviewer, hyphenated names
  # for example:
  # correctness: true
  # test-quality: true
  # goal-alignment: true
  # coderabbit: <true when available, else false>
  # copilot: false
  # codex: <true when available, else false>
  # gator: false
  # accessibility: true       (a project reviewer)

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

output:
  dir: "."
  verbosity: "normal"
  findings_filename: "review-findings.md"

test:
  command: "<detected or empty>"
  timeout_seconds: 300

max_fix_rounds: 3
```

## Step 3: Check for Existing Config

```bash
EXISTING_CONFIG=""
GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
if [ -n "$GIT_ROOT" ] && [ -f "$GIT_ROOT/.cc-review/config.yml" ]; then
  EXISTING_CONFIG="$GIT_ROOT/.cc-review/config.yml"
fi
```

If an existing config is found, perform a deep merge where existing values take priority (preserving user customizations). New keys from detection are added. Legacy `agents.*` / `external_tools.*` keys in the existing config are migrated to `reviewers.<name>` on a copy first; otherwise the generated `reviewers.<name>` key would shadow the user's legacy value and the next review would drop it:

```bash
if [ -n "$EXISTING_CONFIG" ]; then
  EXISTING_COPY=$(mktemp)
  cp "$EXISTING_CONFIG" "$EXISTING_COPY"
  resolve_config_migrate_legacy_keys "$EXISTING_COPY"
  MERGED=$(yq eval-all '. as $item ireduce ({}; . * $item)' "$GENERATED_CONFIG" "$EXISTING_COPY")
  rm -f "$EXISTING_COPY"
fi
```

## Step 4: Preview and Confirm

Display the generated (or merged) config to the user:

```
## Generated Configuration

<YAML config content>

Detection results:
- Reviewers: <N> discovered (<N> prompt, <N> command, <N> invalid)
- Command reviewers: <name> (<installed/not found/not authenticated/unknown/untrusted>), ... (one entry per discovered kind: command reviewer, by name, from the availability query in Step 1)
- Test command: <detected command or "none detected">
- Platform: <github/gitlab/not detected>
```

If any command reviewers had authentication warnings, display them here, followed by the untrusted project command reviewers and their trust lines.

Ask the user to confirm before writing:
- **Confirm**: Write the config file
- **Edit**: Let the user modify values before writing
- **Cancel**: Exit without writing

## Step 5: Write Config

```bash
CONFIG_DIR="${GIT_ROOT:-.}/.cc-review"
mkdir -p "$CONFIG_DIR"
```

Write the confirmed config to `.cc-review/config.yml`.

Report:
```
Configuration written to .cc-review/config.yml
```

Remove the reviewer body files created by discovery (also on the Cancel path):

```bash
[ -n "$REVIEWER_BODY_DIR" ] && [ -d "$REVIEWER_BODY_DIR" ] && rm -rf "$REVIEWER_BODY_DIR"
```

## Interactive Mode

When `--interactive` is passed, walk through each config section with questions instead of using smart defaults.

### Section 1: Reviewers

Iterate the discovered reviewers from Step 1 (valid entries only). For each one, present its `display_name`, `kind`, `layer` (with the override note when set), the first line of its body as a short description, and its precondition status, then ask whether to enable it. Command reviewers that are `skipped (not available)` are presented as unavailable and default to disabled; reviewers with `enabled: false` in their frontmatter (for example gator) default to disabled.

### Section 2: Severity

Ask for:
- Minimum confidence threshold (0-100, default 70)
- Which severities should fail the review and block the merge (default: Critical, Important). Phrase it in these words; do not show GitHub API terms such as `REQUEST_CHANGES` to the user
- Whether to enable auto-fix (default: true)

### Section 3: Output

Ask for:
- Output directory (default: current directory)
- Verbosity level (quiet/normal/verbose, default: normal)
- Findings filename (default: review-findings.md)

### Section 4: PR Posting

Ask for:
- Enable PR review posting (default: true)
- Auto-detect PR from branch (default: false)
- Maximum inline comments (default: 50)

### Section 5: Test

Show the auto-detected test command and ask to confirm or override:
- Test command (default: auto-detected)
- Test timeout in seconds (default: 300)

After all sections, preview the complete config and confirm.
