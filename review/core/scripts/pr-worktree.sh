#!/usr/bin/env bash
# pr-worktree.sh - Isolated, detached checkouts of pull requests
#
# Usage:
#   pr-worktree.sh add <pr> <sha> <path> [<base_ref>]
#   pr-worktree.sh remove <path>
#   pr-worktree.sh local-ahead <branch> <sha> [<head-repo-url>]
#   pr-worktree.sh push <path> <url> <branch> <expected-sha>
#   pr-worktree.sh head <pr>
#   pr-worktree.sh is-pr-branch <pr>
#
# Runs in the invoking repository (the current directory). The user's branch,
# index and working tree are never touched: worktrees are detached at the PR
# head, and pushes go from the worktree to the PR branch, never with --force.
#
# Exit codes: 0 ok, 1 failure, 2 usage error, 75 hosting-service rate limit
# (stderr "Error: RATE_LIMITED").

set -euo pipefail

_TMPFILES=()
_cleanup_tmp() { rm -f ${_TMPFILES[@]+"${_TMPFILES[@]}"}; }
trap _cleanup_tmp EXIT

tmpfile() {
  local f
  f=$(mktemp); _TMPFILES+=("$f")
  printf '%s' "$f"
}

SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# try
# shellcheck source=rate-limit.sh
. "$SCRIPT_DIR/rate-limit.sh"

last_line() {
  tail -n 1 "$1" 2>/dev/null || true
}

# remove_worktree <path>: unregisters and deletes a worktree, or deletes a
# leftover directory that is no longer a registered worktree
remove_worktree() {
  local path="$1"
  if ! git worktree remove --force --force "$path" 2>/dev/null && [ -e "$path" ]; then
    if [ -d "$path/.git" ]; then
      echo "Error: refusing to delete $path: it is a repository, not a worktree" >&2
      exit 1
    fi
    rm -rf "$path"
  fi
  git worktree prune
}

do_add() {
  [ $# -ge 3 ] && [ $# -le 4 ] || { echo "Usage: pr-worktree.sh add <pr> <sha> <path> [<base_ref>]" >&2; exit 2; }
  local pr="$1" sha="$2" path="$3" base="${4:-}" err
  [[ "$pr" =~ ^[0-9]+$ ]] || { echo "Error: PR number must be a positive integer, got '$pr'" >&2; exit 2; }
  err=$(tmpfile)
  remove_worktree "$path"
  mkdir -p "$(dirname "$path")"
  # pull/<n>/head works for fork PRs too; the base ref keeps origin/<base>
  # current for the diff
  local refspecs=("pull/$pr/head")
  [ -n "$base" ] && refspecs+=("+refs/heads/$base:refs/remotes/origin/$base")
  if ! try "$err" git fetch -q origin "${refspecs[@]}"; then
    echo "Error: cannot fetch PR #$pr: $(last_line "$err")" >&2
    exit 1
  fi
  git cat-file -e "$sha^{commit}" 2>/dev/null || {
    echo "Error: commit $sha of PR #$pr is not available after fetching pull/$pr/head" >&2
    exit 1
  }
  if ! try "$err" git worktree add -q --detach "$path" "$sha"; then
    echo "Error: cannot create worktree for PR #$pr at $path: $(last_line "$err")" >&2
    exit 1
  fi
  (cd "$path" && pwd)
}

do_remove() {
  [ $# -eq 1 ] || { echo "Usage: pr-worktree.sh remove <path>" >&2; exit 2; }
  remove_worktree "$1"
}

# repo_id <url>: "owner/name" of a repository URL (https, ssh or a local
# path), lowercased and without .git, so URLs of one repository compare equal
repo_id() {
  printf '%s' "$1" | sed -e 's|/*$||' -e 's|\.git$||' | tr ':' '/' \
    | awk -F/ 'NF >= 2 { print tolower($(NF - 1) "/" $NF) }'
}

# tracks_repo <branch> <head-repo-url>: true when the local branch's upstream
# remote (push remote first) points at the given repository. A branch with
# the same name in another repository (a fork PR from "main" versus the
# user's own "main") is not the PR's branch.
tracks_repo() {
  local branch="$1" want remote url
  want=$(repo_id "$2")
  [ -n "$want" ] || return 1
  for remote in "$(git config --get "branch.$branch.pushRemote" 2>/dev/null || true)" \
                "$(git config --get "branch.$branch.remote" 2>/dev/null || true)"; do
    [ -n "$remote" ] && [ "$remote" != . ] || continue
    url=$(git config --get "remote.$remote.url" 2>/dev/null || true)
    [ -n "$url" ] && [ "$(repo_id "$url")" = "$want" ] && return 0
  done
  return 1
}

do_local_ahead() {
  [ $# -ge 2 ] && [ $# -le 3 ] || { echo "Usage: pr-worktree.sh local-ahead <branch> <sha> [<head-repo-url>]" >&2; exit 2; }
  local branch="$1" sha="$2" head_url="${3:-}"
  if ! git show-ref --verify --quiet "refs/heads/$branch"; then
    echo 0
    return
  fi
  # Cross-repository PR: only a local branch tracking the PR's head repository
  # is the PR's branch
  if [ -n "$head_url" ] && ! tracks_repo "$branch" "$head_url"; then
    echo 0
    return
  fi
  git rev-list --count "$sha..refs/heads/$branch" || {
    echo "Error: cannot compare local branch $branch with $sha" >&2
    exit 1
  }
}

do_push() {
  [ $# -eq 4 ] || { echo "Usage: pr-worktree.sh push <path> <url> <branch> <expected-sha>" >&2; exit 2; }
  local path="$1" url="$2" branch="$3" expected="$4" head remote err out
  err=$(tmpfile)
  out=$(tmpfile)
  head=$(git -C "$path" rev-parse HEAD) || { echo "Error: $path is not a worktree" >&2; exit 1; }
  if ! try "$err" git -C "$path" ls-remote "$url" "refs/heads/$branch" > "$out"; then
    if grep -qiE '403|permission|denied' "$err"; then echo "DENIED"; return; fi
    echo "Error: cannot read $branch from $url: $(last_line "$err")" >&2
    exit 1
  fi
  remote=$(cut -f1 "$out" | head -n 1)
  # The remote already has our commit: a push completed before an interruption
  if [ "$remote" = "$head" ]; then
    echo "PUSHED $head"
    return
  fi
  if [ "$remote" != "$expected" ]; then
    echo "STALE"
    return
  fi
  if try "$err" git -C "$path" push -q "$url" "HEAD:refs/heads/$branch"; then
    echo "PUSHED $head"
    return
  fi
  if grep -qiE 'non-fast-forward|fetch first|\[rejected\]' "$err"; then
    echo "STALE"
  elif grep -qiE '403|permission|denied|declined' "$err"; then
    echo "DENIED"
  else
    echo "Error: push to $branch failed: $(last_line "$err")" >&2
    exit 1
  fi
}

do_head() {
  [ $# -eq 1 ] || { echo "Usage: pr-worktree.sh head <pr>" >&2; exit 2; }
  local err out
  err=$(tmpfile)
  out=$(tmpfile)
  if ! try "$err" gh pr view "$1" --json headRefOid -q .headRefOid > "$out"; then
    echo "Error: cannot read PR #$1: $(last_line "$err")" >&2
    exit 1
  fi
  cat "$out"
}

do_is_pr_branch() {
  [ $# -eq 1 ] || { echo "Usage: pr-worktree.sh is-pr-branch <pr>" >&2; exit 2; }
  local current err out head_url
  current=$(git symbolic-ref --short -q HEAD) || exit 1
  err=$(tmpfile)
  out=$(tmpfile)
  if ! try "$err" gh pr view "$1" --json headRefName,isCrossRepository,headRepository,headRepositoryOwner > "$out"; then
    echo "Error: cannot read PR #$1: $(last_line "$err")" >&2
    exit 1
  fi
  [ "$current" = "$(jq -r '.headRefName // ""' "$out")" ] || return 1
  # A fork PR's branch name says nothing about the user's branch of that name
  if [ "$(jq -r '.isCrossRepository // false' "$out")" = true ]; then
    head_url=$(jq -r '(.headRepositoryOwner.login // .headRepository.owner.login // "") as $o
      | (.headRepository.name // "") as $n | if $o != "" and $n != "" then "https://github.com/\($o)/\($n).git" else "" end' "$out")
    tracks_repo "$current" "$head_url"
  fi
}

case "${1:-}" in
  add)
    shift; do_add "$@" ;;
  remove)
    shift; do_remove "$@" ;;
  local-ahead)
    shift; do_local_ahead "$@" ;;
  push)
    shift; do_push "$@" ;;
  head)
    shift; do_head "$@" ;;
  is-pr-branch)
    shift; do_is_pr_branch "$@" ;;
  *)
    echo "Usage: pr-worktree.sh {add|remove|local-ahead|push|head|is-pr-branch}" >&2
    exit 2 ;;
esac
