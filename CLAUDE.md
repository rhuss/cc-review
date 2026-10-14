# cc-review Development Guidelines

## Technologies

- Bash (POSIX-compatible), Markdown, `jq`, `yq`

## Project Structure

```text
review/                  Plugin directory (distributable, all harnesses)
  .claude-plugin/        Claude Code plugin manifest
  .codex-plugin/         Codex plugin manifest
  skills/                Command shims (Claude Code and Codex)
  opencode/              OpenCode integration (commands + install)
  core/                  Harness-agnostic review engine
    reviewers/           Bundled reviewer plugins (6 prompt, 3 command, gator)
    agents/              Shared preamble + meta-review prompts
    commands/            Command definitions (review.md, init.md, triage.md)
    schemas/             Finding and reviewer frontmatter schemas
    scripts/             Shell utilities
  config/                Default configuration template

speckit/                 Optional spec-kit extension (separate distribution)
```

## Plugin Architecture

The `review/` directory is a single distributable that contains native manifests for Claude Code, Codex, and OpenCode. Each harness reads its own manifest and ignores the others.

Command shims (SKILL.md files) resolve the core directory at runtime and delegate to `core/commands/review.md` or `core/commands/triage.md`. Shims add no review logic.

## SKILL.md Contract

Every command shim must:
1. Resolve the core directory (harness-specific mechanism, then fallbacks)
2. Pass through all user arguments
3. Stay concise (under 50 lines)
