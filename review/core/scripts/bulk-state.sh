#!/usr/bin/env bash
# bulk-state.sh - Manage the state of a bulk review or triage run
#
# Usage:
#   bulk-state.sh init <command> <mode> <selector-json> <options-json> <owner> <repo> <gh-user>
#   bulk-state.sh find-unfinished <command> [<run-id>]
#   bulk-state.sh set-prs <run> <prs-json> <excluded-json>
#   bulk-state.sh pr-set <run> <n> <jq-assignment>...
#   bulk-state.sh pr-get <run> <n> [<jq-path>]
#   bulk-state.sh record <run> <n> pending_push|pushed_sha|review_id <value>
#   bulk-state.sh record <run> <n> reply <comment_id> <reply_id>
#   bulk-state.sh record <run> <n> resolved <thread_id>
#   bulk-state.sh set-status <run> <status>
#   bulk-state.sh reanalyze <run> <n>
#   bulk-state.sh open-prs <run>
#   bulk-state.sh finish <run>
#   bulk-state.sh abandon <run>
#   bulk-state.sh resume-plan <run> <current-heads-json>
#   bulk-state.sh render <run>
#   bulk-state.sh validate <run>
#   bulk-state.sh summary <run>
#
# State root: $CC_REVIEW_BULK_DIR (default <git toplevel>/.cc-review/bulk).
# Each run lives in <root>/<run-id>/ with state.json (source of truth),
# state.md (rendered after every change) and summary.md.

set -euo pipefail

SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RUN_STATUSES="selecting analyzing deciding applying finished paused abandoned"
PR_STATUSES="pending analyzing analyzed applying failed stale cannot-push partially-applied actioned skipped closed"
RUN_ID_PATTERN='^[0-9]{8}-[0-9]{6}-(review|triage)(-[0-9]+)?$'
# A PR whose attempts failed this often (counted across resumes) is not
# retried; it stays failed and counts as finished for the run (FR-028)
MAX_FAILED_ATTEMPTS=3
# A head that moves between analysis and decision is analyzed again this
# often; the next move makes the PR stale (FR-030)
MAX_REANALYSES=1

# jq definitions shared by every filter that needs them:
#   terminal  the PR is finished for this run (nothing is retried or applied)
#   reset     back to pending for a new analysis; the recorded replies and
#             resolutions stay (dedup for the next apply), the push does not
#             (a new analysis prepares a new commit to push)
#   acted     the PR has recorded sub-actions
#   to_apply  the PR has a decision that is not fully applied yet
JQ_DEFS="
  def terminal: .status == \"actioned\" or .status == \"skipped\" or .status == \"stale\"
    or .status == \"cannot-push\" or .status == \"closed\"
    or (.status == \"failed\" and (.failed_attempts // 0) >= $MAX_FAILED_ATTEMPTS);
  def reset: .status = \"pending\" | .reason = null | .analyzed_head = null | .expected_head = null
    | .pending_push = null | .actions.pushed_sha = null
    | .worktree = null | .counts = null | .report = null | .proposed = null
    | .decision = null | del(.fixable) | .flags = ((.flags // []) - [\"local-unpushed\"]);
  def acted: .actions.pushed_sha != null or .actions.review_id != null
    or (.actions.replies | length) > 0 or (.actions.resolved | length) > 0;
  def to_apply: .decision != null
    and (.status == \"analyzed\" or .status == \"applying\" or .status == \"partially-applied\");
"

_TMPFILES=()
_cleanup_tmp() { rm -f ${_TMPFILES[@]+"${_TMPFILES[@]}"}; }
trap _cleanup_tmp EXIT

now_iso() {
  date -u +%Y-%m-%dT%H:%M:%SZ
}

state_root() {
  if [ -n "${CC_REVIEW_BULK_DIR:-}" ]; then
    printf '%s' "$CC_REVIEW_BULK_DIR"
    return
  fi
  local top
  top=$(git rev-parse --show-toplevel 2>/dev/null) || {
    echo "Error: not inside a git repository (set CC_REVIEW_BULK_DIR)" >&2; exit 1
  }
  printf '%s/.cc-review/bulk' "$top"
}

# run_dir <run>: the run's directory; the run must exist
run_dir() {
  local run="$1" dir
  [[ "$run" =~ $RUN_ID_PATTERN ]] || { echo "Error: invalid run id '$run'" >&2; exit 2; }
  dir="$(state_root)/$run"
  [ -f "$dir/state.json" ] || { echo "Error: no bulk run '$run' in $(state_root)" >&2; exit 1; }
  printf '%s' "$dir"
}

require_pr_number() {
  [[ "$1" =~ ^[0-9]+$ ]] || { echo "Error: PR number must be a positive integer, got '$1'" >&2; exit 2; }
}

in_list() {
  case " $2 " in *" $1 "*) return 0 ;; esac
  return 1
}

# check_state <file> <name>: prints one "Error: invalid bulk state" line per
# problem and fails when the file is not a valid BulkRun.
check_state() {
  local file="$1" name="$2" problems
  if ! problems=$(jq -r --arg rs "$RUN_STATUSES" --arg ps "$PR_STATUSES" '
      ($rs | split(" ")) as $run_statuses | ($ps | split(" ")) as $pr_statuses
      | def check(c; msg): if c then empty else msg end;
      if type != "object" then "root is not an object" else
        check(.version == 1; "version must be 1"),
        check((.run_id | type) == "string"; "run_id is missing"),
        check(.command == "review" or .command == "triage"; "command must be review or triage"),
        check(.mode == "deferred" or .mode == "unattended"; "mode must be deferred or unattended"),
        check((.selector | type) == "object"; "selector must be an object"),
        check((.options | type) == "array"; "options must be an array"),
        check((.repo | type) == "object"; "repo must be an object"),
        check((.gh_user | type) == "string"; "gh_user is missing"),
        check(.status as $s | $run_statuses | index($s); "status \(.status | tojson) is not a run status"),
        check((.excluded | type) == "array"; "excluded must be an array"),
        if (.prs | type) != "array" then "prs must be an array" else
          (.prs | to_entries[] | .key as $i | .value
            | check((.number | type) == "number"; "prs[\($i)].number must be a number"),
              check(.status as $s | $pr_statuses | index($s); "prs[\($i)].status \(.status | tojson) is not a PR status"),
              check((.dir | type) == "string"; "prs[\($i)].dir is missing"),
              check((.actions | type) == "object"; "prs[\($i)].actions must be an object"))
        end
      end' "$file" 2>&1); then
    echo "Error: invalid bulk state $name: not valid JSON ($problems)" >&2
    return 1
  fi
  if [ -n "$problems" ]; then
    printf '%s\n' "$problems" | sed "s|^|Error: invalid bulk state $name: |" >&2
    return 1
  fi
}

# update <run> <jq-filter> [jq args...]: applies the filter to state.json,
# stamps updated_at, validates the result and only then replaces the file.
update() {
  local run="$1" filter="$2"; shift 2
  local dir file tmp err
  dir=$(run_dir "$run")
  file="$dir/state.json"
  tmp=$(mktemp "$dir/.state.XXXXXX"); _TMPFILES+=("$tmp")
  if ! err=$(jq "$@" --arg now "$(now_iso)" "$filter | .updated_at = \$now" "$file" 2>&1 >"$tmp"); then
    echo "Error: cannot update $file: $err" >&2
    exit 1
  fi
  check_state "$tmp" "$file" || exit 1
  mv "$tmp" "$file"
  render_md "$dir"
}

# update_pr <run> <n> <jq-filter> [jq args...]: applies the filter to one PR entry
update_pr() {
  local run="$1" n="$2" filter="$3"; shift 3
  local dir
  dir=$(run_dir "$run")
  jq -e --argjson n "$n" 'any(.prs[]; .number == $n)' "$dir/state.json" >/dev/null 2>&1 || {
    check_state "$dir/state.json" "$dir/state.json" || exit 1
    echo "Error: no PR #$n in run $run" >&2; exit 1
  }
  update "$run" ".prs |= map(if .number == \$n then ($filter) else . end)" --argjson n "$n" "$@"
}

render_md() {
  local dir="$1" tmp
  tmp=$(mktemp "$dir/.state-md.XXXXXX"); _TMPFILES+=("$tmp")
  jq -r '
    def cell: tostring | gsub("\\|"; "\\|") | gsub("\n"; " ");
    def dash: if . == null or . == "" or . == [] then "-" else . end;
    def counts: if . == null then "-"
      elif has("critical") then "\(.critical)/\(.important)/\(.minor)/\(.notable)"
      else "\(.bot_valid)/\(.bot_rejected)/\(.deferred)/\(.human)" end;
    "# Bulk \(.command) run \(.run_id)",
    "",
    "- Status: \(.status)",
    "- Mode: \(.mode)",
    "- Selector: \(.selector.kind)\(if .selector.query then " `\(.selector.query)`" else "" end) (limit \(.selector.limit))",
    "- Options: \(if (.options | length) > 0 then (.options | join(" ")) else "none" end)",
    "- Repository: \(.repo.owner)/\(.repo.name)",
    "- Updated: \(.updated_at)",
    "",
    "Counts are \(if .command == "review" then "Critical/Important/Minor/Notable" else "valid/rejected/deferred/human" end).",
    "",
    "| PR | Title | Author | Status | Counts | Proposed | Decision | Reason | Report |",
    "|---|---|---|---|---|---|---|---|---|",
    (.prs[] | "| #\(.number) | \(.title | cell) | \(.author | cell) | \(.status) | \(.counts | counts) | \(.proposed | dash | cell) | \(.decision | if . == null then "-" else join(", ") end) | \(.reason | dash | cell) | \(.report | dash | cell) |"),
    "",
    "## Excluded",
    "",
    (if (.excluded | length) == 0 then "None." else
      ("| PR | Title | Reason |", "|---|---|---|",
       (.excluded[] | "| #\(.number) | \(.title | cell) | \(.reason) |")) end)
  ' "$dir/state.json" > "$tmp"
  mv "$tmp" "$dir/state.md"
}

do_init() {
  [ $# -eq 7 ] || { echo "Usage: bulk-state.sh init <command> <mode> <selector-json> <options-json> <owner> <repo> <gh-user>" >&2; exit 2; }
  local command="$1" mode="$2" selector="$3" options="$4" owner="$5" repo="$6" gh_user="$7"
  in_list "$command" "review triage" || { echo "Error: command must be review or triage, got '$command'" >&2; exit 2; }
  in_list "$mode" "deferred unattended" || { echo "Error: mode must be deferred or unattended, got '$mode'" >&2; exit 2; }
  printf '%s' "$selector" | jq -e 'type == "object"' >/dev/null 2>&1 || { echo "Error: selector must be a JSON object" >&2; exit 2; }
  printf '%s' "$options" | jq -e 'type == "array"' >/dev/null 2>&1 || { echo "Error: options must be a JSON array" >&2; exit 2; }
  [ -n "$owner" ] && [ -n "$repo" ] && [ -n "$gh_user" ] || { echo "Error: owner, repo and gh-user must be non-empty" >&2; exit 2; }

  local root base run dir n=1 repo_root
  root=$(state_root)
  mkdir -p "$root"
  [ -f "$root/.gitignore" ] || printf '*\n' > "$root/.gitignore"
  # mkdir without -p fails when the id is taken, so a run in the same second
  # gets a numeric suffix
  base="$(date -u +%Y%m%d-%H%M%S)-$command"
  run="$base"
  while ! mkdir "$root/$run" 2>/dev/null; do
    # Any failure other than "id taken" (read-only root, full disk) is fatal
    [ -e "$root/$run" ] || { echo "Error: cannot create run directory $root/$run" >&2; exit 1; }
    n=$((n + 1))
    run="$base-$n"
  done
  dir="$root/$run"
  repo_root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
  jq -n --arg id "$run" --arg cmd "$command" --arg mode "$mode" \
    --argjson selector "$selector" --argjson options "$options" \
    --arg owner "$owner" --arg name "$repo" --arg root "$repo_root" \
    --arg user "$gh_user" --arg now "$(now_iso)" \
    '{version: 1, run_id: $id, command: $cmd, mode: $mode, selector: $selector,
      options: $options, repo: {owner: $owner, name: $name, root: $root},
      gh_user: $user, status: "selecting", created_at: $now, updated_at: $now,
      prs: [], excluded: []}' > "$dir/state.json"
  render_md "$dir"
  echo "$run"
}

do_find_unfinished() {
  [ $# -ge 1 ] && [ $# -le 2 ] || { echo "Usage: bulk-state.sh find-unfinished <command> [<run-id>]" >&2; exit 2; }
  local command="$1" wanted="${2:-}" root d run line runs=""
  in_list "$command" "review triage" || { echo "Error: command must be review or triage, got '$command'" >&2; exit 2; }
  root=$(state_root)
  if [ -d "$root" ]; then
    for d in "$root"/*/; do
      [ -f "$d/state.json" ] || continue
      run=$(basename "$d")
      [[ "$run" =~ ^[0-9]{8}-[0-9]{6}-${command}(-[0-9]+)?$ ]] || continue
      # An unreadable state still counts as unfinished, so resume reports it
      # through validate instead of silently starting over
      if line=$(jq -r 'select(.status != "finished" and .status != "abandoned") | .updated_at // "0"' "$d/state.json" 2>/dev/null); then
        [ -n "$line" ] || continue
      else
        line=""
      fi
      runs+="$line	$run"$'\n'
    done
  fi
  runs=$(printf '%s' "$runs" | sort -r | cut -f2)
  if [ -z "$wanted" ]; then
    [ -n "$runs" ] && printf '%s\n' "$runs"
    return 0
  fi
  if printf '%s\n' "$runs" | grep -qxF -- "$wanted"; then
    echo "$wanted"
    return 0
  fi
  echo "Error: no unfinished $command run '$wanted'; unfinished runs: $(if [ -n "$runs" ]; then printf '%s' "$runs" | paste -sd, - | sed 's/,/, /g'; else echo none; fi)" >&2
  exit 1
}

do_set_prs() {
  [ $# -eq 3 ] || { echo "Usage: bulk-state.sh set-prs <run> <prs-json> <excluded-json>" >&2; exit 2; }
  local run="$1" prs="$2" excluded="$3" dir n
  printf '%s' "$prs" | jq -e 'type == "array"' >/dev/null 2>&1 || { echo "Error: prs must be a JSON array" >&2; exit 2; }
  printf '%s' "$excluded" | jq -e 'type == "array"' >/dev/null 2>&1 || { echo "Error: excluded must be a JSON array" >&2; exit 2; }
  dir=$(run_dir "$run")
  update "$run" '
    .status = "analyzing"
    | .excluded = $excluded
    | .prs = ($prs | map(. + {
        analyzed_head: null, expected_head: null, pending_push: null,
        status: "pending", reason: null, dir: "pr-\(.number)", worktree: null,
        counts: null, report: null,
        flags: (if .is_cross_repo then ["cross-repo"] else [] end),
        proposed: null, decision: null, failed_attempts: 0, reanalyses: 0,
        actions: {pushed_sha: null, review_id: null, replies: {}, resolved: []}
      }))' --argjson prs "$prs" --argjson excluded "$excluded"
  for n in $(printf '%s' "$prs" | jq -r '.[].number'); do
    mkdir -p "$dir/pr-$n"
  done
  echo "OK"
}

do_pr_set() {
  [ $# -ge 3 ] || { echo "Usage: bulk-state.sh pr-set <run> <n> <jq-assignment>..." >&2; exit 2; }
  local run="$1" n="$2" filter="" a
  shift 2
  require_pr_number "$n"
  for a in "$@"; do
    filter+="${filter:+ | }($a)"
  done
  # A PR with recorded actions is never failed: a resume re-analyzes failed
  # PRs, which would forget what was already pushed or posted. Every new
  # failure counts as an attempt; the last allowed one says so in the reason.
  filter="$JQ_DEFS . as \$before | $filter"
  filter+=' | if .status == "failed" and acted then .status = "partially-applied" else . end
    | if .status == "failed" and $before.status != "failed" then
        .failed_attempts = ((.failed_attempts // 0) + 1)
        | if terminal then .reason = "\(.reason // "failed"); not retried after \(.failed_attempts) failed attempts" else . end
      else . end'
  update_pr "$run" "$n" "$filter"
  echo "OK"
}

do_pr_get() {
  [ $# -ge 2 ] && [ $# -le 3 ] || { echo "Usage: bulk-state.sh pr-get <run> <n> [<jq-path>]" >&2; exit 2; }
  local run="$1" n="$2" path="${3:-}" dir
  require_pr_number "$n"
  dir=$(run_dir "$run")
  jq -e --argjson n "$n" 'any(.prs[]; .number == $n)' "$dir/state.json" >/dev/null 2>&1 || {
    echo "Error: no PR #$n in run $run" >&2; exit 1
  }
  if [ -n "$path" ]; then
    jq -r --argjson n "$n" ".prs[] | select(.number == \$n) | $path" "$dir/state.json"
  else
    jq --argjson n "$n" '.prs[] | select(.number == $n)' "$dir/state.json"
  fi
}

do_record() {
  local usage="Usage: bulk-state.sh record <run> <n> {pending_push <sha>|pushed_sha <sha>|review_id <id>|reply <comment_id> <reply_id>|resolved <thread_id>}"
  [ $# -ge 4 ] || { echo "$usage" >&2; exit 2; }
  local run="$1" n="$2" form="$3"
  shift 3
  require_pr_number "$n"
  case "$form" in
    pending_push)
      [ $# -eq 1 ] || { echo "$usage" >&2; exit 2; }
      update_pr "$run" "$n" '.pending_push = $v' --arg v "$1" ;;
    pushed_sha)
      [ $# -eq 1 ] || { echo "$usage" >&2; exit 2; }
      update_pr "$run" "$n" '.actions.pushed_sha = $v | .pending_push = null | .expected_head = $v' --arg v "$1" ;;
    review_id)
      [ $# -eq 1 ] || { echo "$usage" >&2; exit 2; }
      update_pr "$run" "$n" '.actions.review_id = ($v | tonumber? // $v)' --arg v "$1" ;;
    reply)
      [ $# -eq 2 ] || { echo "$usage" >&2; exit 2; }
      update_pr "$run" "$n" '.actions.replies[$k] = ($v | tonumber? // $v)' --arg k "$1" --arg v "$2" ;;
    resolved)
      [ $# -eq 1 ] || { echo "$usage" >&2; exit 2; }
      update_pr "$run" "$n" 'if any(.actions.resolved[]; . == $v) then . else .actions.resolved += [$v] end' --arg v "$1" ;;
    *)
      echo "$usage" >&2; exit 2 ;;
  esac
  echo "OK"
}

# intact <dir> <command> <pr-json>: true when the prepared work of an analyzed
# or applying PR is still on disk: its report, its kept worktree, and (triage)
# its plan with the prepared commit in that worktree unless it was pushed
intact() {
  local dir="$1" command="$2" pr="$3" wt report plan prepared pushed
  wt=$(printf '%s' "$pr" | jq -r '.worktree // ""')
  report=$(printf '%s' "$pr" | jq -r '.report // ""')
  pushed=$(printf '%s' "$pr" | jq -r '.actions.pushed_sha // ""')
  [ -z "$wt" ] || [ -d "$wt" ] || return 1
  [ -z "$report" ] || [ -s "$dir/$report" ] || return 1
  if [ "$command" = triage ]; then
    plan="$dir/$(printf '%s' "$pr" | jq -r '.dir')/triage-plan.json"
    jq -e 'type == "object"' "$plan" >/dev/null 2>&1 || return 1
    prepared=$(jq -r '.prepared_commit // ""' "$plan")
    if [ -n "$prepared" ] && [ -z "$pushed" ]; then
      [ -n "$wt" ] && [ -d "$wt" ] || return 1
      [ "$(git -C "$wt" rev-parse HEAD 2>/dev/null)" = "$prepared" ] || return 1
    fi
  fi
  return 0
}

# resume-plan <run> <current-heads-json>: applies the resume transitions
# (bulk.md Resume) to every PR, given the current head per PR number
# ({"<n>": "<sha>"}; a missing or null head is unknown and changes nothing),
# writes them back and prints {reanalyze, keep, apply}.
do_resume_plan() {
  [ $# -eq 2 ] || { echo "Usage: bulk-state.sh resume-plan <run> <current-heads-json>" >&2; exit 2; }
  local run="$1" heads="$2" dir state command n pr intact_json="{}" ok
  printf '%s' "$heads" | jq -e 'type == "object"' >/dev/null 2>&1 || { echo "Error: current heads must be a JSON object" >&2; exit 2; }
  dir=$(run_dir "$run")
  state="$dir/state.json"
  check_state "$state" "$state" || exit 1
  command=$(jq -r '.command' "$state")
  for n in $(jq -r '.prs[] | select(.status == "analyzed" or .status == "applying" or .status == "partially-applied") | .number' "$state"); do
    pr=$(jq -c --argjson n "$n" '.prs[] | select(.number == $n)' "$state")
    ok=false
    if intact "$dir" "$command" "$pr"; then ok=true; fi
    intact_json=$(printf '%s' "$intact_json" | jq -c --arg n "$n" --argjson ok "$ok" '.[$n] = $ok')
  done
  # A failed PR is retried until its attempts reach MAX_FAILED_ATTEMPTS
  # (terminal from then on)
  update "$run" "$JQ_DEFS"'
    .prs |= map(
      # "review findings" is not a decision of its own: an interrupted
      # drill-down leaves the PR undecided
      (if .decision == ["review-findings"] then .decision = null else . end)
      | ($heads[.number | tostring] // null) as $h
      | ($intact[.number | tostring] != false) as $ok
      | if terminal then .
        elif .status == "pending" or .status == "analyzing" or .status == "failed" then reset
        elif .status == "analyzed" then
          if ($h != null and $h != .analyzed_head) or ($ok | not) then reset else . end
        else
          # applying or partially-applied: a remote at the pending sha means
          # the push completed before the interruption
          if $h != null and .pending_push != null and $h == .pending_push then
            .actions.pushed_sha = .pending_push | .expected_head = .pending_push | .pending_push = null
          elif $h != null and $h != .expected_head then
            .status = "stale" | .pending_push = null
            | .reason = "stale, re-run needed: the head moved before the run was resumed"
          elif ($ok | not) and (acted | not) then reset
          else . end
        end)
    | .status = (if any(.prs[]; .status == "pending") then "analyzing"
        elif any(.prs[]; .status == "analyzed" and .decision == null) then "deciding"
        elif any(.prs[]; to_apply) then "applying"
        else .status end)' --argjson heads "$heads" --argjson intact "$intact_json"
  jq -c "$JQ_DEFS"'{
    reanalyze: [.prs[] | select(.status == "pending") | .number],
    apply: [.prs[] | select(to_apply) | .number],
    keep: [.prs[] | select(.status != "pending" and (to_apply | not)) | .number]
  }' "$state"
}

do_set_status() {
  [ $# -eq 2 ] || { echo "Usage: bulk-state.sh set-status <run> <status>" >&2; exit 2; }
  in_list "$2" "$RUN_STATUSES" || { echo "Error: run status must be one of: $RUN_STATUSES" >&2; exit 2; }
  update "$1" '.status = $s' --arg s "$2"
  echo "OK"
}

# reanalyze <run> <n>: an analyzed PR whose head moved before the decision
# step goes back to pending for one more analysis in this run (REANALYZE);
# once MAX_REANALYSES is reached it becomes stale instead (STALE)
do_reanalyze() {
  [ $# -eq 2 ] || { echo "Usage: bulk-state.sh reanalyze <run> <n>" >&2; exit 2; }
  local run="$1" n="$2" count
  require_pr_number "$n"
  count=$(do_pr_get "$run" "$n" '.reanalyses // 0')
  if [ "$count" -lt "$MAX_REANALYSES" ]; then
    update_pr "$run" "$n" "$JQ_DEFS reset | .reanalyses = ((.reanalyses // 0) + 1)"
    echo "REANALYZE"
  else
    update_pr "$run" "$n" '.status = "stale" | .proposed = null | .worktree = null
      | .reason = "stale, re-run needed: the head moved again after it was analyzed a second time"'
    echo "STALE"
  fi
}

# abandon <run>: marks the run abandoned (its state stays on disk), removes
# the worktrees it kept and records them, and rewrites summary.md
do_abandon() {
  [ $# -eq 1 ] || { echo "Usage: bulk-state.sh abandon <run>" >&2; exit 2; }
  local run="$1" dir root n wt removed=()
  dir=$(run_dir "$run")
  check_state "$dir/state.json" "$dir/state.json" || exit 1
  root=$(jq -r '.repo.root' "$dir/state.json")
  while IFS=$'\t' read -r n wt; do
    [ -n "$n" ] || continue
    if (cd "$root" && "$SCRIPT_DIR/pr-worktree.sh" remove "$wt" >/dev/null); then
      update_pr "$run" "$n" '.worktree = null'
      removed+=("$wt")
    else
      echo "Warning: could not remove the worktree of #$n at $wt" >&2
    fi
  done < <(jq -r '.prs[] | select(.worktree != null) | "\(.number)\t\(.worktree)"' "$dir/state.json")
  update "$run" '.status = "abandoned" | .removed_worktrees = ((.removed_worktrees // []) + $removed)' \
    --argjson removed "$(printf '%s\n' ${removed[@]+"${removed[@]}"} | jq -Rnc '[inputs | select(length > 0)]')"
  do_summary "$run" >/dev/null
  echo "OK removed=${#removed[@]}"
}

# open-prs <run>: the numbers of the PRs that are not finished for the run
do_open_prs() {
  [ $# -eq 1 ] || { echo "Usage: bulk-state.sh open-prs <run>" >&2; exit 2; }
  local dir
  dir=$(run_dir "$1")
  check_state "$dir/state.json" "$dir/state.json" || exit 1
  jq -r "$JQ_DEFS"'.prs[] | select(terminal | not) | .number' "$dir/state.json"
}

# finish <run>: marks the run finished when it is not paused (or abandoned)
# and every PR is finished for the run; prints the run status
do_finish() {
  [ $# -eq 1 ] || { echo "Usage: bulk-state.sh finish <run>" >&2; exit 2; }
  local dir
  dir=$(run_dir "$1")
  check_state "$dir/state.json" "$dir/state.json" || exit 1
  if jq -e "$JQ_DEFS"'.status != "paused" and .status != "finished" and .status != "abandoned" and (.prs | all(terminal))' "$dir/state.json" >/dev/null; then
    update "$1" '.status = "finished"'
  fi
  jq -r '.status' "$dir/state.json"
}

do_render() {
  [ $# -eq 1 ] || { echo "Usage: bulk-state.sh render <run>" >&2; exit 2; }
  local dir
  dir=$(run_dir "$1")
  check_state "$dir/state.json" "$dir/state.json" || exit 1
  render_md "$dir"
  echo "OK"
}

do_validate() {
  [ $# -eq 1 ] || { echo "Usage: bulk-state.sh validate <run>" >&2; exit 2; }
  local dir
  dir=$(run_dir "$1")
  check_state "$dir/state.json" "$dir/state.json" || exit 1
  echo "OK"
}

do_summary() {
  [ $# -eq 1 ] || { echo "Usage: bulk-state.sh summary <run>" >&2; exit 2; }
  local dir state tmp n plan lines attention="" ci=""
  dir=$(run_dir "$1")
  state="$dir/state.json"
  check_state "$state" "$state" || exit 1
  tmp=$(mktemp "$dir/.summary.XXXXXX"); _TMPFILES+=("$tmp")
  jq -r '
    def cell: tostring | gsub("\\|"; "\\|") | gsub("\n"; " ");
    def dash: if . == null or . == "" or . == [] then "-" else . end;
    "# Bulk \(.command) summary: \(.run_id)",
    "",
    "- Status: \(.status)",
    "- Mode: \(.mode)",
    "- Selector: \(.selector.kind)\(if .selector.query then " `\(.selector.query)`" else "" end) (limit \(.selector.limit))",
    "",
    "## Selected",
    "",
    (.repo as $r
     | if (.prs | length) == 0 then "None." else
      ("| PR | Title | Outcome | Decision | Done | Reason |", "|---|---|---|---|---|---|",
       (.prs[] | . as $p
        | [(if .actions.review_id != null then "review https://github.com/\($r.owner)/\($r.name)/pull/\(.number)#pullrequestreview-\(.actions.review_id)" else empty end),
           (if .actions.pushed_sha != null then "pushed \(.actions.pushed_sha[:7])" else empty end),
           (if (.actions.replies | length) > 0 then "\(.actions.replies | length) replies" else empty end),
           (if (.actions.resolved | length) > 0 then "\(.actions.resolved | length) threads resolved" else empty end)]
        | join("; ") as $done
        | "| #\($p.number) | \($p.title | cell) | \($p.status) | \($p.decision | if . == null then "-" else join(", ") end) | \($done | dash) | \($p.reason | dash | cell) |")) end),
    "",
    "## Excluded",
    "",
    (if (.excluded | length) == 0 then "None." else
      ("| PR | Title | Reason |", "|---|---|---|",
       (.excluded[] | "| #\(.number) | \(.title | cell) | \(.reason) |")) end),
    "",
    "## Kept worktrees",
    "",
    ([.prs[] | select(.worktree != null) | "- #\(.number): \(.worktree)"] | if length == 0 then "None." else .[] end),
    (if (.removed_worktrees // []) | length > 0 then
      ("", "## Removed worktrees", "", "The run was abandoned; its kept worktrees were removed:", "",
       (.removed_worktrees[] | "- \(.)")) else empty end)
  ' "$state" > "$tmp"
  if [ "$(jq -r '.command' "$state")" = triage ]; then
    # Human comments without a decision were left untouched (unattended mode,
    # or a stopped decision step)
    for n in $(jq -r '.prs[].number' "$state"); do
      plan="$dir/pr-$n/triage-plan.json"
      [ -f "$plan" ] || continue
      lines=$(jq -r --argjson n "$n" '.human[]? | select(.decision == null)
        | "- #\($n) \(.path):\(.line) (@\(.author)): \(.text | split("\n")[0])"' "$plan" 2>/dev/null || true)
      if [ -n "$lines" ]; then attention+="$lines"$'\n'; fi
    done
    ci=$(jq -r '.prs[] | select(.actions.pushed_sha != null)
      | "- #\(.number): CI not checked; run `/triage --pr \(.number)` for CI repair"' "$state")
    {
      printf '\n## Needs attention\n\n'
      if [ -n "$attention" ]; then printf '%s' "$attention"; else echo "None."; fi
      printf '\n## CI\n\n'
      if [ -n "$ci" ]; then printf '%s\n' "$ci"; else echo "No PR was pushed."; fi
    } >> "$tmp"
  fi
  mv "$tmp" "$dir/summary.md"
  echo "$dir/summary.md"
}

case "${1:-}" in
  init)
    shift; do_init "$@" ;;
  find-unfinished)
    shift; do_find_unfinished "$@" ;;
  set-prs)
    shift; do_set_prs "$@" ;;
  pr-set)
    shift; do_pr_set "$@" ;;
  pr-get)
    shift; do_pr_get "$@" ;;
  record)
    shift; do_record "$@" ;;
  set-status)
    shift; do_set_status "$@" ;;
  reanalyze)
    shift; do_reanalyze "$@" ;;
  open-prs)
    shift; do_open_prs "$@" ;;
  finish)
    shift; do_finish "$@" ;;
  abandon)
    shift; do_abandon "$@" ;;
  render)
    shift; do_render "$@" ;;
  validate)
    shift; do_validate "$@" ;;
  summary)
    shift; do_summary "$@" ;;
  resume-plan)
    shift; do_resume_plan "$@" ;;
  *)
    echo "Usage: bulk-state.sh {init|find-unfinished|set-prs|pr-set|pr-get|record|set-status|reanalyze|open-prs|finish|abandon|resume-plan|render|validate|summary}" >&2
    exit 2 ;;
esac
