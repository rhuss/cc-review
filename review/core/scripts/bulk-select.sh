#!/usr/bin/env bash
# bulk-select.sh - Select the PRs of a bulk review or triage run
#
# Usage:
#   bulk-select.sh review [--all-open | --search <q>] [--limit <n>] --user <login>
#   bulk-select.sh triage [--search <q>] [--limit <n>] --user <login>
#   bulk-select.sh check-query <q>
#
# Review selects, by default, the PRs that request the user's review plus
# re-reviews; --all-open selects every open PR; --search selects the open
# PRs of the current repository that match the query.
# Triage selects author feedback and fresh owned reviewer findings, including
# drafts. Shared Python assessment decides both action categories.
#
# Prints {"selected": [PrEntry seed], "excluded": [Exclusion]} on stdout.
# Selected PRs are ordered by updatedAt ascending (least recently updated
# first) and capped at --limit (default 10); the rest are excluded as
# over-limit. Drafts are excluded (unless a --search query asks for them with
# draft:true or is:draft), and so is every PR that already has a cc-review
# review against its current head commit. A marker review by the PR's own
# author does not count (the author could post one to opt out of review),
# unless that author is the user running the bulk review.
#
# check-query rejects search qualifiers that would leave the current
# repository or its open PRs (repo:, org:, user:, is:closed, is:merged,
# state:) with exit 2; review and triage check --search the same way.
#
# Exit codes: 0 ok, 1 failure, 2 usage error, 75 hosting-service rate limit
# (stderr "Error: RATE_LIMITED").

set -euo pipefail

SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
MARKER='<!-- cc-review:run-id:'
PR_FIELDS="number,title,author,isDraft,headRefOid,headRefName,baseRefName,updatedAt,isCrossRepository,headRepository,headRepositoryOwner,reviews"
# gh pr list returns at most this many reviews per PR; a PR at the cap may
# have more, so its reviews are re-fetched with pagination
REVIEWS_PAGE=100
# Candidate PRs fetched per list query; a result at the cap is warned about,
# since PRs beyond it are neither selected nor listed as excluded
LIST_CAP=1000

_TMPFILES=()
_cleanup_tmp() { rm -f ${_TMPFILES[@]+"${_TMPFILES[@]}"}; }
trap _cleanup_tmp EXIT

tmpfile() {
  local f
  f=$(mktemp); _TMPFILES+=("$f")
  printf '%s' "$f"
}

# try
# shellcheck source=rate-limit.sh
. "$SCRIPT_DIR/rate-limit.sh"

# gh_json <out> <cmd...>: runs a gh call into <out>, failing with its message
gh_json() {
  local out="$1" err
  shift
  err=$(tmpfile)
  if ! try "$err" "$@" > "$out"; then
    echo "Error: $* failed: $(tail -n 1 "$err")" >&2
    exit 1
  fi
}

selection_context() {
  local tool identity repo_meta err
  for tool in python3 gh jq; do
    command -v "$tool" >/dev/null 2>&1 || { echo "Error: $tool is required for bulk selection" >&2; exit 1; }
  done
  python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || {
    echo "Error: Python 3.9+ is required for bulk selection" >&2; exit 1;
  }
  identity=$(tmpfile); repo_meta=$(tmpfile); err=$(tmpfile)
  if ! try "$err" gh api user --jq .login > "$identity"; then
    echo "Error: authentication unavailable; run gh auth login: $(tail -n 1 "$err")" >&2; exit 1
  fi
  [ -s "$identity" ] && [ "$(cat "$identity")" != null ] || {
    echo "Error: authentication is unavailable; run gh auth login" >&2; exit 1;
  }
  gh_json "$repo_meta" gh repo view --json nameWithOwner,url
  BULK_REPOSITORY=$(jq -er '.nameWithOwner | select(type == "string" and length > 0)' "$repo_meta") || {
    echo "Error: repository identity is unavailable; check access" >&2; exit 1;
  }
  BULK_HOST=$(jq -r '(.url // "https://github.com") | sub("^https://"; "") | split("/")[0]' "$repo_meta")
  COLLECTION_WARNINGS_FILE=$(tmpfile)
  printf '[]\n' > "$COLLECTION_WARNINGS_FILE"
}

selection_warning() {
  local next
  echo "Warning: $1" >&2
  next=$(tmpfile)
  jq --arg warning "$1" '. + [$warning]' "$COLLECTION_WARNINGS_FILE" > "$next"
  cp "$next" "$COLLECTION_WARNINGS_FILE"
}

# origin_protocol: the protocol of origin's URL (ssh or https), used for the
# push URLs of PR head repositories. The configured URL is read without
# insteadOf expansion, so it reflects what the user typed.
origin_protocol() {
  local url
  url=$(git config --get remote.origin.url 2>/dev/null || true)
  case "$url" in
    git@*|ssh://*) echo ssh ;;
    *) echo https ;;
  esac
}

# refetch_truncated_reviews <prs-file>: replaces the reviews of every PR that
# hit the page size with the paginated list from fetch_reviews
refetch_truncated_reviews() {
  local file="$1" numbers n owner repo reviews tmp
  numbers=$(jq -r --argjson cap "$REVIEWS_PAGE" '.[] | select((.reviews | length) >= $cap) | .number' "$file")
  [ -n "$numbers" ] || return 0
  # shellcheck source=platform.sh
  . "$SCRIPT_DIR/platform.sh"
  owner=$(tmpfile); repo=$(tmpfile)
  gh_json "$owner" gh repo view --json owner -q .owner.login
  gh_json "$repo" gh repo view --json name -q .name
  for n in $numbers; do
    reviews=$(tmpfile)
    gh_json "$reviews" fetch_reviews "$(cat "$owner")" "$(cat "$repo")" "$n"
    tmp=$(tmpfile)
    jq --argjson n "$n" --slurpfile r "$reviews" \
      'map(if .number == $n then .reviews = $r[0] else . end)' "$file" > "$tmp"
    cp "$tmp" "$file"
  done
}

# warn_cap <file>: a list query that hit LIST_CAP may have missed PRs
warn_cap() {
  if [ "$(jq 'length' "$1")" -ge "$LIST_CAP" ]; then
    selection_warning "the PR list reached $LIST_CAP entries; PRs beyond it were not considered (narrow the selection with --search)"
  fi
}

# check_query <q>: fails with exit 2 when the query names a qualifier that
# bulk mode cannot honor; GitHub qualifiers are case-insensitive, and a
# negated one (-repo:x) still changes the scope
check_query() {
  local words word lower qualifier
  # read -a splits on whitespace without glob expansion
  read -r -a words <<< "$1" || true
  for word in ${words[@]+"${words[@]}"}; do
    lower=$(printf '%s' "${word#-}" | tr '[:upper:]' '[:lower:]')
    qualifier=""
    case "$lower" in
      repo:*) qualifier="repo:" ;;
      org:*) qualifier="org:" ;;
      user:*) qualifier="user:" ;;
      state:*) qualifier="state:" ;;
      is:closed) qualifier="is:closed" ;;
      is:merged) qualifier="is:merged" ;;
    esac
    if [ -n "$qualifier" ]; then
      echo "Error: --search may not contain '$qualifier'; bulk mode always uses open PRs of the current repository" >&2
      exit 2
    fi
  done
}

# drafts_wanted <q>: true when the query asks for drafts (draft:true, is:draft)
drafts_wanted() {
  local words word
  read -r -a words <<< "$1" || true
  for word in ${words[@]+"${words[@]}"}; do
    case "$(printf '%s' "$word" | tr '[:upper:]' '[:lower:]')" in
      draft:true|is:draft) echo true; return ;;
    esac
  done
  echo false
}

# classify <candidates-file> <user> <limit> [<keep-drafts>]: drafts (unless
# kept) and PRs reviewed at their head are excluded; the rest is ordered,
# capped and turned into seeds
classify() {
  local file="$1" user="$2" limit="$3" keep_drafts="${4:-false}" action="${5:-review}" mode="${6:-default}"
  local normalized result
  local draft_args=()
  [ "$keep_drafts" = true ] && draft_args+=(--include-review-drafts)
  [ "${FORCE_FULL:-false}" = true ] && draft_args+=(--full)
  normalized=$(tmpfile); result=$(tmpfile)
  jq -e 'type == "array"' "$file" >/dev/null || { echo "Error: required PR evidence is unavailable" >&2; exit 1; }
  jq --arg proto "$(origin_protocol)" --arg host "$BULK_HOST" 'map(. + {origin_protocol:$proto,host:$host})' "$file" > "$normalized"
  python3 -B "$SCRIPT_DIR/pr_actions.py" select --source bulk --repo "$BULK_REPOSITORY" --user "$user" \
    --host "$BULK_HOST" --review-mode "$mode" --action "$action" --limit "$limit" \
    ${draft_args[@]+"${draft_args[@]}"} < "$normalized" > "$result" || exit $?
  jq -r '.warnings[] | "Warning: " + .' "$result" >&2
  jq --slurpfile collection "$COLLECTION_WARNINGS_FILE" '.warnings += $collection[0]' "$result" > "$normalized"
  cp "$normalized" "$result"
  if jq -e --arg action "$action" '(.selected|length)==0 and (.excluded|length)>0
      and all(.excluded[]; .assessment[$action].complete == false)' "$result" >/dev/null; then
    echo "Error: required $action evidence is unavailable; queue assessment is incomplete" >&2
    exit 1
  fi
  cat "$result"
}

do_review() {
  local mode=default query="" limit=10 user=""
  local FORCE_FULL=false
  while [ $# -gt 0 ]; do
    case "$1" in
      --full) FORCE_FULL=true; shift ;;
      --all-open) mode=all-open; shift ;;
      --search) [ $# -ge 2 ] || { echo "Usage: bulk-select.sh review [--all-open | --search <q>] [--limit <n>] --user <login>" >&2; exit 2; }
        mode=search; query="$2"; shift 2 ;;
      --limit) [ $# -ge 2 ] || { echo "Usage: bulk-select.sh review [--all-open | --search <q>] [--limit <n>] --user <login>" >&2; exit 2; }
        limit="$2"; shift 2 ;;
      --user) [ $# -ge 2 ] || { echo "Usage: bulk-select.sh review [--all-open | --search <q>] [--limit <n>] --user <login>" >&2; exit 2; }
        user="$2"; shift 2 ;;
      *) echo "Usage: bulk-select.sh review [--all-open | --search <q>] [--limit <n>] --user <login>" >&2; exit 2 ;;
    esac
  done
  [ -n "$user" ] || { echo "Error: --user is required" >&2; exit 2; }
  [[ "$limit" =~ ^[0-9]+$ ]] && [ "$limit" -gt 0 ] || { echo "Error: --limit must be a positive integer, got '$limit'" >&2; exit 2; }
  [ "$mode" != search ] || check_query "$query"
  selection_context

  local requested reviewed candidates
  requested=$(tmpfile); reviewed=$(tmpfile); candidates=$(tmpfile)
  case "$mode" in
    all-open)
      gh_json "$candidates" gh pr list --state open --limit "$LIST_CAP" --json "$PR_FIELDS"
      warn_cap "$candidates"
      refetch_truncated_reviews "$candidates"
      classify "$candidates" "$user" "$limit" false review all-open
      return ;;
    search)
      check_query "$query"
      # gh pr list keeps the search inside the current repository
      gh_json "$candidates" gh pr list --state open --search "$query" --limit "$LIST_CAP" --json "$PR_FIELDS"
      warn_cap "$candidates"
      refetch_truncated_reviews "$candidates"
      classify "$candidates" "$user" "$limit" "$(drafts_wanted "$query")" review search
      return ;;
  esac
  # review-requested:@me includes requests to the user's teams
  gh_json "$requested" gh pr list --state open --search "review-requested:@me" --limit "$LIST_CAP" --json "$PR_FIELDS"
  # The hosting service drops a direct request once the user reviewed, so PRs
  # with a cc-review review by the user at an older head come back as
  # re-reviews (FR-004); on the user's own PR such a marker does not count,
  # as for reviewed_at_head
  gh_json "$reviewed" gh pr list --state open --search "reviewed-by:@me" --limit "$LIST_CAP" --json "$PR_FIELDS"
  warn_cap "$requested"
  warn_cap "$reviewed"
  refetch_truncated_reviews "$requested"
  refetch_truncated_reviews "$reviewed"
  jq -s --arg user "$user" --arg marker "$MARKER" '
    (.[1] | map(select(.headRefOid as $h |
      (.author.login != $user and any(.reviews[]?; .author.login == $user
        and ((.body // "") | contains($marker)) and .commit.oid != $h))
      or any(.reviews[]?; .author.login == $user and ((.body // "") | contains($marker))
        and ((.body // "") | contains("<!-- cc-review-incomplete:v1 -->")))))) as $rereview
    | (.[0] | map(. + {reasons:["review_requested"]}))
      + ($rereview | map(. + {reasons:["reviewed"]})) | unique_by(.number)' "$requested" "$reviewed" > "$candidates"
  classify "$candidates" "$user" "$limit"
}

# The GraphQL search of bulk triage: the user's open PRs with their review
# threads, so unresolved threads are counted without one call per PR
TRIAGE_QUERY='
  query($q: String!) {
    search(query: $q, type: ISSUE, first: 100) {
      issueCount
      nodes {
        ... on PullRequest {
          number title state isDraft headRefOid headRefName baseRefName updatedAt isCrossRepository
          author { login }
          headRepository { name owner { login } }
          reviewThreads(first: 100) { totalCount pageInfo { hasNextPage hasPreviousPage } nodes { isResolved } }
        }
      }
    }
  }'

# A separate bounded root alias preserves ownership when the latest-reply
# window omits the finding. Truncated decisive history stays incomplete.
REVIEWER_QUERY='query BulkActionContext($owner: String!, $repo: String!, $number: Int!) {
  repository(owner:$owner,name:$repo) { pullRequest(number:$number) {
    number title state isDraft headRefOid headRefName baseRefName updatedAt isCrossRepository author { login }
    headRepository { name owner { login } }
    reviews(last:20) { totalCount pageInfo { hasNextPage hasPreviousPage } nodes { body author { login } commit { oid } } }
    reviewRequests(first:100) { totalCount pageInfo { hasNextPage hasPreviousPage } nodes { requestedReviewer { ... on User { login } } } }
    reviewThreads(last:20) { totalCount pageInfo { hasNextPage hasPreviousPage } nodes {
      id isResolved path line
      rootComment: comments(first: 1) { nodes { id databaseId body updatedAt author { login __typename }
        originalCommit { oid } pullRequestReview { body author { login } commit { oid } } } }
      comments(last: 10) { totalCount pageInfo { hasNextPage hasPreviousPage } nodes {
        id databaseId body updatedAt author { login __typename } originalCommit { oid }
        pullRequestReview { body author { login } commit { oid } }
      } }
    } }
  } }
}'

do_triage() {
  local usage="Usage: bulk-select.sh triage [--search <q>] [--limit <n>] --user <login>"
  local query="" limit=10 user=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --search) [ $# -ge 2 ] || { echo "$usage" >&2; exit 2; }
        query="$2"; shift 2 ;;
      --limit) [ $# -ge 2 ] || { echo "$usage" >&2; exit 2; }
        limit="$2"; shift 2 ;;
      --user) [ $# -ge 2 ] || { echo "$usage" >&2; exit 2; }
        user="$2"; shift 2 ;;
      *) echo "$usage" >&2; exit 2 ;;
    esac
  done
  [ -n "$user" ] || { echo "Error: --user is required" >&2; exit 2; }
  [[ "$limit" =~ ^[0-9]+$ ]] && [ "$limit" -gt 0 ] || { echo "Error: --limit must be a positive integer, got '$limit'" >&2; exit 2; }
  [ -z "$query" ] || check_query "$query"
  selection_context

  local repo result candidates threadless rest out reviewed detail err n record
  repo=$(tmpfile); result=$(tmpfile); candidates=$(tmpfile); rest=$(tmpfile); out=$(tmpfile)
  printf '%s' "$BULK_REPOSITORY" > "$repo"
  gh_json "$result" gh api graphql -f query="$TRIAGE_QUERY" \
    -f q="repo:$(cat "$repo") is:pr is:open author:@me${query:+ $query}"
  if [ "$(jq '.data.search.issueCount // 0' "$result")" -gt 100 ]; then
    selection_warning "the search matched more than 100 of your open PRs; only the first 100 were considered (narrow it with --search)"
  fi
  jq -e '.data.search.nodes | type == "array"' "$result" >/dev/null || {
    echo "Error: required author PR evidence is unavailable" >&2; exit 1;
  }
  jq --arg user "$user" '[.data.search.nodes[]? | select(.number != null and .author.login == $user)
    | . + {reviews: [],reasons:["authored"]}]' \
    "$result" > "$candidates"
  reviewed=$(tmpfile); detail=$(tmpfile); err=$(tmpfile)
  if ! try "$err" gh pr list --state open --search "reviewed-by:@me${query:+ $query}" --limit 100 --json "$PR_FIELDS" > "$reviewed"; then
    if grep -qiE 'HTTP 401|authentication|not logged in|gh auth login' "$err"; then
      echo "Error: GitHub authentication is unavailable: $(tail -n 1 "$err")" >&2; exit 1
    fi
    selection_warning "reviewer PR discovery unavailable; reviewer triage may be incomplete: $(tail -n 1 "$err")"
    printf '[]\n' > "$reviewed"
  fi
  jq -e 'type == "array"' "$reviewed" >/dev/null || { echo "Error: reviewed PR discovery is unavailable" >&2; exit 1; }
  if [ "$(jq 'length' "$reviewed")" -ge 100 ]; then
    selection_warning "reviewed PR discovery reached 100 entries; narrow with --search"
  fi
  for n in $(jq -r --arg user "$user" '.[] | select(.author.login != $user) | .number' "$reviewed"); do
    record=$(tmpfile)
    if try "$err" gh api graphql -f query="$REVIEWER_QUERY" -f owner="${BULK_REPOSITORY%/*}" \
        -f repo="${BULK_REPOSITORY#*/}" -F number="$n" > "$detail" \
        && jq -e --argjson n "$n" '.data.repository.pullRequest | type=="object" and .number==$n' "$detail" >/dev/null; then
      jq '[.data.repository.pullRequest + {reasons:["reviewed"]}]' "$detail" > "$record"
    else
      selection_warning "PR #$n reviewer detail unavailable; assessment incomplete"
      jq --argjson n "$n" '[.[] | select(.number==$n) | . + {reviewThreads:null,reasons:["reviewed"]}]' "$reviewed" > "$record"
    fi
    jq -s '.[0]+.[1] | unique_by(.number)' "$candidates" "$record" > "$rest"
    cp "$rest" "$candidates"
  done
  classify "$candidates" "$user" "$limit" false triage
}

case "${1:-}" in
  review)
    shift; do_review "$@" ;;
  triage)
    shift; do_triage "$@" ;;
  check-query)
    [ $# -eq 2 ] || { echo "Usage: bulk-select.sh check-query <q>" >&2; exit 2; }
    check_query "$2" ;;
  *)
    echo "Usage: bulk-select.sh {review|triage} [--all-open | --search <q>] [--limit <n>] --user <login> | check-query <q>" >&2
    exit 2 ;;
esac
