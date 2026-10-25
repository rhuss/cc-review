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
# Triage selects the user's own open PRs (narrowed by --search) that have at
# least one unresolved review thread; the others are excluded as
# no-open-threads.
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
    echo "Warning: the PR list reached $LIST_CAP entries; PRs beyond it were not considered (narrow the selection with --search)" >&2
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
  local file="$1" user="$2" limit="$3" keep_drafts="${4:-false}"
  jq --arg user "$user" --arg marker "$MARKER" --argjson limit "$limit" --arg proto "$(origin_protocol)" \
    --argjson keep_drafts "$keep_drafts" '
    def reviewed_at_head: .headRefOid as $h | .author.login as $pr_author
      | any(.reviews[]?; ((.body // "") | contains($marker)) and .commit.oid == $h
          and (.author.login != $pr_author or .author.login == $user));
    def seed: {
      number, title,
      author: .author.login,
      head_ref: .headRefName,
      base_ref: .baseRefName,
      head_repo_url: ((.headRepositoryOwner.login // .headRepository.owner.login) as $o | .headRepository.name as $n
        | if $o and $n then
            (if $proto == "ssh" then "git@github.com:\($o)/\($n).git" else "https://github.com/\($o)/\($n).git" end)
          else null end),
      is_cross_repo: (.isCrossRepository // false),
      authored_by_user: (.author.login == $user)
    };
    sort_by(.updatedAt, .number)
    | if $keep_drafts then map(.isDraft = false) else . end
    | (map(select(.isDraft)) | map({number, title, reason: "draft"})) as $drafts
    | (map(select((.isDraft | not) and reviewed_at_head)) | map({number, title, reason: "reviewed-at-head"})) as $at_head
    | map(select((.isDraft | not) and (reviewed_at_head | not))) as $open
    | {
        selected: ($open[:$limit] | map(seed)),
        excluded: ($at_head + $drafts + ($open[$limit:] | map({number, title, reason: "over-limit"})))
      }' "$file"
}

do_review() {
  local mode=default query="" limit=10 user=""
  while [ $# -gt 0 ]; do
    case "$1" in
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

  local requested reviewed candidates
  requested=$(tmpfile); reviewed=$(tmpfile); candidates=$(tmpfile)
  case "$mode" in
    all-open)
      gh_json "$candidates" gh pr list --state open --limit "$LIST_CAP" --json "$PR_FIELDS"
      warn_cap "$candidates"
      refetch_truncated_reviews "$candidates"
      classify "$candidates" "$user" "$limit"
      return ;;
    search)
      check_query "$query"
      # gh pr list keeps the search inside the current repository
      gh_json "$candidates" gh pr list --state open --search "$query" --limit "$LIST_CAP" --json "$PR_FIELDS"
      warn_cap "$candidates"
      refetch_truncated_reviews "$candidates"
      classify "$candidates" "$user" "$limit" "$(drafts_wanted "$query")"
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
    (.[1] | map(select(.headRefOid as $h | .author.login != $user and any(.reviews[]?;
      .author.login == $user and ((.body // "") | contains($marker)) and .commit.oid != $h)))) as $rereview
    | .[0] + $rereview | unique_by(.number)' "$requested" "$reviewed" > "$candidates"
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
          number title isDraft headRefOid headRefName baseRefName updatedAt isCrossRepository
          author { login }
          headRepository { name owner { login } }
          reviewThreads(first: 100) { pageInfo { hasNextPage } nodes { isResolved } }
        }
      }
    }
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

  local repo result candidates threadless rest out
  repo=$(tmpfile); result=$(tmpfile); candidates=$(tmpfile); rest=$(tmpfile); out=$(tmpfile)
  gh_json "$repo" gh repo view --json nameWithOwner -q .nameWithOwner
  gh_json "$result" gh api graphql -f query="$TRIAGE_QUERY" \
    -f q="repo:$(cat "$repo") is:pr is:open author:@me${query:+ $query}"
  if [ "$(jq '.data.search.issueCount // 0' "$result")" -gt 100 ]; then
    echo "Warning: the search matched more than 100 of your open PRs; only the first 100 were considered (narrow it with --search)" >&2
  fi
  # A PR with more than 100 threads may have its unresolved ones on a later
  # page: count it as having one, so it is triaged rather than dropped. Only
  # the user's own PRs are kept, whatever the query matched (FR-007).
  jq --arg user "$user" '[.data.search.nodes[]? | select(.number != null and .author.login == $user)
    | . + {unresolved: (([.reviewThreads.nodes[]? | select(.isResolved | not)] | length)
        + (if .reviewThreads.pageInfo.hasNextPage then 1 else 0 end)), reviews: []}]' \
    "$result" > "$candidates"
  # PRs without an unresolved thread have nothing to triage (FR-007)
  threadless=$(jq -c 'sort_by(.updatedAt, .number) | map(select(.unresolved == 0)) | map({number, title, reason: "no-open-threads"})' "$candidates")
  jq 'map(select(.unresolved > 0))' "$candidates" > "$rest"
  classify "$rest" "$user" "$limit" "$(drafts_wanted "$query")" > "$out"
  jq --argjson none "$threadless" '.excluded = $none + .excluded' "$out"
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
