#!/usr/bin/env bash

CC_REVIEW_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CC_REVIEW_CONFIG_DIR="$(cd "$CC_REVIEW_SCRIPT_DIR/../../config" && pwd 2>/dev/null || echo "")"
CC_REVIEW_MERGED_CONFIG=""

_cc_review_cleanup() {
  [ -n "$CC_REVIEW_MERGED_CONFIG" ] && [ -f "$CC_REVIEW_MERGED_CONFIG" ] && rm -f "$CC_REVIEW_MERGED_CONFIG"
}

resolve_config_init() {
  local config_file=""
  local profile_name=""

  while [ $# -gt 0 ]; do
    case "$1" in
      --config)
        if [ $# -lt 2 ] || [ -z "$2" ]; then
          echo "Error: --config requires a path argument" >&2
          return 1
        fi
        config_file="$2"
        shift 2
        ;;
      --profile)
        if [ $# -lt 2 ] || [ -z "$2" ]; then
          echo "Error: --profile requires a name argument" >&2
          return 1
        fi
        profile_name="$2"
        shift 2
        ;;
      *)
        shift
        ;;
    esac
  done

  if [ -n "$config_file" ] && [ ! -f "$config_file" ]; then
    echo "Error: config file not found: $config_file" >&2
    return 1
  fi

  local profile_file=""
  if [ -n "$profile_name" ]; then
    if ! echo "$profile_name" | grep -qE '^[a-zA-Z0-9_-]+$'; then
      echo "Error: invalid profile name '$profile_name' (only alphanumeric, hyphens, underscores allowed)" >&2
      return 1
    fi
    profile_file="$CC_REVIEW_CONFIG_DIR/profiles/${profile_name}.yml"
    if [ ! -f "$profile_file" ]; then
      echo "Error: unknown profile '$profile_name'. Available profiles:" >&2
      for p in "$CC_REVIEW_CONFIG_DIR/profiles/"*.yml; do
        [ -f "$p" ] && echo "  - $(basename "$p" .yml)" >&2
      done
      return 1
    fi
  fi

  local defaults_file="$CC_REVIEW_CONFIG_DIR/config-template.yml"
  local user_config="$HOME/.cc-review/config.yml"
  local project_config=""
  local git_root
  git_root="$(git rev-parse --show-toplevel 2>/dev/null)"
  if [ -n "$git_root" ] && [ -f "$git_root/.cc-review/config.yml" ]; then
    project_config="$git_root/.cc-review/config.yml"
  fi

  local layers=()

  if [ -f "$defaults_file" ]; then
    layers+=("$defaults_file")
  fi

  if [ -f "$user_config" ]; then
    _cc_review_validate_yaml "$user_config" || return 1
    layers+=("$user_config")
  fi

  if [ -n "$project_config" ]; then
    _cc_review_validate_yaml "$project_config" || return 1
    layers+=("$project_config")
  fi

  if [ -n "$profile_file" ]; then
    _cc_review_validate_yaml "$profile_file" || return 1
    layers+=("$profile_file")
  fi

  if [ -n "$config_file" ]; then
    _cc_review_validate_yaml "$config_file" || return 1
    layers+=("$config_file")
  fi

  CC_REVIEW_MERGED_CONFIG="$(mktemp)"
  _cc_review_existing_trap="$(trap -p EXIT | sed "s/^trap -- '//;s/' EXIT$//")"
  trap '_cc_review_cleanup; eval "$_cc_review_existing_trap"' EXIT

  if [ ${#layers[@]} -eq 0 ]; then
    echo "{}" > "$CC_REVIEW_MERGED_CONFIG"
    return 0
  fi

  if [ ${#layers[@]} -eq 1 ]; then
    cp "${layers[0]}" "$CC_REVIEW_MERGED_CONFIG"
    return 0
  fi

  # Deep merge layers from lowest to highest priority.
  # Unknown keys are silently preserved: yq merge passes through all keys,
  # and resolve_config reads only known keys. This guarantees forward
  # compatibility (FR-017). If validation needs to reject unknown keys in the
  # future, add an allowlist bypass here.
  if ! yq eval-all '. as $item ireduce ({}; . * $item)' "${layers[@]}" > "$CC_REVIEW_MERGED_CONFIG"; then
    echo "Error: failed to merge config layers" >&2
    return 1
  fi
}

_cc_review_validate_yaml() {
  local file="$1"
  if ! yq '.' "$file" >/dev/null 2>&1; then
    local err
    err="$(yq '.' "$file" 2>&1)"
    echo "Error: invalid YAML in $file: $err" >&2
    return 1
  fi
}

resolve_config_apply_cli_overrides() {
  if [ -z "$CC_REVIEW_MERGED_CONFIG" ] || [ ! -f "$CC_REVIEW_MERGED_CONFIG" ]; then
    echo "Error: resolve_config_init must be called before resolve_config_apply_cli_overrides" >&2
    return 1
  fi

  local pair
  for pair in "$@"; do
    local key="${pair%%=*}"
    local value="${pair#*=}"
    if ! echo "$key" | grep -qE '^[a-zA-Z_][a-zA-Z0-9_.]*$'; then
      echo "Error: invalid config key: $key" >&2
      return 1
    fi
    yq -i ".${key} = \"${value}\"" "$CC_REVIEW_MERGED_CONFIG"
  done
}

resolve_config_validate_types() {
  if [ -z "$CC_REVIEW_MERGED_CONFIG" ] || [ ! -f "$CC_REVIEW_MERGED_CONFIG" ]; then
    return 0
  fi

  local defaults_file="$CC_REVIEW_CONFIG_DIR/config-template.yml"

  local key val default_val
  for key in agents.correctness agents.architecture agents.security agents.production agents.test_quality agents.goal_alignment \
             external_tools.coderabbit external_tools.copilot external_tools.codex \
             severity.auto_fix pr_posting.enabled pr_posting.auto_detect_pr; do
    val="$(yq -r ".${key} // \"\"" "$CC_REVIEW_MERGED_CONFIG" 2>/dev/null)"
    if [ -n "$val" ] && [ "$val" != "true" ] && [ "$val" != "false" ]; then
      default_val="$(yq -r ".${key}" "$defaults_file" 2>/dev/null)"
      echo "Warning: invalid value for ${key}: '${val}', using default" >&2
      yq -i ".${key} = ${default_val}" "$CC_REVIEW_MERGED_CONFIG"
    fi
  done

  val="$(yq -r '.severity.min_confidence // ""' "$CC_REVIEW_MERGED_CONFIG" 2>/dev/null)"
  if [ -n "$val" ]; then
    if ! echo "$val" | grep -qE '^[0-9]+$' || [ "$val" -lt 0 ] 2>/dev/null || [ "$val" -gt 100 ] 2>/dev/null; then
      echo "Warning: invalid value for severity.min_confidence: '${val}', using default" >&2
      default_val="$(yq -r '.severity.min_confidence' "$defaults_file" 2>/dev/null)"
      yq -i ".severity.min_confidence = ${default_val}" "$CC_REVIEW_MERGED_CONFIG"
    fi
  fi

  val="$(yq -r '.output.verbosity // ""' "$CC_REVIEW_MERGED_CONFIG" 2>/dev/null)"
  if [ -n "$val" ] && [ "$val" != "quiet" ] && [ "$val" != "normal" ] && [ "$val" != "verbose" ]; then
    echo "Warning: invalid value for output.verbosity: '${val}', using default" >&2
    yq -i '.output.verbosity = "normal"' "$CC_REVIEW_MERGED_CONFIG"
  fi

  val="$(yq -r '.max_fix_rounds // ""' "$CC_REVIEW_MERGED_CONFIG" 2>/dev/null)"
  if [ -n "$val" ]; then
    if ! echo "$val" | grep -qE '^[1-9][0-9]*$'; then
      echo "Warning: invalid value for max_fix_rounds: '${val}', using default" >&2
      default_val="$(yq -r '.max_fix_rounds' "$defaults_file" 2>/dev/null)"
      yq -i ".max_fix_rounds = ${default_val}" "$CC_REVIEW_MERGED_CONFIG"
    fi
  fi

  val="$(yq -r '.pr_posting.max_inline_comments // ""' "$CC_REVIEW_MERGED_CONFIG" 2>/dev/null)"
  if [ -n "$val" ]; then
    if ! echo "$val" | grep -qE '^[1-9][0-9]*$'; then
      echo "Warning: invalid value for pr_posting.max_inline_comments: '${val}', using default" >&2
      default_val="$(yq -r '.pr_posting.max_inline_comments' "$defaults_file" 2>/dev/null)"
      yq -i ".pr_posting.max_inline_comments = ${default_val}" "$CC_REVIEW_MERGED_CONFIG"
    fi
  fi

  val="$(yq -r '.test.timeout_seconds // ""' "$CC_REVIEW_MERGED_CONFIG" 2>/dev/null)"
  if [ -n "$val" ]; then
    if ! echo "$val" | grep -qE '^[1-9][0-9]*$'; then
      echo "Warning: invalid value for test.timeout_seconds: '${val}', using default" >&2
      default_val="$(yq -r '.test.timeout_seconds' "$defaults_file" 2>/dev/null)"
      yq -i ".test.timeout_seconds = ${default_val}" "$CC_REVIEW_MERGED_CONFIG"
    fi
  fi
}

resolve_config_file() {
  local git_root
  git_root="$(git rev-parse --show-toplevel 2>/dev/null)"
  if [ -n "$git_root" ] && [ -f "$git_root/.cc-review/config.yml" ]; then
    printf '%s' "$git_root/.cc-review/config.yml"
    return
  fi
  if [ -f "$HOME/.cc-review/config.yml" ]; then
    printf '%s' "$HOME/.cc-review/config.yml"
    return
  fi
  printf ''
}

resolve_config() {
  local key="$1"
  local default="${2:-}"

  if [ -n "$CC_REVIEW_MERGED_CONFIG" ] && [ -f "$CC_REVIEW_MERGED_CONFIG" ]; then
    local value
    value="$(yq -r ".${key}" "$CC_REVIEW_MERGED_CONFIG" 2>/dev/null)"
    if [ -n "$value" ] && [ "$value" != "null" ]; then
      printf '%s' "$value"
    else
      printf '%s' "$default"
    fi
    return
  fi

  local config_file
  config_file="$(resolve_config_file)"

  if [ -z "$config_file" ]; then
    printf '%s' "$default"
    return
  fi

  local value
  value="$(yq -r ".${key}" "$config_file" 2>/dev/null)"
  if [ -n "$value" ] && [ "$value" != "null" ]; then
    printf '%s' "$value"
  else
    printf '%s' "$default"
  fi
}
