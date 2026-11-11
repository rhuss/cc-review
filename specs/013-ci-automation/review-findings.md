# Unattended CI code review

Spec: [spec.md](spec.md). Reviewed 2026-11-11. All stages executed inline under the repository's restriction on Codex subagents.

## Spec compliance

| Requirement | Implementation evidence | Assessment |
|---|---|---|
| FR-001 | core commands delegate single unattended invocations to commands/unattended.md; harness adapters forward the flag | Compliant |
| FR-002 | ci.py Coordinator.prepare/finish, structured proposal validation, always-run workflow finalizer and failure summaries | Compliant; service outages/cancellation remain visibly failed runs until recovery |
| FR-003 | validate_proposal/publish enforce COMMENT, checks, bot-thread IDs and configured labels; no close mutation | Compliant |
| FR-004 | route/select_requests and independent trigger/command settings | Compliant |
| FR-005 | exact whole-comment grammar, eyes acknowledgement, current collaborator permission and original-comment recheck | Compliant |
| FR-006 | fix validation and push_fix use explicit writer comment, same repo, exact parent, regular-file modes and non-force ref update | Compliant |
| FR-007 | default-branch/pinned checkout only, fork guidance and explicit authorized review, tool-free model | Compliant |
| FR-008 | shared repository/item concurrency, trusted marker freshness, bounded sweep selection and bot suppression | Compliant; GitHub pending-job coalescing is recovered by sweeps |
| FR-009 | updated sticky status comment, step summaries and actionable attention reasons including untouched human thread IDs | Compliant |
| FR-010 | workflow/base-action pass-through for API/OAuth/federation/gateway/AWS/Google; private credential materialization and cleanup | Compliant; live provider acceptance remains follow-up |
| FR-011 | validated resource bounds, empty model tool set, max-turns and model step timeout | Compliant |
| FR-012 | ci skill/core management workflow, install helper, diagnostics, manifest flow, label/secret provisioning and smoke-dispatch instructions | Compliant; browser steps are explicit |
| FR-013 | App/GITHUB_TOKEN setup, preserved settings/caller additions, schema refusal and managed disable/removal | Compliant |
| FR-014 | operation entries include fingerprint/state/run identity/link/freshness; result markers recover partial publication | Compliant |

Functional implementation coverage: 14/14. This is code/spec review coverage, not proof of live provider or App execution.

## Deep review

Six perspectives were reviewed inline: correctness, architecture, security, production readiness, test quality and goal alignment. No unresolved findings remain after the following fixes:

- Preserve caller customization while updating both immutable refs.
- Preserve executable modes and refuse symlink/nonregular fix targets.
- Reuse the running status comment when final evidence refresh fails.
- Match exact workflow run IDs when excluding this run's pending checks.
- Handle deleted authors and deleted fork repositories without crashing.
- Supply bounded trusted project guidance and current fix-file contents.
- Reject structured output from failed/timed-out model steps.
- Acknowledge commands during selection, before worker queuing.
- Accept provider version suffixes while rejecting model values that look like flags.
- Require an assessment classification and an outcome for every unresolved bot thread.

Regression tests cover these cases, plus routing/authorization, forged markers, human-thread refusal, failed checks, missing outcomes, replay and an actual prepare/finish CLI round trip with a fake GitHub transport. No paid model result is simulated as a live validation pass.

External review: CodeRabbit was attempted but returned reauthentication_required. Copilot is disabled in configuration. A nested Codex reviewer was not launched under the repository's subagent restriction. These limits are disclosed rather than counted as independent review evidence.

## Remaining validation

Live GitHub Actions/provider/App/fork acceptance is tracked separately; see [issue #17](https://github.com/rhuss/cc-review/issues/17). No production installation or secrets were changed by this implementation session.
