#!/usr/bin/env bash
# post-review.sh - Post an approved cc-review draft, after fresh safety checks
#
# Usage:
#   post-review.sh --draft <dir> --owner <o> --repo <r> --pr <n> --user <login>
#                  --expected-head <sha> --run-marker <m> --scope <scope dir>
#                  --approved-fingerprint <sha> [--history <history.json>]
#                  [--just-pushed] [--accept-changes <hash>]
#                  [--ignore-author <login>]... [--check-only]
#
# --check-only runs the checks of steps 1 to 5 before a thread reply or
# resolution and prints "OK" instead of posting: the draft may then hold only
# thread-actions.json (no review is posted), step 1 does not check the payload
# shape, step 2 runs only when payload.json exists, and step 4 never stops
# (the run's own review is expected on the PR then).
#
# --ignore-author <login> (repeatable, config pr_posting.ignore_authors): the
# login is treated like a bot in step 5.
#
# Every read and the post address --owner/--repo; the current directory does
# not need to be a clone of the repository.
#
# Order of operations (stops at the first result that is not OK; nothing is
# written to the hosting service before step 6):
#   1. the draft's fingerprint equals --approved-fingerprint   else REFUSED fingerprint
#      (payload.json and thread-actions.json are copied first; the copies are
#      fingerprinted and the copy of payload.json is what step 6 sends), and
#      the payload is a COMMENT or REQUEST_CHANGES review carrying this run's
#      marker line                                              else REFUSED payload
#   2. payload.json pins commit_id to --expected-head           else STALE commit
#   3. the live PR head equals --expected-head (with --just-pushed: up to 3
#      reads about 5 s apart)                                   else STALE head | STALE closed
#   4. no review by --user carries this run's marker line       else FOUND <review_id>
#   5. the conversation could be read completely, and no review thread,
#      review comment, conversation comment or review was created since
#      analysis (scope analyzed-at.json; without it: absent from the analysis
#      snapshot) by someone other than --user, a bot or an ignored author;
#      the Follow-up Continuity history recheck (--history) applies the same
#      rule to the items of the rebuilt history, so edits, the run's own
#      pushes and the user's own comments never count  else CHANGED <hash> <reason>
#      (<hash> is the SHA-256 of <reason>; --accept-changes <hash> passes this
#      step for exactly these changes, any further change is CHANGED again)
#   6. POST payload.json byte for byte. HTTP 422 mentioning the commit is
#      STALE head (with --just-pushed after 3 attempts about 5 s apart); a
#      timeout or 5xx waits about 20 s and repeats step 4 (FOUND when the
#      review exists); any other failure writes <draft>/recovery.json and is
#      FAILED <auth|other> <message>
#   7. POSTED <review_id> <html_url>
#
# A FAILED line before step 6 (the PR, its reviews or its conversation could
# not be read) writes no recovery file: nothing was attempted.
#
# Stdout is exactly one result line. Exit codes: 0 POSTED, FOUND and OK; 1
# REFUSED, STALE, CHANGED and FAILED; 2 usage error; 75 hosting-service rate
# limit (stderr "Error: RATE_LIMITED"). Thread actions are not performed here.
#
# CC_REVIEW_POST_RETRY_DELAY (default 5) and CC_REVIEW_POST_RECHECK_DELAY
# (default 20) set the waits in seconds.

set -euo pipefail

SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DRAFT_TOOL="$SCRIPT_DIR/review_draft.py"
RETRY_DELAY="${CC_REVIEW_POST_RETRY_DELAY:-5}"
RECHECK_DELAY="${CC_REVIEW_POST_RECHECK_DELAY:-20}"

usage() {
  echo "Usage: post-review.sh --draft <dir> --owner <o> --repo <r> --pr <n> --user <login> --expected-head <sha> --run-marker <m> --scope <dir> --approved-fingerprint <sha> [--history <file>] [--just-pushed] [--accept-changes <hash>] [--ignore-author <login>]... [--check-only]" >&2
  exit 2
}

DRAFT="" OWNER="" REPO="" PR="" GH_LOGIN="" EXPECTED="" MARKER="" SCOPE="" APPROVED=""
HISTORY="" JUST_PUSHED=false ACCEPT="" CHECK_ONLY=false
IGNORE_ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --ignore-author)
      [ $# -ge 2 ] || usage
      [ -z "$2" ] || IGNORE_ARGS+=(--ignore-author "$2")
      shift 2 ;;
    --check-only) CHECK_ONLY=true; shift ;;
    --draft|--owner|--repo|--pr|--user|--expected-head|--run-marker|--scope|--approved-fingerprint|--history|--accept-changes)
      [ $# -ge 2 ] || usage
      case "$1" in
        --draft) DRAFT="$2" ;;
        --owner) OWNER="$2" ;;
        --repo) REPO="$2" ;;
        --pr) PR="$2" ;;
        --user) GH_LOGIN="$2" ;;
        --expected-head) EXPECTED="$2" ;;
        --run-marker) MARKER="$2" ;;
        --scope) SCOPE="$2" ;;
        --approved-fingerprint) APPROVED="$2" ;;
        --history) HISTORY="$2" ;;
        --accept-changes) ACCEPT="$2" ;;
      esac
      shift 2 ;;
    --just-pushed) JUST_PUSHED=true; shift ;;
    *) usage ;;
  esac
done
for value in "$DRAFT" "$OWNER" "$REPO" "$PR" "$GH_LOGIN" "$EXPECTED" "$MARKER" "$SCOPE" "$APPROVED"; do
  [ -n "$value" ] || usage
done
[[ "$PR" =~ ^[0-9]+$ ]] || { echo "Error: --pr must be a positive integer, got '$PR'" >&2; exit 2; }
if [ "$CHECK_ONLY" = true ]; then
  [ -f "$DRAFT/payload.json" ] || [ -f "$DRAFT/thread-actions.json" ] \
    || { echo "Error: $DRAFT has neither payload.json nor thread-actions.json" >&2; exit 2; }
else
  [ -f "$DRAFT/payload.json" ] || { echo "Error: $DRAFT/payload.json does not exist" >&2; exit 2; }
fi
[ -d "$SCOPE" ] || { echo "Error: scope directory $SCOPE does not exist" >&2; exit 2; }
if [ -n "$HISTORY" ] && [ ! -f "$HISTORY" ]; then
  echo "Error: history file $HISTORY does not exist" >&2; exit 2
fi

T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/current" "$T/draft"

# rate_limited and try
# shellcheck source=rate-limit.sh
. "$SCRIPT_DIR/rate-limit.sh"
# shellcheck source=platform.sh
. "$SCRIPT_DIR/platform.sh"
# Every read and the post address --owner/--repo on GitHub (gh with --repo,
# GraphQL owner and name, REST paths), never the current directory's remote
CC_REVIEW_PLATFORM=github

sha256() {
  python3 -c 'import hashlib,sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())'
}

# last_line <file>...: the last non-empty line of the files, on one line
last_line() {
  cat "$@" 2>/dev/null | awk 'NF { line = $0 } END { print substr(line, 1, 200) }'
}

MARKER_LINE="<!-- cc-review:run-id:$MARKER -->"

# find_marker: writes the id of a review by --user carrying this run's marker
# line (empty when none) to $T/found; fails when the reviews cannot be read.
# Another author's review with the marker is not this run's review.
find_marker() {
  if ! try "$T/reviews.err" fetch_reviews "$OWNER" "$REPO" "$PR" > "$T/current/reviews.json"; then
    return 1
  fi
  jq -r --arg line "$MARKER_LINE" --arg user "$GH_LOGIN" \
    '[.[] | select((.author.login // "") == $user)
       | select(any((.body // "") | split("\n")[]; sub("^\\s+"; "") | sub("\\s+$"; "") == $line))]
     | first | .databaseId // empty' \
    "$T/current/reviews.json" > "$T/found"
}

write_recovery() {
  cp "$T/draft/payload.json" "$DRAFT/recovery.json"
}

# 1. Fingerprint of exactly the files that will be sent: the copies taken here
#    are what is checked and posted, whatever happens to the draft meanwhile
[ ! -f "$DRAFT/payload.json" ] || cp "$DRAFT/payload.json" "$T/draft/payload.json"
[ ! -f "$DRAFT/thread-actions.json" ] || cp "$DRAFT/thread-actions.json" "$T/draft/thread-actions.json"
if ! fingerprint=$(python3 -B "$DRAFT_TOOL" fingerprint --draft "$T/draft" 2>"$T/fp.err"); then
  echo "Error: cannot fingerprint the draft: $(last_line "$T/fp.err")" >&2
  exit 2
fi
if [ "$fingerprint" != "$APPROVED" ]; then
  echo "REFUSED fingerprint"
  exit 1
fi
# Only a comment or a request for changes, and only with this run's marker
if [ "$CHECK_ONLY" != true ] && ! jq -e --arg line "$MARKER_LINE" \
    '(.event == "COMMENT" or .event == "REQUEST_CHANGES")
     and any((.body // "") | split("\n")[]; sub("^\\s+"; "") | sub("\\s+$"; "") == $line)' \
    "$T/draft/payload.json" >/dev/null 2>&1; then
  echo "REFUSED payload"
  exit 1
fi

# 2. Pinned commit (a check of thread actions alone has no payload)
if [ -f "$T/draft/payload.json" ]; then
  commit=$(jq -r '.commit_id // ""' "$T/draft/payload.json")
  if [ -z "$commit" ] || [ "$commit" != "$EXPECTED" ]; then
    echo "STALE commit"
    exit 1
  fi
fi

# 3. Live head (right after a push by this run GitHub may still report the
#    pre-push head for a few seconds)
reads=1
[ "$JUST_PUSHED" = true ] && reads=3
head=""
for ((i = 1; i <= reads; i++)); do
  if ! try "$T/head.err" gh pr view "$PR" --repo "$OWNER/$REPO" --json state,headRefOid > "$T/head.json"; then
    echo "FAILED other cannot read PR #$PR: $(last_line "$T/head.err")"
    exit 1
  fi
  if [ "$(jq -r '.state // ""' "$T/head.json")" != OPEN ]; then
    echo "STALE closed"
    exit 1
  fi
  head=$(jq -r '.headRefOid // ""' "$T/head.json")
  [ "$head" = "$EXPECTED" ] && break
  [ "$i" -lt "$reads" ] && sleep "$RETRY_DELAY"
done
if [ "$head" != "$EXPECTED" ]; then
  echo "STALE head"
  exit 1
fi

# 4. A review this run already posted (an earlier attempt that timed out);
#    the reviews read here also feed step 5. A check before thread actions
#    expects the run's own review and goes on.
if ! find_marker; then
  echo "FAILED other cannot read the reviews of PR #$PR: $(last_line "$T/reviews.err")"
  exit 1
fi
if [ "$CHECK_ONLY" != true ] && [ -s "$T/found" ]; then
  echo "FOUND $(cat "$T/found")"
  exit 0
fi

# 5. History recheck and conversation changes since analysis
threads_ok=true comments_ok=true
if ! fetch_pr_threads "$PR" "$OWNER" "$REPO" > "$T/current/threads.json" 2>"$T/threads.err"; then
  if rate_limited "$T/threads.err"; then echo "Error: RATE_LIMITED" >&2; exit 75; fi
  threads_ok=false
fi
if ! fetch_issue_comments "$OWNER" "$REPO" "$PR" > "$T/current/comments.json" 2>"$T/comments.err"; then
  if rate_limited "$T/comments.err"; then echo "Error: RATE_LIMITED" >&2; exit 75; fi
  comments_ok=false
fi
# Partial data (for example a thread with more than 100 comments) is still
# compared; data that is not an array at all cannot be compared
for name in threads comments; do
  if ! jq -e 'type == "array"' "$T/current/$name.json" >/dev/null 2>&1; then
    echo "FAILED other cannot read the $name of PR #$PR: $(last_line "$T/$name.err")"
    exit 1
  fi
done

reasons=()
# Without a complete read, a new item could hide in the missing part
if [ "$threads_ok" != true ] || [ "$comments_ok" != true ]; then
  reasons+=("conversation incomplete: the threads or comments could not be read completely")
fi
if [ -n "$HISTORY" ]; then
  # Rebuild the history from the fresh data with the analysis-time inputs;
  # the analyzed files are only read, never replaced. Only new items by
  # other people count, as in the conversation check: edits, thread states,
  # the run's own pushes and the user's own comments do not.
  flags="$SCOPE/history-input.json"
  ids="$SCOPE/review-comment-ids.json"
  [ -f "$ids" ] || { ids="$T/ids.json"; printf '[]\n' > "$ids"; }
  if [ ! -f "$flags" ]; then
    flags="$T/flags.json"
    printf '{"reviews_complete":true,"threads_complete":true,"comments_complete":true}\n' > "$flags"
  fi
  history_rc=0
  if ! jq -n --slurpfile scope "$SCOPE/scope.json" --slurpfile flags "$flags" \
      --slurpfile reviews "$T/current/reviews.json" --slurpfile threads "$T/current/threads.json" \
      --slurpfile comments "$T/current/comments.json" --slurpfile ids "$ids" \
      --argjson threads_ok "$threads_ok" --argjson comments_ok "$comments_ok" \
      '{identity:$scope[0].identity,head_oid:$scope[0].head_oid,reviews:$reviews[0],threads:$threads[0],
        comments:$comments[0],reviews_complete:($flags[0].reviews_complete != false),
        threads_complete:($threads_ok and $flags[0].threads_complete != false),
        comments_complete:($comments_ok and $flags[0].comments_complete != false),
        review_comment_ids:$ids[0]}' > "$T/history-selected.json" 2>"$T/history.err"; then
    history_rc=2
  elif ! python3 -B "$SCRIPT_DIR/review_continuity.py" prepare --input "$T/history-selected.json" \
      > "$T/history.json" 2>>"$T/history.err"; then
    history_rc=2
  else
    python3 -B "$DRAFT_TOOL" history-diff --analysis-history "$HISTORY" --current-history "$T/history.json" \
      --scope "$SCOPE" --user "$GH_LOGIN" ${IGNORE_ARGS[@]+"${IGNORE_ARGS[@]}"} \
      > "$T/history-diff.json" 2>>"$T/history.err" || history_rc=$?
  fi
  case "$history_rc" in
    0) ;;
    1) reasons+=("history changed: $(jq -r 'map("\(.kind) \(.id) by \(.author)") | join(", ")' "$T/history-diff.json")") ;;
    *) reasons+=("history could not be rechecked: $(last_line "$T/history.err")") ;;
  esac
fi
diff_rc=0
python3 -B "$DRAFT_TOOL" conversation-diff --analysis "$SCOPE" --current "$T/current" --user "$GH_LOGIN" \
  ${IGNORE_ARGS[@]+"${IGNORE_ARGS[@]}"} > "$T/diff.json" 2>"$T/diff.err" || diff_rc=$?
case "$diff_rc" in
  0) ;;
  1) reasons+=("new conversation items: $(jq -r 'map("\(.kind) \(.id) by \(.author)") | join(", ")' "$T/diff.json")") ;;
  *) echo "FAILED other cannot compare the conversation: $(last_line "$T/diff.err")"; exit 1 ;;
esac
if [ "${#reasons[@]}" -gt 0 ]; then
  reason=$(printf '%s; ' "${reasons[@]}")
  reason="${reason%; }"
  hash=$(printf '%s' "$reason" | sha256)
  if [ "$ACCEPT" != "$hash" ]; then
    echo "CHANGED $hash $reason"
    exit 1
  fi
fi
if [ "$CHECK_ONLY" = true ]; then
  echo "OK"
  exit 0
fi

# 6. POST the checked file unchanged
posts=1
[ "$JUST_PUSHED" = true ] && posts=3
for ((attempt = 1; ; attempt++)); do
  rc=0
  # post_review merges gh's stderr into its output
  post_review "$OWNER" "$REPO" "$PR" "$T/draft/payload.json" > "$T/out" 2>"$T/err" || rc=$?
  [ "$rc" -eq 0 ] && break
  if rate_limited "$T/out" "$T/err"; then
    echo "Error: RATE_LIMITED" >&2
    exit 75
  fi
  # GitHub rejects a commit_id that is no longer the PR's head line
  if grep -q '422' "$T/out" "$T/err" && grep -qi 'commit' "$T/out" "$T/err"; then
    if [ "$attempt" -lt "$posts" ]; then
      sleep "$RETRY_DELAY"
      continue
    fi
    echo "STALE head"
    exit 1
  fi
  message=$(last_line "$T/out" "$T/err")
  # A timeout does not mean nothing was posted: look for the marker first
  if grep -qiE 'HTTP 5[0-9][0-9]|\b50[234]\b|timed? ?out|gateway' "$T/out" "$T/err"; then
    sleep "$RECHECK_DELAY"
    if find_marker && [ -s "$T/found" ]; then
      echo "FOUND $(cat "$T/found")"
      exit 0
    fi
    write_recovery
    echo "FAILED other $message"
    exit 1
  fi
  write_recovery
  if grep -qiE 'authentication|401|403|login|credential' "$T/out" "$T/err"; then
    echo "FAILED auth $message"
  else
    echo "FAILED other $message"
  fi
  exit 1
done

# 7. Success (post_review merges gh's stderr into its output, so an answer
#    without a readable id is checked with the marker search)
id=$(jq -r '.id // empty' "$T/out" 2>/dev/null || true)
if [ -z "$id" ]; then
  if find_marker && [ -s "$T/found" ]; then
    echo "FOUND $(cat "$T/found")"
    exit 0
  fi
  write_recovery
  echo "FAILED other the review POST returned no review id"
  exit 1
fi
url=$(jq -r '.html_url // empty' "$T/out" 2>/dev/null || true)
[ -n "$url" ] || url="https://github.com/$OWNER/$REPO/pull/$PR#pullrequestreview-$id"
echo "POSTED $id $url"
