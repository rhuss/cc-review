# Implementation Plan: Unattended CI

**Branch**: `014-ci-automation` | **Date**: 2026-11-11 | **Spec**: [spec.md](spec.md)

## Summary

Ship a versioned reusable workflow with a prepare/finalize composite helper. A Python coordinator selects events, gathers bounded remote evidence, validates structured model proposals and performs policy-limited GitHub writes. The model has no tools or GitHub token; all evidence is supplied as quoted JSON. A concise CI skill manages repository installation.

## Technical Context

- Python 3.9+ standard library, existing gh CLI, yq v4 for YAML conversion, Bash and Markdown; no new runtime Python dependencies.
- GitHub Actions Linux runners; GitHub API via gh subprocess argument arrays, never shell interpolation.
- Persistent state: one bot-authored sticky comment containing per-operation versioned JSON markers. Ephemeral JSON snapshots carry model input and validation context.
- Tests: unittest fixtures and fake GitHub transport integrated into `make test`; workflow syntax with actionlint; `make validate` for manifests.
- Limits: default 10 sweep items, 30 turns, 15 minutes, 100000 diff bytes. Explicit bounded numeric validation.

## Constitution Check

The constitution is an unfilled template and imposes no concrete principles. Follow CLAUDE.md: distributable code under review/, concise harness shims, harness-neutral core, Python matching existing collectors. AGENTS.md requires make validate and commit/push. No violations before or after design.

## Project Structure

- `review/core/scripts/ci.py`: config validation, pure routing/state/policy functions, gh transport and prepare/finalize/select CLI.
- `review/config/ci.yml`: defaults and caller template in `review/core/templates/ci-workflow.yml`.
- `ci/action.yml`: prepare/finalize policy helper used around the pinned base-action in the reusable workflow.
- `.github/workflows/cc-review.yml`: reusable select + per-item matrix workers, shared item concurrency and always-run finalizer.
- `review/core/commands/unattended.md`: shared single-item contract and CI proposal mode.
- `review/core/commands/ci.md`, `review/skills/ci/SKILL.md`, OpenCode and Spec Kit adapters: installation lifecycle.
- `tests/test_ci.py`: routing, provenance, freshness, authorization, bounded outcomes, publisher restrictions, setup generation, fake transport integration.
- `docs/CI.md`, README links: setup/provider/identity/operations guidance.

## Design

1. Select from trusted default-branch configuration and event metadata. Comment commands are exact whole-line matches. Current collaborator permission comes from API, never author association. Ignore configured bot. Fork automatic events create an explanatory terminal status; only explicit authorized read-only review is permitted. Follow-up pushes select triage then review.
2. Reusable workflow serializes every item under the same repository/number group with cancel-in-progress false. Sweep selection checks trusted status markers and defers active/current complete operations. Worker rechecks under concurrency lock. Selection has no LLM secrets; only workers receive provider credentials.
3. Prepare fetches current PR/issue, all relevant comments/threads and check state, computes head/conversation fingerprint, writes running status and bounded evidence/prompt files. Never check out PR code. Tool-free model analysis inspects the supplied diff and bundled review/triage/assessment guidance; no question, shell, network or mutation tools. Use --json-schema for a proposal carrying terminal status and operation-specific actions.
4. Finalize validates identity, shape, bounds, unchanged state and operation policy before writes. Reviews use COMMENT; failed/pending checks withhold. Triage replies/resolutions reference exact bot thread IDs only; human threads force attention. Assessment posts a marked reply plus configured labels without closing. Fix proposals contain bounded file changes, only from maintainer comment on same-repository branches; Git data APIs create a child commit and non-force update rejects races without executing code.
5. Every worker finalizes even after model failure or timeout. Abandoned running markers expire after timeout plus five minutes. Sticky status retains separate operation completion entries; publication markers make partial retries idempotent. Summaries name outcomes and remedies.
6. Setup generates a caller pinned to a selected commit, config and optional App manifest. Skill provisions secrets through gh stdin/files, creates mapped labels, handles browser-required App registration/install, dispatches/watches a smoke test. Doctor/status inspect metadata only. Update preserves settings; disable changes only managed files.

## Interfaces

`load_config(path) -> dict`; `route(event_name, event, config, permission) -> list[request]`; `fingerprint(snapshot, operation, bot) -> str`; `eligible(marker, request, now, timeout) -> bool`; `validate_proposal(request, snapshot, proposal, config) -> dict`.

`GitHub.call(method, path, payload=None) -> JSON`; `select`, `prepare`, `finish`, `setup`, `status`, `doctor`, `update`, `disable` CLI subcommands. Request JSON carries item number, operation, source, actor, permission and fork status; worker must refresh sensitive metadata itself.

## Validation

Test invalid config, all event/command combinations, permissions, spoofed and stale markers, bot loops, pending/failed checks, missing/interaction results, human triage, fork fix denial, changed heads, duplicate publication recovery, bounded sweeps and managed-file preservation. Run offline tests first; live provider/App integration requires target repository credentials and is documented in quickstart. No paid live run without configured credentials.
