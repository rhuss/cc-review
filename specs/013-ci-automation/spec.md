# Feature Specification: Unattended CI

**Feature Branch**: `014-ci-automation`
**Created**: 2026-11-11
**Status**: Reviewed
**Input**: [Brainstorm and issue #16](https://github.com/rhuss/cc-review/issues/16)

## Overview

Maintainers can run cc-review automatically in their repositories using their own identity and model credentials. Every run finishes without a question and records an outcome. A CI management skill installs and maintains the integration.

## User Scenarios & Testing

### User Story 1 - Receive unattended assistance (Priority: P1)

A maintainer enables automatic PR review, follow-up reviewer triage, and issue assessment.

**Why this priority**: This is the core value of unattended operation.
**Independent Test**: Route representative events and complete one item without interactive input.

**Acceptance Scenarios**:

1. **Given** an enabled same-repository PR event, **When** a PR opens, **Then** a COMMENT review is posted and a terminal outcome is recorded for its head.
2. **Given** a follow-up push, **When** reviewer threads exist, **Then** bot threads are triaged, human threads are left untouched and reported for attention.
3. **Given** an enabled issue event, **When** an issue opens, **Then** an assessment reply and configured triage labels are applied without closing it.
4. **Given** a prompt attempt, failed check, missing outcome, timeout or tool denial, **When** the run terminates, **Then** the item visibly needs attention with a reason and remedy.

### User Story 2 - Request an authorized action (Priority: P1)

Maintainers invoke `/cc-review review`, `triage`, `assess`, `fix` or `help` in item comments.

**Why this priority**: Explicit authorization enables safe fork review and optional fixes.
**Independent Test**: Exercise command authorization across permissions, target types and fork status.

**Acceptance Scenarios**:

1. **Given** a writer, **When** an enabled command is posted, **Then** it is acknowledged and ends with a visible result.
2. **Given** a fork PR, **When** an automatic event arrives, **Then** no secret-bearing code execution occurs and the maintainer sees how to request review.
3. **Given** an authorized maintainer fix on a same-repository PR, **When** it succeeds, **Then** fixes are pushed to the PR branch; a fork fix or unauthorized request is refused.
4. **Given** a disabled or unsupported command, **When** it arrives, **Then** no model action runs and the response explains the restriction.

### User Story 3 - Sweep unfinished work (Priority: P2)

Maintainers run a bounded sweep that processes only unfinished item states.

**Why this priority**: Scheduled recovery covers missed events without repeat billing or duplicate writes.
**Independent Test**: Mix complete, stale, active and new states; verify selection and summary.

**Acceptance Scenarios**:

1. **Given** a matching complete marker or an active run, **When** the sweep selects items, **Then** that item is skipped.
2. **Given** stale or absent completion evidence, **When** the sweep runs, **Then** eligible PR and issue work runs within configured limits, sharing per-item serialization with event and command runs.
3. **Given** failures, **When** the sweep ends, **Then** its run summary lists processed items and attention reasons.

### User Story 4 - Manage CI (Priority: P2)

A repository owner uses `cc-review:ci setup`, `status`, `update`, `disable` and `doctor`.

**Why this priority**: Reusable installation and diagnostics make CI usable across repositories.
**Independent Test**: Generate a setup, inspect its settings, migrate it and disable it in a fixture repository.

**Acceptance Scenarios**:

1. **Given** setup choices, **When** setup completes, **Then** a version-pinned caller and configuration exist, labels and secrets are configured, and a test dispatch result is reported.
2. **Given** an existing installation, **When** status or doctor runs, **Then** triggers, commands, identity, model, recent outcomes, missing secrets, permission errors and missing labels are explained without exposing credentials.
3. **Given** an installation, **When** update or disable runs, **Then** the pin/configuration are migrated or the integration is switched off without deleting unrelated files.

### Edge Cases and Error Handling

- Events emitted by the configured bot never trigger new work.
- Invalid configuration fails before model execution with a precise setting and remedy.
- A changed PR head or conversation invalidates previous completion evidence.
- A canceled or abandoned run cannot leave an indefinitely active item; stale evidence becomes eligible for retry after the configured timeout.
- Very large diffs, exhausted turns, unavailable credentials and rate limits produce attention outcomes without waiting for interaction.
- Repeated events and retries reuse one status surface per item and avoid duplicate completed actions.
- Untrusted comments and repository content are data, never authority to expand permissions or override unattended policy.

## Clarifications

### Session 2026-11-11

- Q: What is the single status surface? → A: One sticky issue/PR conversation comment, updated by the configured bot; separate result reviews/replies retain existing cc-review markers.
- Q: What makes completion current? → A: PR review uses head SHA; triage uses head plus review-thread activity; assessment uses issue body plus non-bot conversation activity. Only bot-authored status evidence is trusted.
- Q: How are abandoned runs retried? → A: Running evidence expires after the per-item timeout plus five minutes; terminal attention states are eligible on a later explicit command or sweep.
- Q: What counts as unattended interaction failure? → A: Question tools are denied; structured result validation requires an explicit terminal outcome. A question or permission request in place of that result fails closed, without heuristic punctuation matching.
- Q: Where do authorized fixes land? → A: Push to the observed same-repository PR branch with a head check; failed verification or changed head withholds the push and records attention.

## Requirements

### Functional Requirements

- **FR-001**: Single-item review, triage and issue commands MUST support `--unattended` and bypass all interactive choices using documented defaults, including preview and posting gates.
- **FR-002**: Every accepted run MUST end as completed, skipped or needs attention with an item, operation, observed state, reason and run link. Missing or invalid outcome evidence and attempted interaction MUST become needs attention.
- **FR-003**: Unattended reviews MUST use COMMENT only; failed checks withhold publication. Triage MUST limit replies/resolution to bot reviewer threads and list human threads for attention. Issue assessment MUST post and apply configured triage labels and MUST NOT close items.
- **FR-004**: The integration MUST route enabled PR open/synchronize, issue open, comment, schedule and manual-dispatch events. Each event and command MUST be independently configurable.
- **FR-005**: Commands MUST be parsed as an exact supported command, acknowledged and authorized using current repository permission. Default access is write/maintain/admin; configurable broader access MUST NOT broaden fix authorization beyond maintainers.
- **FR-006**: Fixes MUST require an explicit maintainer comment command on a same-repository PR and MUST push only to its observed branch after checking for head changes. Automatic events and sweeps MUST NOT fix.
- **FR-007**: Fork automatic events MUST explain the maintainer-command path. Authorized fork review MUST inspect remote content as data and MUST NOT execute fork code in a secret-bearing context.
- **FR-008**: All entry points MUST share per-item concurrency, trusted persistent markers and bot-loop suppression. Sweep MUST skip active/current complete states and obey a configurable item limit.
- **FR-009**: Each item MUST have one reusable status surface. Sweeps MUST publish processed/attention summaries. Attention messages MUST identify a corrective action.
- **FR-010**: Model, credentials and provider MUST be repository-owned. Support API key, OAuth, workload identity, Bedrock, Vertex and a gateway without storing credential values in configuration or logs.
- **FR-011**: The central entry point MUST ship fixed tool permissions, a turn bound, execution timeout and diff-size limit, with visible outcomes on exhaustion.
- **FR-012**: `cc-review:ci` MUST provide setup/status/update/disable/doctor, including pinned workflow generation, secret provisioning, optional GitHub App manifest setup, triage labels and a test dispatch. App setup MUST clearly identify any required browser interaction and resume after installation.
- **FR-013**: Setup MUST offer a named scoped GitHub App identity and a GITHUB_TOKEN fallback. Update MUST preserve user settings and report incompatible versions. Disable MUST support switching triggers off and clean removal of managed files.
- **FR-014**: Markers MUST encode operation, current head/conversation fingerprint, lifecycle state, run identity and freshness. Local runner files MUST NOT be required for cross-run resumption.

### Key Entities

- **CI configuration**: version, independent trigger/command switches, model/provider/identity choices, labels and resource limits.
- **Request**: repository, item, operation, event, actor and current permission, trusted item state.
- **Outcome/status marker**: item operation/state identity, run identity/link, freshness, terminal state and attention remedy.
- **Managed installation**: pinned caller, repository settings, named secrets and labels.

## Success Criteria

### Measurable Outcomes

- **SC-001**: All supported event/command fixtures terminate without interactive input and have a terminal outcome or explicit ignored-event decision.
- **SC-002**: Policy tests demonstrate zero approvals, request-changes reviews, closures, automatic fixes or fork code execution with secrets.
- **SC-003**: Duplicate, overlapping and self-generated event fixtures produce at most one active operation per item and no repeat action for an unchanged completed state.
- **SC-004**: Missing outcomes, prompt attempts and resource exhaustion are visible with a remedy in every tested failure case.
- **SC-005**: Setup produces a valid pinned installation; diagnostics detect every intentionally missing prerequisite; disable prevents all triggers.

## Assumptions and Dependencies

- GitHub Actions and claude-code-action supply execution and repository-owned provider authentication; their supported inputs must be checked during planning.
- A sticky item comment is the default status surface; existing cc-review result markers remain compatible.
- Maintainer means current write, maintain or admin permission.
- Default limits: 10 sweep items, 30 model turns, 15 minutes per item and 100,000 diff bytes; settings can lower or raise bounded values.
- Existing label schemes are preserved through explicit mappings; default assessment labels are created only by setup.
- Hosted services, GitLab, item closure, approval/request-changes and cross-repository dashboards are out of scope.
