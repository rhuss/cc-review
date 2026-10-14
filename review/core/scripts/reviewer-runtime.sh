#!/usr/bin/env bash
#
# reviewer-runtime.sh: runtime helpers the review command applies to the
# discovery output (enablement, selection, detection) and per finding or
# command run (timeouts, invoke substitution, severity mapping).
#
# Executed:
#   reviewer-runtime.sh helper <function> [args...]
#
#   Runs one helper under bash, so a caller whose shell is not bash (zsh is the
#   macOS default) never has to source this file: word splitting, set -f and
#   shopt are bash semantics. Sourcing the file (bash only) defines the same
#   functions; discover-reviewers.sh and the tests do that.
#
# Helpers:
#   run_with_timeout <seconds> <command...>
#   substitute_invoke <template> <base_branch> <files> <pr_number>
#   map_severity <reviewer_json_element> <native_severity>
#   apply_config_enablement <reviewers_json> <reviewers_config_json>
#   apply_cli_selection <reviewers_json> <only_csv> <no_csv> <external_flag>
#   apply_detection <reviewers_json>
#
# The status values these helpers read and write are defined in one place:
# specs/004-reviewer-plugins/contracts/discovery-output.md ("Status values").

CC_REVIEW_SEVERITIES="Critical Important Minor Notable"
# Wall-clock bound (seconds) for a command reviewer's detect and auth_check.
CC_REVIEW_DETECT_TIMEOUT="${CC_REVIEW_DETECT_TIMEOUT:-15}"
# Timeout backend: auto (default), timeout, gtimeout, perl or none. Tests set it.
CC_REVIEW_TIMEOUT_BACKEND="${CC_REVIEW_TIMEOUT_BACKEND:-auto}"
# Seconds between SIGTERM and SIGKILL when a command outlives its bound.
CC_REVIEW_KILL_AFTER="${CC_REVIEW_KILL_AFTER:-5}"
# Longest skip reason taken from a failed probe's stderr.
CC_REVIEW_REASON_MAX=160

_runtime_warn() {
  printf 'Warning: %s\n' "$*" >&2
}

# run_with_timeout <seconds> <command...>
# Uses timeout/gtimeout when available, then perl (present on macOS and every
# Linux distribution), otherwise runs unbounded with a warning. Exit 124 on
# timeout. A command that ignores SIGTERM is killed CC_REVIEW_KILL_AFTER
# seconds later, so the bound holds for every backend.
run_with_timeout() {
  local secs="$1"
  shift
  local backend="$CC_REVIEW_TIMEOUT_BACKEND"
  if [ "$backend" = "auto" ]; then
    if command -v timeout >/dev/null 2>&1; then backend="timeout"
    elif command -v gtimeout >/dev/null 2>&1; then backend="gtimeout"
    elif command -v perl >/dev/null 2>&1; then backend="perl"
    else backend="none"
    fi
  fi
  local rc=0
  case "$backend" in
    timeout|gtimeout)
      # Old busybox builds have no -k; probe once per process instead of
      # failing every command with a usage error.
      if [ -z "${CC_REVIEW_TIMEOUT_HAS_K:-}" ]; then
        if "$backend" -k 1 1 true >/dev/null 2>&1; then CC_REVIEW_TIMEOUT_HAS_K=true; else CC_REVIEW_TIMEOUT_HAS_K=false; fi
      fi
      local started=$SECONDS
      if [ "$CC_REVIEW_TIMEOUT_HAS_K" = true ]; then
        "$backend" -k "$CC_REVIEW_KILL_AFTER" "$secs" "$@" || rc=$?
        # timeout exits 137 when it had to escalate to SIGKILL; that is still
        # a timeout when the bound has passed (a command killed early by
        # someone else keeps 137).
        [ "$rc" -eq 137 ] && [ $((SECONDS - started)) -ge "$secs" ] && rc=124
      else
        "$backend" "$secs" "$@" || rc=$?
      fi
      # busybox timeout reports 143 (SIGTERM) instead of 124 after killing the child
      if [ "$rc" -eq 143 ]; then
        if [ -z "${CC_REVIEW_TIMEOUT_IS_BUSYBOX:-}" ]; then
          if "$backend" --help 2>&1 | grep -q -i busybox; then CC_REVIEW_TIMEOUT_IS_BUSYBOX=true; else CC_REVIEW_TIMEOUT_IS_BUSYBOX=false; fi
        fi
        [ "$CC_REVIEW_TIMEOUT_IS_BUSYBOX" = true ] && rc=124
      fi
      return $rc
      ;;
    perl)
      # Matches coreutils timeout: perl leaves the caller's process group (a
      # group kill of the caller cannot remove the bound), the child gets its
      # own group so the whole command tree is signalled, and TERM/INT/HUP sent
      # to perl are forwarded to that group instead of orphaning it.
      perl -e '
        my $secs = shift @ARGV;
        setpgrp(0, 0);
        my $pid = fork();
        exit 125 unless defined $pid;
        if ($pid == 0) { setpgrp(0, 0); exec { $ARGV[0] } @ARGV; exit 127; }
        my $stop = sub {
          my $code = shift;
          kill "TERM", -$pid; select(undef, undef, undef, 1); kill "KILL", -$pid;
          waitpid($pid, 0); exit $code;
        };
        local $SIG{ALRM} = sub { $stop->(124) };
        local $SIG{TERM} = sub { $stop->(143) };
        local $SIG{INT} = sub { $stop->(130) };
        local $SIG{HUP} = sub { $stop->(129) };
        alarm $secs;
        waitpid($pid, 0);
        my $st = $?;
        exit(($st & 127) ? 128 + ($st & 127) : ($st >> 8));
      ' "$secs" "$@"
      ;;
    *)
      _runtime_warn "no timeout, gtimeout or perl found; running '$1' without a time bound"
      "$@"
      ;;
  esac
}

# substitute_invoke <template> <base_branch> <files> <pr_number>
# Replaces {base_branch}, {files} (one path per line in <files>; each path is
# shell-quoted and the result is space-separated) and {pr_number}. The
# placeholder set is defined once, in the discovery validator
# (CC_REVIEW_PLACEHOLDERS in discover-reviewers.sh), which rejects any other.
# base_branch and pr_number are inserted verbatim (templates may embed them inside
# their own quoting), so they are restricted to a safe character set. Returns 1
# with an error on stderr when a value is unsafe.
substitute_invoke() {
  local template="$1" base_branch="$2" files="$3" pr_number="${4:-}"
  # ASCII ranges only, independent of the caller's locale (bash 3.2 would
  # otherwise admit accented letters under en_US.UTF-8). A leading "-" would be
  # read as an option by the tool, so it is rejected too.
  local LC_ALL=C
  case "$base_branch" in
    ""|-*|*[!A-Za-z0-9._/@+-]*)
      printf 'Error: unsupported base branch name: %s\n' "$base_branch" >&2
      return 1 ;;
  esac
  case "$pr_number" in
    *[!0-9]*)
      printf 'Error: PR number must be numeric: %s\n' "$pr_number" >&2
      return 1 ;;
  esac
  # The list holds one path per line (git diff --name-only), so a path with
  # spaces stays one argument. Pathname expansion is disabled so paths such as
  # app/[id]/page.tsx are not globbed against the working directory. A path
  # starting with "-" (chosen by whoever authored the change) is prefixed with
  # "./" so the tool cannot read it as an option.
  local quoted="" f glob_was_off=false IFS=$'\n'
  case "$-" in *f*) glob_was_off=true ;; esac
  set -f
  for f in $files; do
    [ -n "$f" ] || continue
    case "$f" in -*) f="./$f" ;; esac
    quoted="${quoted:+$quoted }$(printf '%q' "$f")"
  done
  [ "$glob_was_off" = true ] || set +f
  # bash >= 5.2 (patsub_replacement) would interpret & and \& inside the
  # substituted text; bash 3.2 keeps the quotes of a quoted replacement
  # literally. Turn the option off for the substitution and restore it.
  local psr_state
  psr_state="$(shopt -p patsub_replacement 2>/dev/null || true)"
  shopt -u patsub_replacement 2>/dev/null || true
  local out="$template"
  out="${out//\{base_branch\}/$base_branch}"
  out="${out//\{files\}/$quoted}"
  out="${out//\{pr_number\}/$pr_number}"
  [ -n "$psr_state" ] && eval "$psr_state"
  printf '%s' "$out"
}

# map_severity <reviewer_json_element> <native_severity>
# Exact lookup in severity_map, then pass-through for cc-review severities,
# otherwise prints nothing (the finding must be dropped).
map_severity() {
  local element="$1" native="$2"
  local mapped
  mapped="$(printf '%s' "$element" | jq -r --arg s "$native" '(.severity_map // {})[$s] // empty')"
  if [ -n "$mapped" ]; then
    printf '%s' "$mapped"
    return 0
  fi
  case " $CC_REVIEW_SEVERITIES " in
    *" $native "*) printf '%s' "$native" ;;
    *) printf '' ;;
  esac
}

# apply_config_enablement <reviewers_json> <reviewers_config_json>
# <reviewers_config_json> is the merged config's reviewers map ({} or empty when
# absent; see resolve_config_reviewers_json). A ready entry becomes disabled
# (reason "disabled") when its config value is false, or when the config has
# no key for it and its frontmatter `enabled` is false (FR-013). Every other
# status, including an invalid entry sharing the name, is left untouched.
apply_config_enablement() {
  local json="$1" cfg="${2:-}"
  [ -n "$cfg" ] || cfg='{}'
  printf '%s' "$json" | jq --argjson cfg "$cfg" '
    ($cfg | if type == "object" then . else {} end) as $c
    | map(. as $e
        | if $e.status == "ready" then
            (if ($c | has($e.name)) then $c[$e.name] else $e.enabled end) as $v
            | if $v == false or $v == "false" then .status = "disabled" | .reason = "disabled" else . end
          else . end)'
}

# apply_cli_selection <reviewers_json> <only_csv> <no_csv> <external_flag>
# external_flag is "", "on" or "off". Prints the updated JSON. Returns 1 with an
# error on stderr for unknown names, an invalid --only name, or when
# --only/--no-/--no-external leave no reviewer. A --no-<name> for an invalid
# reviewer only warns: there is nothing to disable (FR-010).
apply_cli_selection() {
  local json="$1" only_csv="${2:-}" no_csv="${3:-}" external_flag="${4:-}"
  local name discovered
  # Tolerate "a, b" and trailing commas: whitespace is never part of a name.
  only_csv="${only_csv//[[:space:]]/}"
  no_csv="${no_csv//[[:space:]]/}"
  # An invalid entry can share its name with the valid one it failed to
  # override; list each name once, in discovery order.
  discovered="$(printf '%s' "$json" | jq -r 'reduce .[].name as $n ([]; if any(.[]; . == $n) then . else . + [$n] end) | join(", ")')"

  local flag
  for flag in only no; do
    local csv="$only_csv"
    [ "$flag" = no ] && csv="$no_csv"
    for name in ${csv//,/ }; do
      [ -z "$name" ] && continue
      if ! printf '%s' "$json" | jq -e --arg n "$name" 'any(.[]; .name == $n)' >/dev/null; then
        printf 'Error: unknown reviewer '"'"'%s'"'"'. Discovered reviewers: %s\n' "$name" "$discovered" >&2
        return 1
      fi
      if ! printf '%s' "$json" | jq -e --arg n "$name" 'any(.[]; .name == $n and .status != "invalid")' >/dev/null; then
        local why
        why="$(printf '%s' "$json" | jq -r --arg n "$name" 'first(.[] | select(.name == $n) | .reason // "invalid")')"
        if [ "$flag" = only ]; then
          printf 'Error: reviewer '"'"'%s'"'"' is invalid (%s); see the discovery warnings\n' "$name" "$why" >&2
          return 1
        fi
        _runtime_warn "--no-$name: reviewer '$name' is invalid ($why) and would not run anyway"
      fi
    done
  done

  if [ -n "$only_csv" ]; then
    local remaining
    # "<after --no->:<after --no- and --no-external>"
    remaining="$(printf '%s' "$json" | jq -r --arg only "$only_csv" --arg no "$no_csv" --arg ext "$external_flag" '
      ($only | split(",") | map(select(length > 0))) as $o
      | ($no | split(",") | map(select(length > 0))) as $n
      | [.[] | select(.status != "invalid" and .kind == "command") | .name] as $cmd
      | [$o[] | select(. as $x | ($n | index($x)) == null)] as $left
      | "\($left | length):\([$left[] | select($ext != "off" or (. as $x | ($cmd | index($x)) == null))] | length)"')"
    if [ "${remaining%%:*}" = "0" ]; then
      echo "Error: no reviewers remain after --only/--no- selection" >&2
      return 1
    fi
    if [ "${remaining#*:}" = "0" ]; then
      echo "Error: no reviewers remain: every --only reviewer is a command reviewer and --no-external disables them" >&2
      return 1
    fi
  fi

  printf '%s' "$json" | jq --arg only "$only_csv" --arg no "$no_csv" --arg ext "$external_flag" '
    ($only | split(",") | map(select(length > 0))) as $o
    | ($no | split(",") | map(select(length > 0))) as $n
    | map(. as $e
        | if .status == "ready" or .status == "disabled" then
          (if ($o | length) > 0 then
             (if ($o | index($e.name)) != null then .status = "ready" | .reason = null
              else .status = "disabled" | .reason = "not in --only" end)
           else . end)
          | (if .kind == "command" and $ext == "off" then .status = "disabled" | .reason = "--no-external"
             elif .kind == "command" and $ext == "on" and .status == "disabled" and (($o | length) == 0 or ($o | index($e.name)) != null) then .status = "ready" | .reason = null
             else . end)
          | (if ($n | index($e.name)) != null then .status = "disabled" | .reason = ("--no-" + $e.name) else . end)
        else . end)'
}

# _runtime_reason <prefix> <stderr_file>
# Prints "<prefix>", or "<prefix>: <last non-empty stderr line>" with terminal
# escape sequences and control characters removed and the line cut to
# CC_REVIEW_REASON_MAX characters.
_runtime_reason() {
  local prefix="$1" file="$2" line esc
  esc="$(printf '\033')"
  line="$(LC_ALL=C sed "s/${esc}\[[0-9;?]*[A-Za-z]//g" "$file" 2>/dev/null \
    | LC_ALL=C tr '\t' ' ' | LC_ALL=C tr -d '\000-\010\013-\037\177' \
    | awk -v max="$CC_REVIEW_REASON_MAX" '{ sub(/^ +/, ""); sub(/ +$/, "") } length($0) { l = $0 } END { print substr(l, 1, max) }')"
  if [ -n "$line" ]; then
    printf '%s: %s' "$prefix" "$line"
  else
    printf '%s' "$prefix"
  fi
}

# _runtime_detect <detect> <auth_check>
# Runs a command reviewer's detect and (when non-empty) auth_check under the
# CC_REVIEW_DETECT_TIMEOUT bound, with stdin closed. Prints nothing when both
# pass, otherwise the skip reason: "not available[: <stderr>]",
# "not authenticated[: <stderr>]", "detection timed out" or
# "authentication check timed out".
_runtime_detect() {
  local detect="$1" auth_check="$2" err rc=0 reason=""
  if ! err="$(mktemp "${TMPDIR:-/tmp}/cc-review-probe.XXXXXX")"; then
    printf 'not available: cannot create a temporary file'
    return 0
  fi
  run_with_timeout "$CC_REVIEW_DETECT_TIMEOUT" bash -c "$detect" </dev/null >/dev/null 2>"$err" || rc=$?
  if [ "$rc" -eq 124 ]; then
    reason="detection timed out"
  elif [ "$rc" -ne 0 ]; then
    reason="$(_runtime_reason "not available" "$err")"
  elif [ -n "$auth_check" ]; then
    run_with_timeout "$CC_REVIEW_DETECT_TIMEOUT" bash -c "$auth_check" </dev/null >/dev/null 2>"$err" || rc=$?
    if [ "$rc" -eq 124 ]; then
      reason="authentication check timed out"
    elif [ "$rc" -ne 0 ]; then
      reason="$(_runtime_reason "not authenticated" "$err")"
    fi
  fi
  rm -f "$err"
  printf '%s' "$reason"
}

# apply_detection <reviewers_json>
# Runs detect and auth_check for every kind: command entry that is still ready,
# that is, after config enablement and CLI selection, so disabled reviewers
# cost no probe. A failing probe moves the entry to skipped with the reason
# from _runtime_detect. No other entry is touched, so an untrusted or changed
# project reviewer (already skipped by discovery) never runs a probe.
apply_detection() {
  local json="$1" idx detect auth_check reason updates="{}"
  for idx in $(printf '%s' "$json" | jq -r 'to_entries[] | select(.value.status == "ready" and .value.kind == "command") | .key'); do
    detect="$(printf '%s' "$json" | jq -r --argjson i "$idx" '.[$i].command.detect')"
    auth_check="$(printf '%s' "$json" | jq -r --argjson i "$idx" '.[$i].command.auth_check // ""')"
    reason="$(_runtime_detect "$detect" "$auth_check")"
    [ -n "$reason" ] && updates="$(jq -cn --argjson u "$updates" --arg i "$idx" --arg r "$reason" '$u + {($i): $r}')"
  done
  printf '%s' "$json" | jq --argjson u "$updates" '
    to_entries
    | map((.key | tostring) as $k
        | .value
        | if $u[$k] != null then .status = "skipped" | .reason = $u[$k] else . end)'
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  if [ "${1:-}" = "helper" ]; then
    shift
    case "${1:-}" in
      run_with_timeout|substitute_invoke|map_severity|apply_config_enablement|apply_cli_selection|apply_detection) "$@"; exit $? ;;
    esac
  fi
  echo "Error: usage: reviewer-runtime.sh helper <function> [args...] (run_with_timeout, substitute_invoke, map_severity, apply_config_enablement, apply_cli_selection, apply_detection)" >&2
  exit 2
fi
