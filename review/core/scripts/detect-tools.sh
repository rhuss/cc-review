#!/usr/bin/env bash

detect_external_tools() {
  local tool status auth_status

  for tool in coderabbit copilot codex; do
    status="false"
    auth_status=""

    if command -v "$tool" >/dev/null 2>&1; then
      status="true"

      case "$tool" in
        coderabbit)
          if ! coderabbit auth status >/dev/null 2>&1; then
            auth_status="not_authenticated"
          fi
          ;;
        copilot)
          # Copilot auth flows through GitHub CLI
          if command -v gh >/dev/null 2>&1 && ! gh auth status >/dev/null 2>&1; then
            auth_status="not_authenticated"
          fi
          ;;
        codex)
          if ! codex --version >/dev/null 2>&1; then
            auth_status="not_authenticated"
          fi
          ;;
      esac
    fi

    printf '%s\n' "$tool:$status:$auth_status"
  done
}

detect_test_command() {
  if [ -f "Makefile" ] && grep -q '^test:' Makefile 2>/dev/null; then
    printf '%s' "make test"
    return
  fi

  if [ -f "package.json" ] && jq -e '.scripts.test' package.json >/dev/null 2>&1; then
    printf '%s' "npm test"
    return
  fi

  if [ -f "go.mod" ]; then
    printf '%s' "go test ./..."
    return
  fi

  if [ -f "pyproject.toml" ] || [ -f "setup.py" ]; then
    printf '%s' "pytest"
    return
  fi

  if [ -f "Cargo.toml" ]; then
    printf '%s' "cargo test"
    return
  fi

  printf ''
}

detect_platform() {
  if ! git rev-parse --git-dir >/dev/null 2>&1; then
    echo "Warning: not a git repository, skipping platform detection" >&2
    printf ''
    return
  fi

  local remote_url
  remote_url="$(git remote get-url origin 2>/dev/null)"

  if [ -z "$remote_url" ]; then
    echo "Warning: no git remote found, skipping platform detection" >&2
    printf ''
    return
  fi

  case "$remote_url" in
    *github.com*) printf '%s' "github" ;;
    *gitlab.com*) printf '%s' "gitlab" ;;
    *) printf '' ;;
  esac
}
