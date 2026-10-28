#!/usr/bin/env bash
# bulk-apply.sh - Apply the decided bulk actions that need no judgment
#
# Usage:
#   bulk-apply.sh head <run> <n>
#   bulk-apply.sh marker <run> <n>
#   bulk-apply.sh review-push <run> <n>
#   bulk-apply.sh triage <run> <n>
#
# Every completed sub-action is recorded in the run state the moment it
# completes, and an already recorded one is never repeated, so a resumed run
# can call these again safely. head changes nothing.
#
# Output (stdout, one line):
#   head         OK <sha> | MOVED <sha> | CLOSED <state>
#   marker       POSTED <id> | FOUND <id> | RECORDED <id> | STALE
#   review-push  PUSHED <sha> | UP-TO-DATE | STALE | DENIED
#   triage       ACTIONED ... | PARTIAL failed=<n> ... | STALE | DENIED ...
#                (DENIED: no push permission; the fixes stay unpushed, the
#                replies that do not depend on them are posted)
#
# triage uses the invoking repository's triage state ($TRIAGE_STATE_FILE,
# default <repo root>/.cc-review/.triage-state.json).
#
# Exit codes: 0 ok, 1 failure, 2 usage error, 75 hosting-service rate limit
# (stderr "Error: RATE_LIMITED").

set -euo pipefail

SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BULK_STATE="$SCRIPT_DIR/bulk-state.sh"
PR_WORKTREE="$SCRIPT_DIR/pr-worktree.sh"

_TMPFILES=()
_cleanup_tmp() { rm -f ${_TMPFILES[@]+"${_TMPFILES[@]}"}; }
trap _cleanup_tmp EXIT

tmpfile() {
  local f
  f=$(mktemp); _TMPFILES+=("$f")
  printf '%s' "$f"
}

# rate_limited and try
# shellcheck source=rate-limit.sh
. "$SCRIPT_DIR/rate-limit.sh"

# state_file <run>: the run's state.json, validated
state_file() {
  local root
  if [ -n "${CC_REVIEW_BULK_DIR:-}" ]; then
    root="$CC_REVIEW_BULK_DIR"
  else
    root="$(git rev-parse --show-toplevel)/.cc-review/bulk"
  fi
  "$BULK_STATE" validate "$1" >/dev/null || exit 1
  printf '%s/%s/state.json' "$root" "$1"
}

pr_field() {
  "$BULK_STATE" pr-get "$RUN" "$PR" "$1"
}

check_args() {
  [ $# -eq 3 ] || { echo "Usage: bulk-apply.sh $1 <run> <n>" >&2; exit 2; }
  [[ "$3" =~ ^[0-9]+$ ]] || { echo "Error: PR number must be a positive integer, got '$3'" >&2; exit 2; }
}

# The head check of bulk.md (FR-030), for the pre-decision refresh and before
# every push, post and marker: OK when the PR's head is the expected head (or
# a recorded pending push), MOVED when it is another commit, CLOSED <state>
# when the PR is no longer open. Right after this run pushed, GitHub may still
# report the pre-push head, so the branch tip of the PR's head repository
# decides then.
do_head() {
  check_args "$@"
  RUN="$2" PR="$3"
  local err out pr_state head expected pending pushed url branch tip
  state_file "$RUN" >/dev/null
  err=$(tmpfile); out=$(tmpfile)
  if ! try "$err" gh pr view "$PR" --json state,headRefOid > "$out"; then
    echo "Error: cannot read PR #$PR: $(tail -n 1 "$err")" >&2
    exit 1
  fi
  pr_state=$(jq -r '.state' "$out")
  head=$(jq -r '.headRefOid' "$out")
  if [ "$pr_state" != OPEN ]; then
    echo "CLOSED $(printf '%s' "$pr_state" | tr '[:upper:]' '[:lower:]')"
    return
  fi
  expected=$(pr_field '.expected_head // ""')
  pending=$(pr_field '.pending_push // ""')
  pushed=$(pr_field '.actions.pushed_sha // ""')
  if [ "$head" != "$expected" ] && { [ -n "$pushed" ] || [ -n "$pending" ]; }; then
    url=$(pr_field '.head_repo_url // ""')
    branch=$(pr_field '.head_ref // ""')
    tip=$(git ls-remote "$url" "refs/heads/$branch" 2>/dev/null | cut -f1) || tip=""
    if [ -n "$tip" ]; then head="$tip"; fi
  fi
  if [ "$head" = "$expected" ] || { [ -n "$pending" ] && [ "$head" = "$pending" ]; }; then
    echo "OK $head"
  else
    echo "MOVED $head"
  fi
}

# The no-findings marker (FR-021a): a short comment review on the analyzed
# head carrying this run's marker, so later runs see the PR as reviewed there
do_marker() {
  check_args "$@"
  RUN="$2" PR="$3"
  local state recorded owner repo head marker reviews err found body payload out rc=0 id
  local completion_file completion_input completion_result completion_text
  local candidate_file live_head fresh_threads fresh_complete fresh_outcomes refresh_input refreshed
  state=$(state_file "$RUN")
  recorded=$(pr_field '.actions.review_id // ""')
  if [ -n "$recorded" ]; then
    echo "RECORDED $recorded"
    return
  fi
  owner=$(jq -r '.repo.owner' "$state")
  repo=$(jq -r '.repo.name' "$state")
  head=$(pr_field '.expected_head // ""')
  [ -n "$head" ] || { echo "Error: PR #$PR has no expected head in run $RUN" >&2; exit 1; }
  marker="<!-- cc-review:run-id:$RUN/pr-$PR -->"
  # shellcheck source=platform.sh
  . "$SCRIPT_DIR/platform.sh"

  # A marker this run already posted (an interrupted earlier attempt) is
  # recorded instead of posted twice; only the user posts this run's markers
  reviews=$(tmpfile); err=$(tmpfile)
  if ! try "$err" fetch_reviews "$owner" "$repo" "$PR" > "$reviews"; then
    echo "Error: cannot read the reviews of PR #$PR: $(tail -n 1 "$err")" >&2
    exit 1
  fi
  found=$(jq -r --arg m "$marker" --arg me "$(jq -r '.gh_user' "$state")" \
    '[.[] | select(.author.login == $me and ((.body // "") | contains($m)))] | first | .databaseId // empty' "$reviews")
  if [ -n "$found" ]; then
    "$BULK_STATE" record "$RUN" "$PR" review_id "$found" >/dev/null
    echo "FOUND $found"
    return
  fi

  body=$(printf 'cc-review found no issues at `%s`.\n\n%s' "${head:0:7}" "$marker")
  completion_file="$(dirname "$state")/pr-$PR/scope/completion.json"
  if [ -f "$completion_file" ]; then
    candidate_file="$(dirname "$completion_file")/completion-input.json"
    if [ "$(jq -r '.complete' "$completion_file")" = true ]; then
      if [ -f "$candidate_file" ]; then
        live_head=$(do_head "$@") || return $?
        if [ "$live_head" != "OK $head" ]; then
          "$BULK_STATE" pr-set "$RUN" "$PR" '.status="stale"' \
            '.reason="PR changed before completion publication; re-analyze"' >/dev/null
          echo "STALE"; return
        fi
        fresh_threads=$(tmpfile); fresh_complete=true
        fetch_pr_threads "$PR" > "$fresh_threads" || fresh_complete=false
        if ! jq -e 'type == "array"' "$fresh_threads" >/dev/null 2>&1; then
          printf '[]\n' > "$fresh_threads"; fresh_complete=false
        fi
        fresh_outcomes="$(dirname "$completion_file")/outcomes.json"
        if [ ! -f "$fresh_outcomes" ]; then
          fresh_outcomes=$(tmpfile); printf '[]\n' > "$fresh_outcomes"
        fi
        refresh_input=$(tmpfile); refreshed=$(tmpfile)
        jq -n --slurpfile candidate "$candidate_file" --slurpfile threads "$fresh_threads" \
          --slurpfile outcomes "$fresh_outcomes" --arg head "$head" --argjson complete "$fresh_complete" \
          '{candidate:$candidate[0],outcomes:$outcomes[0],threads_snapshot:{
            identity:$candidate[0].scope.identity,head_oid:$head,threads:$threads[0],threads_complete:$complete}}' > "$refresh_input"
        python3 "$SCRIPT_DIR/review_scope.py" refresh --input "$refresh_input" > "$refreshed" || exit 1
        completion_file="$refreshed"
      else
        refreshed=$(tmpfile)
        printf '{"complete":false,"marker":""}\n' > "$refreshed"
        completion_file="$refreshed"
      fi
    fi
    completion_input=$(tmpfile); completion_result=$(tmpfile)
    jq -n --slurpfile completion "$completion_file" --arg user "$(jq -r '.gh_user' "$state")" \
      --arg repository "$owner/$repo" --argjson pr "$PR" --arg run "$RUN/pr-$PR" --arg head "$head" \
      '{completion:$completion[0],identity:{host:"github.com",repository:$repository,user:$user,pr:$pr},run_id:$run,head_oid:$head}' \
      > "$completion_input"
    python3 "$SCRIPT_DIR/review_scope.py" publication --input "$completion_input" > "$completion_result" || {
      echo "Error: saved completion evidence is invalid; re-analyze PR #$PR" >&2; exit 1;
    }
    completion_text=$(jq -r '.marker' "$completion_result")
    if [ "$(jq -r '.complete' "$completion_result")" != true ]; then
      body=$(printf 'cc-review could not complete all checks at `%s`.\n\n%s' "${head:0:7}" "$marker")
    fi
    body="$body
$completion_text"
  fi
  payload=$(tmpfile)
  jq -n --arg body "$body" --arg commit "$head" \
    '{body: $body, event: "COMMENT", commit_id: $commit, comments: []}' > "$payload"
  out=$(tmpfile)
  if [ -f "$completion_file" ]; then
    live_head=$(do_head "$@") || return $?
    if [ "$live_head" != "OK $head" ]; then
      "$BULK_STATE" pr-set "$RUN" "$PR" '.status="stale"' \
        '.reason="PR changed after thread refresh; re-analyze"' >/dev/null
      echo "STALE"; return
    fi
  fi
  # post_review merges gh's stderr into its output
  post_review "$owner" "$repo" "$PR" "$payload" > "$out" 2>"$err" || rc=$?
  if [ "$rc" -ne 0 ]; then
    if rate_limited "$out" "$err"; then
      echo "Error: RATE_LIMITED" >&2
      exit 75
    fi
    # GitHub rejects a commit_id that is no longer the PR's head line
    if grep -q '422' "$out" "$err" && grep -qi 'commit' "$out" "$err"; then
      "$BULK_STATE" pr-set "$RUN" "$PR" '.status="stale"' \
        '.reason="stale, re-run needed: the PR head moved; review not posted"' >/dev/null
      echo "STALE"
      return
    fi
    echo "Error: posting the marker review on PR #$PR failed: $(cat "$out" "$err" | tail -n 1)" >&2
    exit 1
  fi
  id=$(jq -r '.id // empty' "$out" 2>/dev/null || true)
  [ -n "$id" ] || { echo "Error: posting the marker review on PR #$PR returned no review id" >&2; exit 1; }
  "$BULK_STATE" record "$RUN" "$PR" review_id "$id" >/dev/null
  echo "POSTED $id"
}

# Pushes the fix commits of "apply fixes" from the PR's worktree. The sha is
# recorded as pending before the push, so an interruption between push and
# record is recognized on resume (the remote then equals the pending sha).
do_review_push() {
  check_args "$@"
  RUN="$2" PR="$3"
  local wt url branch expected head result rc=0
  state_file "$RUN" >/dev/null
  wt=$(pr_field '.worktree // ""')
  [ -n "$wt" ] && [ -d "$wt" ] || { echo "Error: PR #$PR has no worktree in run $RUN" >&2; exit 1; }
  url=$(pr_field '.head_repo_url // ""')
  branch=$(pr_field '.head_ref // ""')
  expected=$(pr_field '.expected_head // ""')
  [ -n "$url" ] && [ -n "$branch" ] && [ -n "$expected" ] || {
    echo "Error: PR #$PR lacks head_repo_url, head_ref or expected_head in run $RUN" >&2; exit 1
  }
  head=$(git -C "$wt" rev-parse HEAD)
  if [ "$head" = "$expected" ]; then
    echo "UP-TO-DATE"
    return
  fi
  "$BULK_STATE" record "$RUN" "$PR" pending_push "$head" >/dev/null
  result=$("$PR_WORKTREE" push "$wt" "$url" "$branch" "$expected") || rc=$?
  [ "$rc" -eq 75 ] && exit 75
  [ "$rc" -eq 0 ] || exit 1
  case "$result" in
    "PUSHED "*)
      "$BULK_STATE" record "$RUN" "$PR" pushed_sha "${result#PUSHED }" >/dev/null
      echo "$result" ;;
    STALE)
      "$BULK_STATE" pr-set "$RUN" "$PR" '.status="stale"' '.pending_push=null' \
        '.reason="stale, re-run needed: the PR branch moved; fixes not pushed"' >/dev/null
      echo "STALE" ;;
    DENIED)
      BRANCH="$branch" "$BULK_STATE" pr-set "$RUN" "$PR" '.status="cannot-push"' '.pending_push=null' \
        '.reason="cannot push to \(env.BRANCH): permission denied"' >/dev/null
      echo "DENIED" ;;
    *)
      echo "Error: unexpected push result for PR #$PR: $result" >&2
      exit 1 ;;
  esac
}

# pr_status <status> [<reason>]: the PR's status, with a reason or none
pr_status() {
  STATUS="$1" REASON="${2:-}" "$BULK_STATE" pr-set "$RUN" "$PR" '.status=env.STATUS' \
    '.reason=(if env.REASON == "" then null else env.REASON end)' >/dev/null
}

# triage_items <plan> <skip-accepted>: the replies to post, in order: bot
# replies, cc-review thread replies, then human comments the user approved or
# edited. Each item keeps the plan's comment id as its key.
triage_items() {
  jq -c --argjson skip "$2" '
    [(.replies // [])[] | {comment_id, thread_id, author, path, line, body, action, resolve: (.resolve // false)}]
    + [(.cc_review_threads // [])[] | select((.body // "") != "")
        | {comment_id, thread_id, author, path, line, body, action: (.action // "resolved"), resolve: (.resolve // false)}]
    + [(.human // [])[] | select(.decision == "approve" or .decision == "edit")
        | {comment_id, thread_id, author, path, line,
           body: ((.body // .draft // "")
             # signed, so a rerun recognizes the posted reply
             | if . == "" or contains("<!-- cc-review-triage") then . else . + "\n\n<!-- cc-review-triage -->" end),
           action: (if .decision == "edit" then "edited" else "approved" end), resolve: false}]
    | map(select((.body // "") != "" and (($skip | not) or .action != "accepted")))
    | .[]' "$1"
}

# thread_for <threads> <item>: the current thread of an item, found by its
# comment id, or (bots re-post their comments when a PR moves) by path, line
# and author. Prints {thread_id, comment_id, resolved, own_reply} or nothing.
# own_reply is a signed reply by the user posted since this run started (an
# interrupted attempt of this run); an older signed reply is an earlier
# exchange and does not stand in for a new reply.
thread_for() {
  jq -c --argjson item "$2" --arg me "$GH_USER" --arg since "$RUN_STARTED" '
    def bare: (. // "") | sub("\\[bot\\]$"; "");
    (map(select(any(.comments.nodes[]?; .databaseId == $item.comment_id))) | first)
    // (if $item.path == null then null else
         map(select(.path == $item.path and .line == $item.line
           and (.comments.nodes[0].author.login | bare) == ($item.author | bare))) | first end)
    | if . == null then empty else
        (.comments.nodes[0].databaseId) as $first
        | {thread_id: .id,
           comment_id: (if any(.comments.nodes[]?; .databaseId == $item.comment_id) then $item.comment_id else $first end),
           resolved: (.isResolved // false),
           own_reply: ([.comments.nodes[]? | select(.author.login == $me and ((.body // "") | contains("<!-- cc-review-triage"))
               and (.createdAt // "") >= $since)
             | .databaseId] | first)}
      end' "$1"
}

# reviewer_current_check <plan> <item> <pr-view-file> <thread-file>
# Fetch live PR/thread data and authorize only the exact prepared activity.
# On success, the exact current thread JSON is written to thread-file.
reviewer_current_check() {
  local plan="$1" item="$2" pr_view_file="$3" thread_file="$4"
  local activity identity expected expected_thread root_db result allow_resolved="${5:-false}"
  if ! try "$err" gh pr view "$PR" --json state,headRefOid,author > "$pr_view_file"; then
    echo "PR state unavailable: $(tail -n 1 "$err")"
    return 1
  fi
  if ! try "$err" fetch_pr_threads "$PR" > "$threads"; then
    echo "review thread detail unavailable: $(tail -n 1 "$err")"
    return 1
  fi
  activity=$(printf '%s' "$item" | jq -c '.activity // empty')
  expected_thread=$(printf '%s' "$item" | jq -r '.thread_id // ""')
  root_db=$(printf '%s' "$item" | jq -r '.comment_id // ""')
  [ -n "$activity" ] && [ -n "$expected_thread" ] && [ -n "$root_db" ] || {
    echo "reviewer action is missing exact thread, root, or activity identity"
    return 1
  }
  jq -c --arg tid "$expected_thread" --argjson rootdb "$root_db" \
    'map(select(.id == $tid and .comments.nodes[0].databaseId == $rootdb)) | if length == 1 then .[0] else empty end' \
    "$threads" > "$thread_file"
  [ -s "$thread_file" ] || { echo "exact reviewer thread/root is missing or replaced"; return 1; }
  if [ "$allow_resolved" = true ]; then
    jq -e '.isResolved == true' "$thread_file" >/dev/null || return 1
    jq '.isResolved = false' "$thread_file" > "$thread_file.tmp" && mv "$thread_file.tmp" "$thread_file"
  fi
  identity=$(jq -c '.activity_identity' "$plan")
  expected=$(jq -c '.activity' <<<"$item")
  result=$(jq -nc --argjson identity "$identity" --argjson expected "$expected" \
    --argjson current_pr "$(jq '{state, head_oid: .headRefOid, author: .author.login}' "$pr_view_file")" \
    --slurpfile thread "$thread_file" \
    '{identity:$identity, expected:$expected, current_pr:$current_pr, thread:$thread[0]}')
  if ! printf '%s\n' "$result" | python3 "$SCRIPT_DIR/reviewer_activity.py" check > "$out" 2>"$err"; then
    echo "review activity check failed: $(tail -n 1 "$err")"
    return 1
  fi
  jq -e '.allowed == true and .complete == true' "$out" >/dev/null || {
    echo "$(jq -r '.reason // "review activity is incomplete"' "$out")"
    return 1
  }
  return 0
}

reviewer_marker_reply() {
  local thread_file="$1" plan="$2" item="$3" identity activity
  identity=$(jq -c '.activity_identity' "$plan")
  activity=$(printf '%s' "$item" | jq -c '.activity')
  jq -nc --argjson identity "$identity" --argjson activity "$activity" \
    --slurpfile thread "$thread_file" '{identity:$identity,activity:$activity,thread:$thread[0]}' \
    | python3 -c 'import json,sys; from pathlib import Path; p=Path(sys.argv[1]); sys.path.insert(0,str(p.parent)); import reviewer_activity as r; v=json.load(sys.stdin); print(r.matching_activity_reply(v["thread"],v["identity"],v["activity"]) or "")' "$SCRIPT_DIR/reviewer_activity.py"
}

reviewer_record_outcome() {
  local plan="$1" item="$2" reply_id="$3" resolved="$4" identity activity outcome
  identity=$(jq -c '.activity_identity' "$plan")
  activity=$(printf '%s' "$item" | jq -c '.activity')
  outcome=$(printf '%s' "$item" | jq -c '.outcome')
  jq -nc --argjson identity "$identity" --argjson activity "$activity" --argjson outcome "$outcome" \
    --argjson reply_id "$(if [ -n "$reply_id" ]; then printf '%s' "$reply_id"; else printf null; fi)" \
    --argjson resolved "$resolved" \
    '{identity:$identity,activity:$activity,outcome:$outcome,reply_id:$reply_id,resolved:$resolved}' \
    | python3 "$SCRIPT_DIR/reviewer_activity.py" record > "$out" 2>"$err" || {
      echo "Error: cannot record completed reviewer activity: $(tail -n 1 "$err")" >&2
      return 1
    }
  jq -e '.complete == true' "$out" >/dev/null || return 1
}

# Reviewer plans never use the author bot-repair path. Revalidate each exact
# activity immediately before posting and again before resolving.
do_reviewer_triage() {
  local plan="$1" state="$2" item items action_body activity marker current_pr_file current_thread_file identity
  local comment_id thread_id resolve outcome_status reply_body response_id posted=0 resolved_n=0 stale=0 retriage=0
  local activity_key local_reply marker_reply local_resolved
  local reviewer_state="$SCRIPT_DIR/reviewer_activity.py"
  pr_status applying
  current_pr_file=$(tmpfile); current_thread_file=$(tmpfile)
  items=$(tmpfile)
  jq -c '[((.cc_review_threads // [])[] | select(
      (.outcome.completed == true and (.outcome.status == "confirmed-fixed" or .outcome.status == "still-present" or .outcome.status == "accepted-explanation"))
      and ((.body // "") != "" or .outcome.completed == true))
      | . + {review_item_kind:"cc_review"})]
      + [((.human // [])[] | select((.decision == "approve" or .decision == "edit")
      and .outcome.completed == true
      and (.outcome.status == "confirmed-fixed" or .outcome.status == "still-present" or .outcome.status == "accepted-explanation"))
      | . + {review_item_kind:"human"})] | .[]' "$plan" > "$items"
  while IFS= read -r item <&3; do
    [ -n "$item" ] || continue
    response_id=""
    activity_key=$(printf '%s' "$item" | jq -r '.activity.activity_key')
    local_resolved=$(pr_field ".actions.reviewer_resolved // [] | index(\"$activity_key\") != null")
    [ "$local_resolved" = true ] && continue
    resolve=$(printf '%s' "$item" | jq -r '.resolve // false')
    outcome_status=$(printf '%s' "$item" | jq -r '.outcome.status // "unclear"')
    if ! reviewer_current_check "$plan" "$item" "$current_pr_file" "$current_thread_file" >/dev/null; then
      # Recover the crash window after GitHub resolved the exact prepared
      # activity but before local resolution/cache recording completed.
      if [ "$resolve" = true ] \
        && [[ "$outcome_status" == confirmed-fixed || "$outcome_status" == accepted-explanation ]] \
        && reviewer_current_check "$plan" "$item" "$current_pr_file" "$current_thread_file" true >/dev/null; then
        local_reply=$(pr_field ".actions.reviewer_replies[\"$activity_key\"] // \"\"")
        marker_reply=$(reviewer_marker_reply "$current_thread_file" "$plan" "$item")
        response_id="${local_reply:-$marker_reply}"
        if [ -z "$response_id" ] && [ -n "$(printf '%s' "$item" | jq -r '.body // .draft // ""')" ]; then
          echo "Warning: reviewer thread $(printf '%s' "$item" | jq -r '.thread_id') was resolved before the approved reply was posted"
          stale=$((stale + 1)); continue
        fi
        if [ -n "$response_id" ] && [ -z "$local_reply" ]; then
          "$BULK_STATE" record "$RUN" "$PR" reviewer_reply "$activity_key" "$response_id" >/dev/null
        fi
        reviewer_record_outcome "$plan" "$item" "${response_id:-}" true || { stale=$((stale + 1)); continue; }
        "$BULK_STATE" record "$RUN" "$PR" reviewer_resolved "$activity_key" >/dev/null
        resolved_n=$((resolved_n + 1))
        continue
      fi
      echo "Warning: reviewer action on PR #$PR needs fresh preparation: $(jq -r '.reason // "incomplete evidence"' "$out" 2>/dev/null || true)"
      stale=$((stale + 1)); retriage=$((retriage + 1)); continue
    fi
    comment_id=$(printf '%s' "$item" | jq -r '.comment_id')
    thread_id=$(printf '%s' "$item" | jq -r '.thread_id')
    activity=$(printf '%s' "$item" | jq -c '.activity')
    local_reply=$(pr_field ".actions.reviewer_replies[\"$activity_key\"] // \"\"")
    identity=$(jq -c '.activity_identity' "$plan")
    action_body=$(printf '%s' "$item" | jq -r '.body // .draft // ""')
    if [[ "$action_body" == *"<!-- cc-review-triage"* ]]; then
      signed_body="$action_body"
    else
      signed_body="$action_body

<!-- cc-review-triage -->"
    fi
    marker=$(jq -nc --argjson identity "$identity" --argjson activity "$activity" --arg body "$signed_body" \
      '{identity:$identity,activity:$activity,body:$body}' | python3 -c 'import json,sys; from pathlib import Path; p=Path(sys.argv[1]); sys.path.insert(0,str(p.parent)); import reviewer_activity as r; v=json.load(sys.stdin); print(r.activity_marker(v["identity"],v["activity"],v["body"]))' "$reviewer_state")
    reply_body="$signed_body
$marker"
    if [ "$resolve" = true ] && [[ "$outcome_status" != confirmed-fixed && "$outcome_status" != accepted-explanation ]]; then
      echo "Warning: reviewer action on thread $thread_id cannot resolve outcome '$outcome_status'"
      stale=$((stale + 1))
      continue
    fi
    if [ -n "$action_body" ]; then
      if ! reviewer_current_check "$plan" "$item" "$current_pr_file" "$current_thread_file"; then
        echo "Warning: reviewer thread $thread_id became stale before reply: $(jq -r '.reason // .warnings[0] // "incomplete activity"' "$out")"
        stale=$((stale + 1)); retriage=$((retriage + 1))
        continue
      fi
      if [ -n "$local_reply" ]; then
        response_id="$local_reply"
      else
        marker_reply=$(reviewer_marker_reply "$current_thread_file" "$plan" "$item")
        if [ -n "$marker_reply" ]; then
          response_id="$marker_reply"
        else
          if ! try "$err" post_reply "$PR" "$comment_id" "$reply_body" > "$out"; then
            echo "Warning: reviewer reply to thread $thread_id failed: $(tail -n 1 "$err")"
            stale=$((stale + 1))
            continue
          fi
          response_id=$(tr -d '[:space:]' < "$out")
          [ -n "$response_id" ] && posted=$((posted + 1))
        fi
      fi
      if [ -n "$response_id" ]; then
        "$BULK_STATE" record "$RUN" "$PR" reviewer_reply "$activity_key" "$response_id" >/dev/null
        if [ "$resolve" != true ] && ! reviewer_record_outcome "$plan" "$item" "$response_id" false; then
          stale=$((stale + 1))
          continue
        fi
      fi
    fi
    if [ "$resolve" = true ]; then
      if ! reviewer_current_check "$plan" "$item" "$current_pr_file" "$current_thread_file"; then
        echo "Warning: reviewer thread $thread_id became stale before resolution: $(jq -r '.reason // .warnings[0] // "incomplete activity"' "$out")"
        stale=$((stale + 1)); retriage=$((retriage + 1))
        continue
      fi
      if ! try "$err" resolve_thread "$thread_id" >/dev/null; then
        echo "Warning: resolving reviewer thread $thread_id failed: $(tail -n 1 "$err")"
        stale=$((stale + 1))
        continue
      fi
      resolved_n=$((resolved_n + 1))
      reviewer_record_outcome "$plan" "$item" "${response_id:-}" true || { stale=$((stale + 1)); continue; }
      "$BULK_STATE" record "$RUN" "$PR" reviewer_resolved "$activity_key" >/dev/null
    elif [ -z "$response_id" ]; then
      reviewer_record_outcome "$plan" "$item" "" false || { stale=$((stale + 1)); continue; }
    fi
  done 3< "$items"
  if [ "$retriage" -gt 0 ]; then
    pr_status stale "$retriage reviewer actions need fresh preparation because activity changed or evidence was incomplete"
    echo "STALE needs-retriage=$retriage replies=$posted resolved=$resolved_n"
  elif [ "$stale" -gt 0 ]; then
    pr_status partially-applied "$stale reviewer actions failed; resume to retry the remaining writes"
    echo "PARTIAL stale=$stale replies=$posted resolved=$resolved_n"
  else
    pr_status actioned "reviewer activity applied with exact freshness checks"
    echo "ACTIONED replies=$posted resolved=$resolved_n"
  fi
}

# Executes the prepared triage of one PR (pr-<n>/triage-plan.json): push the
# prepared commit, re-read the threads, post the replies, resolve the threads.
# Every sub-action is recorded the moment it completes and skipped once
# recorded, so a rerun only does what is left.
do_triage() {
  check_args "$@"
  RUN="$2" PR="$3"
  local state plan owner repo root prepared pushed flags wt url branch expected head result rc tip selected_role plan_role author
  local err out threads items item key current cid tid recorded id failed=0 posted=0 resolved_n=0 skipped=0
  local notes=() to_resolve=()
  state=$(state_file "$RUN")
  plan="$(dirname "$state")/pr-$PR/triage-plan.json"
  jq -e 'type == "object"' "$plan" >/dev/null 2>&1 || { echo "Error: PR #$PR has no valid triage plan at $plan" >&2; exit 1; }
  owner=$(jq -r '.repo.owner' "$state")
  repo=$(jq -r '.repo.name' "$state")
  root=$(jq -r '.repo.root' "$state")
  GH_USER=$(jq -r '.gh_user' "$state")
  RUN_STARTED=$(jq -r '.created_at // ""' "$state")
  selected_role=$(pr_field '.triage_role // ""')
  plan_role=$(jq -r '.triage_role // ""' "$plan")
  author=$(pr_field '.author // ""')
  # The persisted selection is the authority for reviewer operations. The only
  # legacy fallback is an author plan for a PR whose recorded author is the
  # authenticated bulk user; a plan cannot promote itself to reviewer.
  if [ -z "$plan_role" ] && [ "$author" = "$GH_USER" ] \
    && { [ -z "$selected_role" ] || [ "$selected_role" = author ]; }; then
    selected_role=author
    plan_role=author
  fi
  if [ -z "$selected_role" ] || [ "$selected_role" != "$plan_role" ]; then
    echo "Error: PR #$PR triage role is missing or does not match the trusted bulk selection" >&2
    exit 1
  fi
  case "$selected_role" in
    author) [ "$author" = "$GH_USER" ] || { echo "Error: PR #$PR author role does not match the authenticated user" >&2; exit 1; } ;;
    reviewer)
      [ "$author" != "$GH_USER" ] || { echo "Error: PR #$PR reviewer role is invalid for an author-owned PR" >&2; exit 1; }
      if [ "$(jq -r '.prepared_commit // empty' "$plan")" != "" ] \
        || [ "$(jq -r '(.replies // []) | length' "$plan")" -gt 0 ] \
        || [ "$(jq -r '(.stale_resolutions // []) | length' "$plan")" -gt 0 ]; then
        echo "Error: reviewer triage plan for PR #$PR contains author-only commit, reply, or resolution work" >&2
        exit 1
      fi
      if ! jq -e --arg host "github.com" --arg repository "$owner/$repo" --arg user "$GH_USER" --argjson pr "$PR" \
        '.activity_identity == {host: $host, repository: $repository, user: $user, pr: $pr}
         and (.expected_head | type == "string" and length > 0)
         and ((.cc_review_threads // []) | type == "array")
         and ((.human // []) | type == "array")' "$plan" >/dev/null; then
        echo "Error: reviewer triage plan for PR #$PR has missing or mismatched activity identity" >&2
        exit 1
      fi
      ;;
    *) echo "Error: PR #$PR has unsupported triage role '$selected_role'" >&2; exit 1 ;;
  esac
  # The invoking repository's triage state, as single-PR triage uses it (FR-014a)
  export TRIAGE_STATE_FILE="${TRIAGE_STATE_FILE:-$root/.cc-review/.triage-state.json}"
  err=$(tmpfile); out=$(tmpfile); threads=$(tmpfile)
  # shellcheck source=platform.sh
  . "$SCRIPT_DIR/platform.sh"
  if [ "$selected_role" = reviewer ]; then
    do_reviewer_triage "$plan" "$state"
    return
  fi
  pr_status applying

  # 1. Push the prepared commit
  prepared=$(jq -r '.prepared_commit // ""' "$plan")
  pushed=$(pr_field '.actions.pushed_sha // ""')
  flags=$(pr_field '.flags | join(" ")')
  local skip_accepted=false denied=false
  if [ -n "$prepared" ] && [ -z "$pushed" ]; then
    case " $flags " in
      *" local-unpushed "*)
        # Pushing from the worktree would bypass the user's local commits;
        # accepted replies would point at fixes that are not on the remote
        skip_accepted=true
        notes+=("fixes not pushed: the local branch has unpushed commits; accepted replies skipped") ;;
      *)
        wt=$(pr_field '.worktree // ""')
        url=$(pr_field '.head_repo_url // ""')
        branch=$(pr_field '.head_ref // ""')
        expected=$(pr_field '.expected_head // ""')
        if [ -z "$wt" ] || [ ! -d "$wt" ]; then
          pr_status partially-applied "worktree missing; re-run needed"
          echo "Error: PR #$PR has no worktree with the prepared commit" >&2
          exit 1
        fi
        head=$(git -C "$wt" rev-parse HEAD)
        if [ "$head" != "$prepared" ]; then
          pr_status partially-applied "the worktree is not at the prepared commit; re-run needed"
          echo "Error: worktree of PR #$PR is at $head, not at the prepared commit $prepared" >&2
          exit 1
        fi
        "$BULK_STATE" record "$RUN" "$PR" pending_push "$prepared" >/dev/null
        rc=0
        result=$("$PR_WORKTREE" push "$wt" "$url" "$branch" "$expected" 2>"$err") || rc=$?
        [ "$rc" -eq 75 ] && { cat "$err" >&2; exit 75; }
        if [ "$rc" -ne 0 ]; then
          pr_status partially-applied "push failed: $(tail -n 1 "$err")"
          cat "$err" >&2
          exit 1
        fi
        case "$result" in
          "PUSHED "*)
            "$BULK_STATE" record "$RUN" "$PR" pushed_sha "${result#PUSHED }" >/dev/null
            # Head check before the replies: someone may have pushed on top of
            # the fixes; replies would then describe code that is not the head
            if ! tip=$(git -C "$wt" ls-remote "$url" "refs/heads/$branch" 2>"$err" | cut -f1) || [ -z "$tip" ]; then
              pr_status partially-applied "cannot read the branch after the push: $(tail -n 1 "$err")"
              echo "Error: cannot read $branch of PR #$PR after the push: $(tail -n 1 "$err")" >&2
              exit 1
            fi
            if [ "$tip" != "${result#PUSHED }" ]; then
              pr_status stale "stale, re-run needed: the PR branch moved after the push; replies not posted"
              echo "STALE"
              return
            fi ;;
          STALE)
            "$BULK_STATE" pr-set "$RUN" "$PR" '.status="stale"' '.pending_push=null' \
              '.reason="stale, re-run needed: the PR branch moved; nothing pushed or posted"' >/dev/null
            echo "STALE"
            return ;;
          DENIED)
            # No push permission (a fork): the fixes stay unpushed, but the
            # replies that do not depend on them are still posted (spec edge
            # case "PR from a fork": only reply posting)
            "$BULK_STATE" pr-set "$RUN" "$PR" '.pending_push=null' >/dev/null
            denied=true
            skip_accepted=true
            notes+=("cannot push to $branch: permission denied; fixes not pushed, accepted replies skipped") ;;
          *)
            echo "Error: unexpected push result for PR #$PR: $result" >&2
            exit 1 ;;
        esac ;;
    esac
  fi

  # 2. Re-read the threads: a push can make bots re-post their comments, and
  # the threads show replies an interrupted run already posted
  if ! try "$err" fetch_pr_threads "$PR" > "$threads"; then
    pr_status partially-applied "cannot read the review threads: $(tail -n 1 "$err")"
    echo "Error: cannot read the review threads of PR #$PR: $(tail -n 1 "$err")" >&2
    exit 1
  fi

  # Head check right before the replies (FR-030): the branch may have moved
  # while the threads were read. The branch tip is read from the head
  # repository, which is current right after a push (GitHub's PR head may lag).
  url=$(pr_field '.head_repo_url // ""')
  branch=$(pr_field '.head_ref // ""')
  expected=$(pr_field '.actions.pushed_sha // .expected_head // ""')
  wt=$(pr_field '.worktree // ""')
  [ -n "$wt" ] && [ -d "$wt" ] || wt="."
  if [ -n "$url" ] && [ -n "$branch" ] && [ -n "$expected" ]; then
    if ! tip=$(git -C "$wt" ls-remote "$url" "refs/heads/$branch" 2>"$err" | cut -f1) || [ -z "$tip" ]; then
      pr_status partially-applied "cannot read the branch before posting replies: $(tail -n 1 "$err")"
      echo "Error: cannot read $branch of PR #$PR before posting replies: $(tail -n 1 "$err")" >&2
      exit 1
    fi
    if [ "$tip" != "$expected" ]; then
      pr_status stale "stale, re-run needed: the PR branch moved before the replies were posted"
      echo "STALE"
      return
    fi
  fi

  # 3. Replies
  items=$(tmpfile)
  triage_items "$plan" "$skip_accepted" > "$items"
  # fd 3, so no command in the loop can read the item list
  while IFS= read -r item <&3; do
    [ -n "$item" ] || continue
    key=$(printf '%s' "$item" | jq -r '.comment_id')
    current=$(thread_for "$threads" "$item")
    if [ -z "$current" ]; then
      skipped=$((skipped + 1))
      continue
    fi
    cid=$(printf '%s' "$current" | jq -r '.comment_id')
    tid=$(printf '%s' "$current" | jq -r '.thread_id')
    recorded=$(pr_field ".actions.replies[\"$key\"] // \"\"")
    if [ -z "$recorded" ]; then
      id=$(printf '%s' "$current" | jq -r '.own_reply // empty')
      if [ -z "$id" ]; then
        rc=0
        try "$err" post_reply "$PR" "$cid" "$(printf '%s' "$item" | jq -r '.body')" > "$out" || rc=$?
        id=$(tr -d '[:space:]' < "$out")
        if [ "$rc" -ne 0 ] || [ -z "$id" ]; then
          echo "Warning: reply to comment $cid on PR #$PR failed: $(tail -n 1 "$err")" >&2
          failed=$((failed + 1))
          continue
        fi
        posted=$((posted + 1))
      fi
      "$BULK_STATE" record "$RUN" "$PR" reply "$key" "$id" >/dev/null
      "$SCRIPT_DIR/triage-state.sh" init "$PR" >/dev/null
      "$SCRIPT_DIR/triage-state.sh" set "$PR" "$cid" "$(printf '%s' "$item" | jq -r '.action')" "$id" >/dev/null
    elif [ "$("$SCRIPT_DIR/triage-state.sh" get "$PR" "$cid" 2>/dev/null || echo NOT_FOUND)" = NOT_FOUND ]; then
      # Recorded here but not in the shared triage state (an interruption
      # between the two writes): repair it, so single-PR triage skips it
      "$SCRIPT_DIR/triage-state.sh" init "$PR" >/dev/null
      "$SCRIPT_DIR/triage-state.sh" set "$PR" "$cid" "$(printf '%s' "$item" | jq -r '.action')" "$recorded" >/dev/null
    fi
    # Only a thread with our reply is ever resolved
    if [ "$(printf '%s' "$item" | jq -r '.resolve')" = true ]; then
      to_resolve+=("$tid")
    fi
  done 3< "$items"

  # 4. Resolutions: replied threads, then stale handled threads (replied in an
  # earlier pass)
  while IFS= read -r tid; do
    [ -n "$tid" ] && to_resolve+=("$tid")
  done < <(jq -r '(.stale_resolutions // [])[]' "$plan")
  for tid in ${to_resolve[@]+"${to_resolve[@]}"}; do
    [ "$(pr_field "any(.actions.resolved[]; . == \"$tid\")")" = true ] && continue
    if [ "$(jq -r --arg t "$tid" 'any(.[]; .id == $t and .isResolved)' "$threads")" != true ]; then
      if ! try "$err" resolve_thread "$tid" >/dev/null; then
        echo "Warning: resolving thread $tid on PR #$PR failed: $(tail -n 1 "$err")" >&2
        failed=$((failed + 1))
        continue
      fi
    fi
    "$BULK_STATE" record "$RUN" "$PR" resolved "$tid" >/dev/null
    resolved_n=$((resolved_n + 1))
  done

  [ "$skipped" -gt 0 ] && notes+=("$skipped replies skipped (thread not found after push)")
  if [ "$failed" -gt 0 ]; then
    notes+=("$failed sub-actions failed; a resume retries them")
    pr_status partially-applied "$(IFS=';'; printf '%s' "${notes[*]}" | sed 's/;/; /g')"
    echo "PARTIAL failed=$failed replies=$posted resolved=$resolved_n"
    return
  fi
  if [ "$denied" = true ]; then
    pr_status cannot-push "$(IFS=';'; printf '%s' "${notes[*]}" | sed 's/;/; /g')"
    echo "DENIED replies=$posted resolved=$resolved_n skipped=$skipped"
    return
  fi
  pr_status actioned "$(IFS=';'; printf '%s' "${notes[*]+"${notes[*]}"}" | sed 's/;/; /g')"
  echo "ACTIONED replies=$posted resolved=$resolved_n skipped=$skipped"
}

case "${1:-}" in
  head)
    do_head "$@" ;;
  marker)
    do_marker "$@" ;;
  review-push)
    do_review_push "$@" ;;
  triage)
    do_triage "$@" ;;
  *)
    echo "Usage: bulk-apply.sh {head|marker|review-push|triage} <run> <n>" >&2
    exit 2 ;;
esac
