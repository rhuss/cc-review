---
name: init
description: Initialize cc-review configuration by detecting tools and generating .cc-review/config.yml
argument-hint: "[--interactive]"
---

# Init

Generate a `.cc-review/config.yml` configuration file by auto-detecting the project environment.

## Prerequisites

```bash
source "$(dirname "$0")/../scripts/resolve-config.sh"
source "$(dirname "$0")/../scripts/detect-tools.sh"
```

## Step 1: Detect Environment

### External Tools

```bash
TOOL_RESULTS=$(detect_external_tools)
```

Parse each line (`tool:installed:auth_status`) and build config values:

```bash
for line in $TOOL_RESULTS; do
  TOOL_NAME="${line%%:*}"
  rest="${line#*:}"
  INSTALLED="${rest%%:*}"
  AUTH_STATUS="${rest#*:}"

  if [ "$INSTALLED" = "true" ] && [ -n "$AUTH_STATUS" ]; then
    echo "Warning: $TOOL_NAME is installed but not authenticated" >&2
  fi
done
```

### Test Command

```bash
TEST_CMD=$(detect_test_command)
```

### Platform

```bash
PLATFORM=$(detect_platform)
```

## Step 2: Build Config

Generate a YAML config from the detections. Start from the default template structure and override detected values:

```yaml
agents:
  correctness: true
  architecture: true
  security: true
  production: true
  test_quality: true
  goal_alignment: true

external_tools:
  coderabbit: <detected>
  copilot: <detected>
  codex: <detected>

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

If an existing config is found, perform a deep merge where existing values take priority (preserving user customizations). New keys from detection are added:

```bash
if [ -n "$EXISTING_CONFIG" ]; then
  MERGED=$(yq eval-all '. as $item ireduce ({}; . * $item)' "$GENERATED_CONFIG" "$EXISTING_CONFIG")
fi
```

## Step 4: Preview and Confirm

Display the generated (or merged) config to the user:

```
## Generated Configuration

<YAML config content>

Detection results:
- External tools: coderabbit (<installed/not found>), copilot (<installed/not found>), codex (<installed/not found>)
- Test command: <detected command or "none detected">
- Platform: <github/gitlab/not detected>
```

If any tools had authentication warnings, display them here.

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

## Interactive Mode

When `--interactive` is passed, walk through each config section with questions instead of using smart defaults.

### Section 1: Agents

Present each agent with a description and ask whether to enable:

- Correctness: Checks for bugs, logic errors, and incorrect behavior
- Architecture: Reviews code structure, patterns, and idioms
- Security: Scans for vulnerabilities and security anti-patterns
- Production: Checks deployment readiness, logging, error handling
- Test Quality: Reviews test coverage and test design
- Goal Alignment: Verifies code matches PR goals and spec requirements

### Section 2: External Tools

For each detected tool, confirm whether to enable. For tools not installed, note they are unavailable.

### Section 3: Severity

Ask for:
- Minimum confidence threshold (0-100, default 70)
- Which severities should trigger REQUEST_CHANGES (default: Critical, Important)
- Whether to enable auto-fix (default: true)

### Section 4: Output

Ask for:
- Output directory (default: current directory)
- Verbosity level (quiet/normal/verbose, default: normal)
- Findings filename (default: review-findings.md)

### Section 5: PR Posting

Ask for:
- Enable PR review posting (default: true)
- Auto-detect PR from branch (default: false)
- Maximum inline comments (default: 50)

### Section 6: Test

Show the auto-detected test command and ask to confirm or override:
- Test command (default: auto-detected)
- Test timeout in seconds (default: 300)

After all sections, preview the complete config and confirm.
