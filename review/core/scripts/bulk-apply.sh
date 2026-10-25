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
  payload=$(tmpfile)
  jq -n --arg body "$body" --arg commit "$head" \
    '{body: $body, event: "COMMENT", commit_id: $commit, comments: []}' > "$payload"
  out=$(tmpfile)
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

# Executes the prepared triage of one PR (pr-<n>/triage-plan.json): push the
# prepared commit, re-read the threads, post the replies, resolve the threads.
# Every sub-action is recorded the moment it completes and skipped once
# recorded, so a rerun only does what is left.
do_triage() {
  check_args "$@"
  RUN="$2" PR="$3"
  local state plan owner repo root prepared pushed flags wt url branch expected head result rc tip
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
  # The invoking repository's triage state, as single-PR triage uses it (FR-014a)
  export TRIAGE_STATE_FILE="${TRIAGE_STATE_FILE:-$root/.cc-review/.triage-state.json}"
  err=$(tmpfile); out=$(tmpfile); threads=$(tmpfile)
  # shellcheck source=platform.sh
  . "$SCRIPT_DIR/platform.sh"
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
