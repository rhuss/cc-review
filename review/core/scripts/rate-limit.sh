#!/usr/bin/env bash
# rate-limit.sh - Hosting-service rate-limit handling of the bulk scripts
#
# Sourced by bulk-select.sh, bulk-apply.sh and pr-worktree.sh (under bash):
#   rate_limited <file>...  true when a file holds GitHub's rate-limit wording
#                           (primary, including the GraphQL "already exceeded"
#                           form, or secondary)
#   try <errfile> <cmd...>  runs the command with stderr in <errfile>. A rate
#                           limit is checked before anything else and exits 75
#                           (stderr "Error: RATE_LIMITED"); any other failure
#                           returns the command's exit code for the caller to
#                           map.

rate_limited() {
  grep -qiE 'API rate limit (already )?exceeded|secondary rate limit' "$@"
}

try() {
  local err="$1" rc=0
  shift
  "$@" 2>"$err" || rc=$?
  if [ "$rc" -ne 0 ] && rate_limited "$err"; then
    echo "Error: RATE_LIMITED" >&2
    exit 75
  fi
  return "$rc"
}
