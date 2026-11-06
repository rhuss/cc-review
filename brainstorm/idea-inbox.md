# Idea Inbox

Ideas captured from code reviews for future brainstorming.

### goal-alignment-skip-behavior

- **Source**: triage
- **Date**: 2026-08-03
- **Reference**: PR rhuss/cc-spex#51 (051-extract-cc-review)
- **Summary**: The spec's user story 1 mentions goal-alignment as a review perspective but doesn't explicitly state it should be skipped when no PR context exists. The behavior is defined in research.md R-005 and tasks.md T015b but not in the spec itself.

> CodeRabbit flagged that FR-003 lists goal-alignment as a required perspective, while the no-PR flow has no defined behavior for it. The downstream artifacts (research.md, plan, tasks) already handle this correctly by skipping goal-alignment without PR context. Consider adding an explicit note to the spec's acceptance scenarios or FR-003 stating that goal-alignment is skipped gracefully when no PR body/issue metadata is available.


### spec-completeness

- **Source**: triage
- **Date**: 2026-08-03
- **Reference**: PR rhuss/cc-spex#51 (051-extract-cc-review)
- **Summary**: Spec and documentation artifacts don't fully reflect implementation decisions around triage removal and skip behaviors.

> When extracting/removing features, update all spec-level references, not just code-level ones. Pattern detected from 3 CodeRabbit findings about gaps between what the spec describes and what the code implements.

### reviewer-schema-single-source

- **Source**: deep-review
- **Date**: 2026-10-13
- **Reference**: 004-reviewer-plugins
- **Summary**: Frontmatter rules live twice, in the jq validator and in reviewer.schema.json, which no code or test reads; the reserved-name list is copied into the script, schema, docs and data model.

> Adding a field or flag means editing four or five places with nothing catching drift. A test that validates fixtures against the schema, or compares the schema's reserved list with CC_REVIEW_RESERVED_NAMES, would keep one source honest.

### goals-report-section-contract

- **Source**: deep-review
- **Date**: 2026-10-13
- **Reference**: 004-reviewer-plugins
- **Summary**: The report's Goal Delivery section is keyed on the generic `goals` context block but assumes goal-alignment's own table output.

> A contributed reviewer declaring `context: [goals]` would trigger the section without producing those tables. A reviewer-declared report-section contract would remove the last reviewer-shaped assumption from the review command.

### command-finding-path-validation

- **Source**: deep-review
- **Date**: 2026-10-13
- **Reference**: 004-reviewer-plugins
- **Summary**: Findings from command reviewers carry a `file` taken verbatim from external tool output and feed the autonomous fix loop without a containment check.

> LLM-backed tools read the untrusted diff and could be steered to emit absolute or `..` paths. Dropping findings whose file is absolute, has a `..` segment, or is not in CHANGED_FILES before the fix loop would close this.

### deterministic-command-output-parsing

- **Source**: deep-review
- **Date**: 2026-10-13
- **Reference**: 004-reviewer-plugins
- **Summary**: The `json` and `delimited` formats have no deterministic converter, so the orchestrator must read whole tool output; detection also runs for reviewers later disabled by config or --no-external.

> A shipped parse-command-output.sh for json/delimited would keep tool output out of the orchestrator's context, and passing config-disabled names to discovery would skip their network auth probes.

### timeout-process-group-detach

- **Source**: deep-review
- **Date**: 2026-10-13
- **Reference**: 004-reviewer-plugins
- **Summary**: The perl timeout backend now leaves the caller's process group like coreutils timeout, so a harness interrupt no longer reaches a running tool; it stops at its own bound.

> Recording the timeout wrapper's PID so the orchestrator can send TERM (now forwarded to the tool's group) would allow prompt cancellation of slow external reviewers.

### bulk-worktrees-outside-tree

- **Source**: deep-review
- **Date**: 2026-10-25
- **Reference**: 005-bulk-review-triage
- **Summary**: Bulk worktrees and run state live inside the user's working tree, and finished or abandoned runs are kept forever with no retention.

> Tools that ignore nested .gitignore files (linters, test runners, IDE indexers) see full nested checkouts while a run keeps them; placing worktrees under the git common dir and offering a prune option for old runs would bound disk use and avoid that.

### explicit-prs-canonical-equivalence-test

- **Source**: deep-review
- **Date**: 2026-11-06
- **Reference**: 012-inbox-tour-orchestration
- **Summary**: The explicit `--prs` selector test asserts only `.assessment.review.eligible == true`, not that the explicit path's assessment equals the canonical `pr_actions.py assess` output. SC-004/FR-018 ("no separate selection authority that could diverge") would be more strongly pinned by a canonical-equivalence assertion like `test_bulk_select_shared_roles_and_scope`.

> A single-field truthiness check would still pass if the explicit path's assessment diverged in role/reason/exclusion from the canonical assessor.

### uncertain-certainty-fixture-coverage

- **Source**: deep-review
- **Date**: 2026-11-06
- **Reference**: 012-inbox-tour-orchestration
- **Summary**: No inbox snapshot fixture item exercises the "Uncertain"/"Inferred" certainty branch (every assessment has `uncertain: false`), so `test_certainty_values_are_known` is a near-tautology. Add an attention item with `uncertain: true` to give the uncertain-responsibility report branch (FR-003) concrete coverage.

> A report/collector change that mishandled uncertain items would have no fixture to surface it.

### user-defined-named-profiles

- **Source**: presentation prep
- **Date**: 2026-11-06
- **Reference**: review/core/scripts/resolve-config.sh (profile lookup)
- **Summary**: `--profile <name>` only resolves bundled profiles in `review/config/profiles/` (quick, thorough, ci); a user or project cannot add their own named profile.

> Look up `<name>.yml` in the project config directory and the user config directory first, then fall back to the bundled profiles, so a team can ship `--profile security-audit` with its repo. Open points: precedence when a project profile shadows a bundled name, listing all available profiles (with their source) in the "unknown profile" error, and whether `init` should scaffold an example profile. Today's workaround is `--config path/to/profile.yml`.

### comment-voice-and-template-overrides

- **Source**: presentation prep
- **Date**: 2026-11-06
- **Reference**: review/core/templates/reviewer-voice.md, review/core/commands/review.md (7.5f, 7.5i), review/config/config-template.yml (`pr_posting.voice_profile`)
- **Summary**: `pr_posting.voice_profile` is written by `init` but never read; the posting step always loads the bundled reviewer-voice.md. That file mixes two concerns (prose voice and comment structure), and the summary layout is hard-coded in review.md, so neither tone nor layout can be adjusted without editing the plugin.

> Split the concerns. (1) Voice: make `pr_posting.voice_profile` select the cc-prose voice used to word comments, defaulting to the bundled `reviewer` voice; keep only tone guidance in the voice file. (2) Layout: add separate settings such as `pr_posting.comment_template` and `pr_posting.summary_template` that point to a project or user file and fall back to the bundled layout. Keep the what/why/fix elements, the source footer and the run-id marker mandatory regardless of template, since they carry the comments' value and the follow-up machinery depends on the marker. Validate custom templates for the required placeholders before posting.

### critic-merge-weak-upgrade

- **Source**: presentation prep
- **Date**: 2026-11-06
- **Reference**: review/core/commands/review.md (Verdict Application, Severity Calibration)
- **Summary**: The critic merge is meant to resolve disagreement toward the lower severity, but a Calibrator upgrade is applied unconditionally, even to a finding the Skeptic marked `weak`.

> The rules cover confirmed + downgrade (downgrade wins) and weak without calibration (drop one level), but a weak finding with a calibrated severity above the original is raised. Either clamp: a `weak` finding never ends above its original severity, or require the Skeptic to confirm before any upgrade. Add a fixture with a weak finding plus an upgrade so the rule is tested. Rare in practice (the Calibrator almost never upgrades), but the talk claims "lower severity wins".

### skeptic-never-removes

- **Source**: presentation prep
- **Date**: 2026-11-06
- **Reference**: review/core/agents/meta-skeptic.md, brainstorm/13-skeptic-false-positives.md
- **Summary**: The Skeptic is supposed to refute findings against the code, but across 6 local runs (128 findings) and the OpenShell runs it removed 0 findings and only marked some as weak, while the user held back 29 findings by hand.

> How it works today: it receives each finding with the reviewer's rationale, confidence and source, reads the cited range plus 20 lines of context, tries to refute it, and answers confirmed, weak or false-positive (false-positive needs cited counter-evidence; confirmed needs nothing). Likely causes: anchoring on the reviewer's narrative, no burden of proof for "confirmed", same model family as the reviewers. Candidate fixes (blind refutation, reachability proof for Critical/Important, cross-vendor second skeptic, a labeled eval set from the OpenShell outcomes) are collected in brainstorm #13.

### enforce-locked-edit-fields

- **Source**: deep-review
- **Date**: 2026-11-06
- **Reference**: 011-review-draft-approval
- **Summary**: FR-016 forbids an approval-time edit from changing paths, lines, the pinned commit or the run marker, but only the LLM instructions enforce it.

> `review_draft.py assemble` could compare the locked fields per slot id against the previous payload of the same inputs key and refuse a change, so the restriction holds by construction like the labels do.
