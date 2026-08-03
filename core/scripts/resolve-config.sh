#!/usr/bin/env bash

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
  local config_file
  config_file="$(resolve_config_file)"

  if [ -z "$config_file" ]; then
    printf '%s' "$default"
    return
  fi

  local value
  value="$(yq -r ".$key // \"\"" "$config_file" 2>/dev/null)"
  if [ -n "$value" ]; then
    printf '%s' "$value"
  else
    printf '%s' "$default"
  fi
}
