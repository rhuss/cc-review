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

_github_fetch_pr_threads() {
  local pr_number="$1"
  local owner repo
  owner=$(gh repo view --json owner -q '.owner.login')
  repo=$(gh repo view --json name -q '.name')

  local all_threads="[]"
  local has_next="true"
  local cursor=""

  while [ "$has_next" = "true" ]; do
    local after_clause=""
    if [ -n "$cursor" ]; then
      after_clause=", after: \"$cursor\""
    fi

    local query="
      query {
        repository(owner: \"$owner\", name: \"$repo\") {
          pullRequest(number: $pr_number) {
            reviewThreads(first: 100$after_clause) {
              pageInfo {
                hasNextPage
                endCursor
              }
              nodes {
                id
                isResolved
                isOutdated
                comments(first: 100) {
                  nodes {
                    body
                    author { login }
                    databaseId
                    createdAt
                    url
                  }
                }
              }
            }
          }
        }
      }
    "

    local result
    result=$(gh api graphql -f query="$query") || return 1

    local page_threads
    page_threads=$(echo "$result" | jq '.data.repository.pullRequest.reviewThreads.nodes')
    all_threads=$(echo "$all_threads" "$page_threads" | jq -s '.[0] + .[1]')

    has_next=$(echo "$result" | jq -r '.data.repository.pullRequest.reviewThreads.pageInfo.hasNextPage')
    cursor=$(echo "$result" | jq -r '.data.repository.pullRequest.reviewThreads.pageInfo.endCursor')
  done

  echo "$all_threads"
}

_github_post_reply() {
  local pr_number="$1"
  local comment_id="$2"
  local body="$3"

  gh api \
    "repos/{owner}/{repo}/pulls/$pr_number/comments/$comment_id/replies" \
    -f body="$body" \
    --silent
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

_github_check_ci() {
  local pr_number="$1"
  local output
  output=$(gh pr checks "$pr_number" 2>&1) || true

  if echo "$output" | grep -q "fail"; then
    echo "failing"
  elif echo "$output" | grep -q "pending\|queued\|in_progress\|waiting"; then
    echo "pending"
  else
    echo "passing"
  fi
}
