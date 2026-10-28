#!/usr/bin/env bash

detect_platform() {
  local remote_url
  remote_url=$(git remote get-url origin 2>/dev/null) || {
    echo "No git remote 'origin' found" >&2
    return 1
  }

  case "$remote_url" in
    *github.com*) echo "github" ;;
    *gitlab.com*) echo "gitlab" ;;
    *)
      echo "Unrecognized platform for remote: $remote_url" >&2
      return 1
      ;;
  esac
}

fetch_pr_threads() {
  local pr_number="$1"
  local platform
  platform=$(detect_platform) || return 1

  case "$platform" in
    github) _github_fetch_pr_threads "$pr_number" ;;
    gitlab)
      echo "GitLab support not yet implemented" >&2
      return 1
      ;;
  esac
}

post_reply() {
  local pr_number="$1"
  local comment_id="$2"
  local body="$3"
  local platform
  platform=$(detect_platform) || return 1

  case "$platform" in
    github) _github_post_reply "$pr_number" "$comment_id" "$body" ;;
    gitlab)
      echo "GitLab support not yet implemented" >&2
      return 1
      ;;
  esac
}

resolve_thread() {
  local thread_id="$1"
  local platform
  platform=$(detect_platform) || return 1

  case "$platform" in
    github) _github_resolve_thread "$thread_id" ;;
    gitlab)
      echo "GitLab support not yet implemented" >&2
      return 1
      ;;
  esac
}

check_ci() {
  local pr_number="$1"
  local platform
  platform=$(detect_platform) || return 1

  case "$platform" in
    github) _github_check_ci "$pr_number" ;;
    gitlab)
      echo "GitLab support not yet implemented" >&2
      return 1
      ;;
  esac
}

post_review() {
  local owner="$1"
  local repo="$2"
  local pr_number="$3"
  local json_payload_file="$4"
  local platform
  platform=$(detect_platform) || return 1

  case "$platform" in
    github) _github_post_review "$owner" "$repo" "$pr_number" "$json_payload_file" ;;
    gitlab)
      echo "GitLab support not yet implemented" >&2
      return 1
      ;;
  esac
}

fetch_reviews() {
  local owner="$1"
  local repo="$2"
  local pr_number="$3"
  local platform
  platform=$(detect_platform) || return 1

  case "$platform" in
    github) _github_fetch_reviews "$owner" "$repo" "$pr_number" ;;
    gitlab)
      echo "GitLab support not yet implemented" >&2
      return 1
      ;;
  esac
}

parse_diff_hunks() {
  local pr_number="$1"
  local platform
  platform=$(detect_platform) || return 1

  case "$platform" in
    github) _github_parse_diff_hunks "$pr_number" ;;
    gitlab)
      echo "GitLab support not yet implemented" >&2
      return 1
      ;;
  esac
}

_github_fetch_pr_threads() {
  local pr_number="$1"
  local owner repo
  owner=$(gh repo view --json owner -q '.owner.login') || {
    echo "Failed to determine repository owner" >&2
    return 1
  }
  repo=$(gh repo view --json name -q '.name') || {
    echo "Failed to determine repository name" >&2
    return 1
  }
  if [ -z "$owner" ] || [ -z "$repo" ]; then
    echo "Could not extract owner/repo from 'gh repo view'" >&2
    return 1
  fi

  local all_threads="[]"
  local has_next="true"
  local cursor=""
  local max_pages=20
  local page_count=0

  while [ "$has_next" = "true" ]; do
    page_count=$((page_count + 1))
    if [ "$page_count" -gt "$max_pages" ]; then
      echo "WARNING: Pagination limit ($max_pages pages) reached, results may be incomplete" >&2
      break
    fi

    local cursor_arg=""
    if [ -n "$cursor" ]; then
      cursor_arg="-f cursor=$cursor"
    fi

    local result
    result=$(gh api graphql -f query='
      query($owner: String!, $repo: String!, $number: Int!, $cursor: String) {
        repository(owner: $owner, name: $repo) {
          pullRequest(number: $number) {
            reviewThreads(first: 100, after: $cursor) {
              pageInfo {
                hasNextPage
                endCursor
              }
              nodes {
                id
                isResolved
                isOutdated
                path
                line
                comments(first: 100) {
                  totalCount
                  pageInfo { hasNextPage hasPreviousPage }
                  nodes {
                    id
                    databaseId
                    body
                    author { login }
                    createdAt
                    updatedAt
                    originalCommit { oid }
                    pullRequestReview { author { login } body }
                  }
                }
              }
            }
          }
        }
      }
    ' -f owner="$owner" -f repo="$repo" -F number="$pr_number" $cursor_arg) || return 1

    local page_threads
    page_threads=$(printf '%s' "$result" | jq '.data.repository.pullRequest.reviewThreads.nodes')
    all_threads=$(printf '%s\n%s' "$all_threads" "$page_threads" | jq -s '.[0] + .[1]')

    has_next=$(printf '%s' "$result" | jq -r '.data.repository.pullRequest.reviewThreads.pageInfo.hasNextPage')
    cursor=$(printf '%s' "$result" | jq -r '.data.repository.pullRequest.reviewThreads.pageInfo.endCursor')
  done

  printf '%s' "$all_threads"
}

_github_post_reply() {
  local pr_number="$1"
  local comment_id="$2"
  local body="$3"

  gh api \
    "repos/{owner}/{repo}/pulls/$pr_number/comments/$comment_id/replies" \
    -f body="$body" \
    --jq '.id'
}

_github_resolve_thread() {
  local thread_id="$1"

  local query='
    mutation($threadId: ID!) {
      resolveReviewThread(input: { threadId: $threadId }) {
        thread { isResolved }
      }
    }
  '

  gh api graphql \
    -f query="$query" \
    -f threadId="$thread_id" \
    --silent
}

_github_post_review() {
  local owner="$1"
  local repo="$2"
  local pr_number="$3"
  local json_payload_file="$4"

  if [ ! -f "$json_payload_file" ]; then
    echo "ERROR: Payload file not found: $json_payload_file" >&2
    return 1
  fi

  gh api \
    "repos/$owner/$repo/pulls/$pr_number/reviews" \
    --method POST \
    --input "$json_payload_file" 2>&1

  return $?
}

_github_fetch_reviews() {
  local owner="$1"
  local repo="$2"
  local pr_number="$3"

  local all_reviews="[]"
  local has_next="true"
  local cursor=""
  local max_pages=20
  local page_count=0

  while [ "$has_next" = "true" ]; do
    page_count=$((page_count + 1))
    if [ "$page_count" -gt "$max_pages" ]; then
      echo "WARNING: Pagination limit ($max_pages pages) reached, results may be incomplete" >&2
      break
    fi

    local cursor_arg=""
    if [ -n "$cursor" ]; then
      cursor_arg="-f cursor=$cursor"
    fi

    local result
    result=$(gh api graphql -f query='
      query($owner: String!, $repo: String!, $number: Int!, $cursor: String) {
        repository(owner: $owner, name: $repo) {
          pullRequest(number: $number) {
            reviews(first: 100, after: $cursor) {
              pageInfo {
                hasNextPage
                endCursor
              }
              nodes {
                databaseId
                body
                author { login }
                commit { oid }
                comments(first: 100) {
                  nodes {
                    databaseId
                    path
                    line
                    body
                  }
                }
              }
            }
          }
        }
      }
    ' -f owner="$owner" -f repo="$repo" -F number="$pr_number" $cursor_arg) || return 1

    local page_reviews
    page_reviews=$(printf '%s' "$result" | jq '.data.repository.pullRequest.reviews.nodes')
    all_reviews=$(printf '%s\n%s' "$all_reviews" "$page_reviews" | jq -s '.[0] + .[1]')

    has_next=$(printf '%s' "$result" | jq -r '.data.repository.pullRequest.reviews.pageInfo.hasNextPage')
    cursor=$(printf '%s' "$result" | jq -r '.data.repository.pullRequest.reviews.pageInfo.endCursor')
  done

  # A review comment has no field pointing at its thread, so join the thread
  # node IDs (needed by resolve_thread) in from the PR's review threads by
  # comment databaseId. Without threads the reviews are returned unchanged.
  local threads
  if ! threads=$(_github_fetch_pr_threads "$pr_number"); then
    echo "WARNING: could not fetch review threads for PR #$pr_number; reviews are returned without thread IDs, so fixed threads cannot be resolved" >&2
    threads="[]"
  fi
  if printf '%s' "${threads:-[]}" | jq -e 'any(.[]; (.comments.nodes | length) >= 100)' >/dev/null 2>&1; then
    echo "WARNING: a review thread on PR #$pr_number has 100 or more comments; comments past the first 100 get no thread ID" >&2
  fi
  printf '%s\n%s' "$all_reviews" "${threads:-[]}" | jq -s '
    (reduce (.[1][] | . as $t | .comments.nodes[] | {key: (.databaseId | tostring), value: $t.id}) as $e
      ({}; .[$e.key] = $e.value)) as $by_comment
    | .[0] | map(.comments.nodes |= map(
        . + (if $by_comment[.databaseId | tostring] then {pullRequestReviewThread: {id: $by_comment[.databaseId | tostring]}} else {} end)))'
}

_github_parse_diff_hunks() {
  local pr_number="$1"

  gh pr diff "$pr_number" 2>/dev/null | awk '
    /^diff --git/ {
      file = ""
    }
    /^\+\+\+ b\// {
      file = substr($0, 7)
    }
    /^@@ / {
      if (file != "") {
        hunk = $3
        sub(/^\+/, "", hunk)
        split(hunk, parts, ",")
        start = parts[1] + 0
        if (parts[2] != "") {
          count = parts[2] + 0
        } else {
          count = 1
        }
        end = start + count - 1
        printf "%s\t%d\t%d\n", file, start, end
      }
    }
  ' | jq -R -s '
    split("\n") | map(select(length > 0)) |
    map(split("\t") | {file: .[0], start: (.[1] | tonumber), end: (.[2] | tonumber)}) |
    group_by(.file) |
    map({key: .[0].file, value: map({start: .start, end: .end})}) |
    from_entries
  '

  return $?
}

_github_check_ci() {
  local pr_number="$1"
  local output
  if ! output=$(gh pr checks "$pr_number" 2>&1); then
    echo "error"
    return 0
  fi

  if echo "$output" | grep -q "fail"; then
    echo "failing"
  elif echo "$output" | grep -q "pending\|queued\|in_progress\|waiting"; then
    echo "pending"
  else
    echo "passing"
  fi
}
