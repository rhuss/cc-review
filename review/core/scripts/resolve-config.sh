#!/usr/bin/env bash

# The commands set CC_REVIEW_CORE_DIR before sourcing: zsh (the default shell
# of many harnesses) has no BASH_SOURCE, so the script cannot locate itself.
if [ -n "${CC_REVIEW_CORE_DIR:-}" ]; then
  CC_REVIEW_SCRIPT_DIR="$CC_REVIEW_CORE_DIR/scripts"
else
  CC_REVIEW_SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
fi
CC_REVIEW_CONFIG_DIR="$(CDPATH='' cd -- "$CC_REVIEW_SCRIPT_DIR/../../config" 2>/dev/null && pwd || echo "")"
CC_REVIEW_MERGED_CONFIG=""

_cc_review_cleanup() {
  [ -n "$CC_REVIEW_MERGED_CONFIG" ] && [ -f "$CC_REVIEW_MERGED_CONFIG" ] && rm -f "$CC_REVIEW_MERGED_CONFIG"
}

# Convert a dotted config key into a yq bracket path so hyphenated segments work:
#   reviewers.test-quality -> .["reviewers"]["test-quality"]
_cc_review_yq_path() {
  # Split on "." with parameter expansion: zsh does not word-split $key. The
  # result variable is not called "path", which zsh ties to PATH.
  local rest="$1" segment yq_path=""
  while :; do
    case "$rest" in
      *.*) segment="${rest%%.*}"; rest="${rest#*.}" ;;
      *) segment="$rest"; rest="" ;;
    esac
    yq_path="${yq_path}[\"${segment}\"]"
    [ -n "$rest" ] || break
  done
  printf '.%s' "$yq_path"
}

# Dotted path with non-empty segments; no quotes, brackets or whitespace, so a
# key can be spliced into a yq path expression safely.
# The whole string is matched (grep would accept a multi-line key when any one
# line matches).
_cc_review_valid_key() {
  local LC_ALL=C re='^[a-zA-Z_][a-zA-Z0-9_-]*(\.[a-zA-Z0-9_-]+)*$'
  [[ "$1" =~ $re ]]
}

# resolve_config_migrate_legacy_keys <config_file>
# Maps legacy agents.<x> and external_tools.<x> keys to reviewers.<x with _ -> ->
# when the new key is absent, printing one deprecation warning per legacy key.
# The legacy sections are removed afterwards. The file is required: it must be
# one layer (or a copy of one), never the merged config, or a reviewers.<x> key
# from another layer would hide the legacy value and break layer precedence.
resolve_config_migrate_legacy_keys() {
  if [ $# -lt 1 ] || [ -z "$1" ]; then
    echo "Error: resolve_config_migrate_legacy_keys requires a config file argument" >&2
    return 1
  fi
  local file="$1"
  [ -f "$file" ] || return 0

  local section key new_key existing
  for section in agents external_tools; do
    while IFS= read -r key; do
      [ -z "$key" ] && continue
      # Keys come from a user-editable file; never splice them into yq expressions.
      if ! _cc_review_valid_key "$key"; then
        echo "Warning: ignoring config key ${section}.${key}: invalid key name" >&2
        continue
      fi
      new_key="${key//_/-}"
      echo "Warning: config key ${section}.${key} is deprecated, use reviewers.${new_key}" >&2
      # Presence check with has(): an explicit `false` must count as present.
      existing="$(CC_K="$new_key" yq -r '(.reviewers // {}) | select(type == "!!map") | has(strenv(CC_K))' "$file" 2>/dev/null)"
      if [ "$existing" != "true" ]; then
        CC_K="$new_key" CC_S="$section" CC_L="$key" yq -i '.reviewers[strenv(CC_K)] = .[strenv(CC_S)][strenv(CC_L)]' "$file"
      fi
    done < <(yq -r "(.[\"${section}\"] // {}) | select(type == \"!!map\") | keys | .[]" "$file" 2>/dev/null)
    yq -i "del(.[\"${section}\"])" "$file"
  done
}

resolve_config_init() {
  local config_file=""
  local profile_name=""

  # A value of "-" means "not provided", so callers can always pass both flags
  # (zsh does not split an unquoted ${x:+--config "$x"} into two words).
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

  [ "$config_file" = "-" ] && config_file=""
  [ "$profile_name" = "-" ] && profile_name=""

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

  _cc_review_cleanup
  CC_REVIEW_MERGED_CONFIG="$(mktemp)"
  if [ -n "${ZSH_VERSION:-}" ]; then
    # zsh runs an EXIT trap set inside a function as soon as the function
    # returns, which would delete the merged config right away.
    zshexit_functions+=(_cc_review_cleanup)
  else
    # Chain an existing EXIT trap once; a second init must not chain this
    # trap to itself (the eval would recurse at exit).
    case "$(trap -p EXIT)" in
      *_cc_review_cleanup*) ;;
      *)
        _cc_review_existing_trap="$(trap -p EXIT | sed "s/^trap -- '//;s/' EXIT$//")"
        trap '_cc_review_cleanup; eval "$_cc_review_existing_trap"' EXIT
        ;;
    esac
  fi

  if [ ${#layers[@]} -eq 0 ]; then
    echo "{}" > "$CC_REVIEW_MERGED_CONFIG"
    return 0
  fi

  # Legacy agents.* / external_tools.* keys are migrated per layer, before the
  # merge, so layer precedence applies to them exactly as to reviewers.<name>
  # keys: a project config's agents.test_quality still beats a user config's
  # reviewers.test-quality, and a legacy key in a user config takes effect even
  # though a profile defines every bundled reviewers.<name> key.
  # The template itself carries no legacy keys and is merged as is.
  local layer migrated
  local -a merge_inputs=() temps=()
  for layer in "${layers[@]}"; do
    if [ "$layer" = "$defaults_file" ]; then
      merge_inputs+=("$layer")
      continue
    fi
    migrated="$(mktemp)"
    cp "$layer" "$migrated"
    resolve_config_migrate_legacy_keys "$migrated"
    merge_inputs+=("$migrated")
    temps+=("$migrated")
  done

  # Deep merge layers from lowest to highest priority.
  # Unknown keys are silently preserved: yq merge passes through all keys,
  # and resolve_config reads only known keys. This guarantees forward
  # compatibility (FR-017). If validation needs to reject unknown keys in the
  # future, add an allowlist bypass here.
  local rc=0
  if [ ${#merge_inputs[@]} -eq 1 ]; then
    # "[@]" rather than "[0]": zsh arrays start at index 1.
    cp "${merge_inputs[@]}" "$CC_REVIEW_MERGED_CONFIG"
  elif ! yq eval-all '. as $item ireduce ({}; . * $item)' "${merge_inputs[@]}" > "$CC_REVIEW_MERGED_CONFIG"; then
    echo "Error: failed to merge config layers" >&2
    rc=1
  fi
  [ ${#temps[@]} -gt 0 ] && rm -f "${temps[@]}"
  return $rc
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
    if ! _cc_review_valid_key "$key"; then
      echo "Error: invalid config key: $key" >&2
      return 1
    fi
    # The value travels through the environment, not the expression text.
    CC_V="$value" yq -i "$(_cc_review_yq_path "$key") = strenv(CC_V)" "$CC_REVIEW_MERGED_CONFIG"
  done
}

resolve_config_validate_types() {
  if [ -z "$CC_REVIEW_MERGED_CONFIG" ] || [ ! -f "$CC_REVIEW_MERGED_CONFIG" ]; then
    return 0
  fi

  local defaults_file="$CC_REVIEW_CONFIG_DIR/config-template.yml"

  local key val default_val

  # Every reviewers.<name> and allow_untrusted_checkout.<name> key must be
  # boolean. An invalid value is removed so the default applies: the
  # reviewer's frontmatter `enabled`, or no run in an untrusted checkout.
  local section fallback
  for section in reviewers allow_untrusted_checkout; do
    fallback="using the reviewer's default"
    [ "$section" = allow_untrusted_checkout ] && fallback="using false"
    while IFS= read -r key; do
      [ -z "$key" ] && continue
      val="$(CC_S="$section" CC_K="$key" yq -r '.[strenv(CC_S)][strenv(CC_K)]' "$CC_REVIEW_MERGED_CONFIG" 2>/dev/null)"
      if [ "$val" != "true" ] && [ "$val" != "false" ]; then
        echo "Warning: invalid value for ${section}.${key}: '${val}', ${fallback}" >&2
        CC_S="$section" CC_K="$key" yq -i 'del(.[strenv(CC_S)][strenv(CC_K)])' "$CC_REVIEW_MERGED_CONFIG"
      fi
    done < <(CC_S="$section" yq -r '(.[strenv(CC_S)] // {}) | select(type == "!!map") | keys | .[]' "$CC_REVIEW_MERGED_CONFIG" 2>/dev/null)
  done

  for key in severity.auto_fix pr_posting.enabled pr_posting.auto_detect_pr; do
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

# _cc_review_map_json <caller> <section>: prints one top-level map of the
# merged config as compact JSON ({} when absent or not a map)
_cc_review_map_json() {
  if [ -z "$CC_REVIEW_MERGED_CONFIG" ] || [ ! -f "$CC_REVIEW_MERGED_CONFIG" ]; then
    echo "Error: resolve_config_init must be called before $1" >&2
    return 1
  fi
  local out
  out="$(CC_S="$2" yq -o=json -I=0 '.[strenv(CC_S)] // {}' "$CC_REVIEW_MERGED_CONFIG" 2>/dev/null)" || out='{}'
  printf '%s' "$out" | jq -c 'if type == "object" then . else {} end' 2>/dev/null || printf '{}'
}

# resolve_config_reviewers_json: prints the merged config's reviewers map as
# compact JSON ({} when absent), the input of apply_config_enablement.
resolve_config_reviewers_json() {
  _cc_review_map_json resolve_config_reviewers_json reviewers
}

# resolve_config_untrusted_json: prints the merged config's
# allow_untrusted_checkout map as compact JSON ({} when absent), the input of
# apply_untrusted_checkout.
resolve_config_untrusted_json() {
  _cc_review_map_json resolve_config_untrusted_json allow_untrusted_checkout
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

  if ! _cc_review_valid_key "$key"; then
    printf '%s' "$default"
    return
  fi
  # Not "path": zsh ties that name to PATH, so a local would hide yq.
  local yq_path
  yq_path="$(_cc_review_yq_path "$key")"

  if [ -n "$CC_REVIEW_MERGED_CONFIG" ] && [ -f "$CC_REVIEW_MERGED_CONFIG" ]; then
    local value
    value="$(yq -r "$yq_path" "$CC_REVIEW_MERGED_CONFIG" 2>/dev/null)"
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
  value="$(yq -r "$yq_path" "$config_file" 2>/dev/null)"
  if [ -n "$value" ] && [ "$value" != "null" ]; then
    printf '%s' "$value"
  else
    printf '%s' "$default"
  fi
}
