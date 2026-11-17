# Readable Issue Assessments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Issue assessments post one readable comment (friendly reply plus a structured `### Assessment` section) in CI, local unattended and manual mode; bugs are checked against the code; the status comment becomes a compact table; only API-key providers remain.

**Architecture:** The model returns `body` plus a structured `assessment` object. A new stdlib module `review/core/scripts/assessment.py` validates and renders it; `ci.py` uses it in the publisher and manual `/cc-review:issue` calls its CLI. CI assessments get read-only `Read`/`Grep`/`Glob` confined to the default-branch checkout. The status comment keeps its heading and hidden marker but renders a table from a new per-entry `outcome`.

**Tech Stack:** Python 3.9+ stdlib, Bash, GitHub Actions YAML, Markdown command files, Claude Code CLI flags (`--tools`, `--add-dir`, `--permission-mode`).

**Spec:** `docs/superpowers/specs/2026-11-17-issue-assessment-format-design.md`

## Global Constraints

- No em dashes (U+2014) or en dashes (U+2013) in any posted text, rendered output, docs or command files you write.
- Python: stdlib only, runs with `python3 -B`, Python 3.9 compatible (no `match`, no `X | Y` types).
- Status comment heading stays exactly `### cc-review CI` and the marker stays `<!-- cc-review:ci:v1 {json} -->` with `schema: 1`.
- Providers after Task 1: `anthropic` (secret `ANTHROPIC_API_KEY`) and `gateway` (secret `ANTHROPIC_API_KEY`, variable `CC_REVIEW_ANTHROPIC_BASE_URL`) only.
- Assessment string fields at most 2,000 characters; `alternatives` at most 5 entries of at most 500 characters each.
- Status rows: reasons capped at 300 characters, dash-repaired; `|` escaped as `\|`, newlines collapsed to spaces.
- Code is read, never executed. No PR head checkout. No shell, network or GitHub token for the model.
- Commits end with the trailer `Assisted-By: 🤖 Claude Code`.
- Verification commands: `python3 -B tests/test_ci.py`, `python3 -B tests/test_assessment.py`, `bash tests/run.sh` (about 10 minutes; ends with `N passed, 0 failed`), `make validate`, `actionlint .github/workflows/*.yml`.

## Review Focus

1. An issue with an empty body and no comments: the model leaves `use_case`/`why` empty; render shows "Not clear yet" and omits severity/alternatives, no crash (Task 3 test `test_render_empty_use_case`).
2. A proposal whose legacy `labels` disagree with `assessment.recommendation`: needs attention, nothing posted (Task 4 test `test_assess_labels_must_match_recommendation`).
3. Field text containing `|`, newlines, `<!--`/`-->` or backticks: the status table stays one row per action, and rendered assessment text cannot open an HTML comment (Task 2 `test_status_table_escapes_cells`, Task 3 `test_render_neutralizes_html_comments`).
4. A status comment written by v1.6 (old bullet list, entries without `outcome`): found by `read_status`, rewritten as a table with all entries kept (Task 2 `test_status_upgrades_v16_comment`).
5. The model trying to read outside the checkout (`/proc/self/environ`, the runner temp dir, `$HOME`): denied (Task 5 local confinement check plus `test_assess_tools_confined`).

---

### Task 1: Keep only API-key providers

**Files:**
- Modify: `review/core/scripts/ci.py` (provider check in `load_config` near line 76; `inspect_installation` near lines 685-710)
- Modify: `.github/workflows/cc-review-reusable.yml`, `review/core/templates/ci-workflow.yml`
- Modify: `docs/CI.md` (Identity and Model providers sections), `review/core/commands/ci.md` (Setup step 3)
- Test: `tests/test_ci.py`

**Interfaces:**
- Produces: `PROVIDERS = ('anthropic', 'gateway')` in `ci.py`.

- [ ] **Step 1: Write the failing tests** in `PolicyTests`:
  - `test_removed_providers_are_rejected_with_guidance`: for each of `oauth`, `vertex`, `bedrock`, `federation`, `load_config` on `{"provider": p}` raises `CIError` whose message contains `p` and `anthropic` and `gateway`.
  - `test_model_identifier_supports_version_suffix`: replaces `test_vertex_model_identifier_supports_version_suffix`; `{"provider": "anthropic", "model": "claude-sonnet-4-5@20250929"}` loads.
  - In the doctor test, assert no issue string mentions `OAUTH`, `Vertex`, `Bedrock` or `FEDERATION`.
- [ ] **Step 2: Run** `python3 -B tests/test_ci.py`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement.** `load_config` rejects any provider not in `PROVIDERS` with `CIError("Provider '<p>' is no longer supported; use anthropic (API key) or gateway (API key plus base URL).")` for the four removed names, and the existing "Unsupported provider." otherwise. `inspect_installation` keeps only the `ANTHROPIC_API_KEY` check (anthropic, gateway) and `CC_REVIEW_ANTHROPIC_BASE_URL` (gateway).
  - Reusable workflow: delete the "Materialize Vertex credentials privately" step, the Google file cleanup, `id-token: write`, and the model step's `AWS_*`, `ANTHROPIC_VERTEX_PROJECT_ID`, `CLOUD_ML_REGION`, `GOOGLE_APPLICATION_CREDENTIALS` env, `claude_code_oauth_token`, `anthropic_federation_rule_id`, `anthropic_organization_id`, `anthropic_service_account_id`, `anthropic_workspace_id`, `use_bedrock`, `use_vertex`. Keep every removed `workflow_call` input and secret declared, with `description: Deprecated and ignored (removed provider)`, so v1.6 callers moved by `ci update` (which only rewrites pins) still validate.
  - Caller template: drop `id-token: write` and every removed input/secret line; keep `app_id`, `anthropic_base_url`, `anthropic_api_key`, `app_private_key`.
  - Docs: provider table lists `anthropic` and `gateway` only; remove the cloud OIDC paragraph; `ci.md` step 3 mentions only `ANTHROPIC_API_KEY` and `CC_REVIEW_ANTHROPIC_BASE_URL`.
- [ ] **Step 4: Run** `python3 -B tests/test_ci.py` and `actionlint .github/workflows/cc-review-reusable.yml review/core/templates/ci-workflow.yml`. Expected: OK, no actionlint output. Then `rg -n -i "vertex|bedrock|oauth|federation|google|aws_" review/core docs/CI.md review/core/templates`: hits only in the deprecated input declarations and the rejection message.
- [ ] **Step 5: Commit** `refactor(ci): keep only API-key providers (anthropic, gateway)`.

### Task 2: Status comment as a table

**Files:**
- Modify: `review/core/scripts/ci.py` (`status_body`, `Coordinator.status`, `Coordinator.prepare`, `Coordinator.finish`, `Coordinator.publish`, `summary`)
- Test: `tests/test_ci.py`

**Interfaces:**
- Produces: `status_body(entries: dict) -> str`; `Coordinator.status(snapshot, request, state, reason='', outcome='') -> dict` (returns the stored entry plus `'state'` and `'reason'` keys as today); `Coordinator.publish(request, snapshot, proposal) -> str` returns the outcome text; `finish()` returns `{'state', 'reason'}` where `reason` is the full text for the step summary.
- Consumes: `repair_dashes` (exists in `ci.py`; Task 3 moves it).

- [ ] **Step 1: Write the failing tests:**
  - `test_status_table_renders_outcomes_newest_first`: entries `assess` (completed, `outcome` "Assessment posted, labeled `cc-review:pursue`", updated 2026-11-17 10:00 UTC) and `review` (needs_attention, reason "Checks are still pending.", updated 11:12 UTC) render a body that starts with `### cc-review CI\n`, contains `| Action | Result | Updated | Log |`, has the `review` row before the `assess` row, contains `Needs attention: Checks are still pending.`, `2026-11-17 11:12 UTC`, `[run](`.
  - `test_status_help_shows_commands_once`: an entry `help` (completed) renders the row result "Command list shown below" and exactly one `<details><summary>Commands</summary>` block containing `/cc-review fix`.
  - `test_status_table_escapes_cells`: a reason `"a | b\nc <!-- x -->"` renders as one row with `a \| b c &lt;!-- x --&gt;`, and the reason is cut to 300 characters when longer.
  - `test_status_upgrades_v16_comment`: a comment body in the v1.6 bullet format (build it from a literal string with the `### cc-review CI` heading, a `- **assess**: completed. ...` line and the marker with an entry lacking `outcome`) is found by `read_status`; after `Coordinator.status(..., 'help', ...)` the PATCHed body is a table with both `assess` and `help` rows; the `assess` result cell shows `Completed`.
  - `test_completed_status_keeps_model_reason_out`: `finish` on an assess proposal with `reason` "Long internal reasoning" stores an entry whose rendered row does not contain that text, and `finish()` returns `reason` containing it.
  - Existing tests asserting the old line format (search `assertIn('needs attention'`) are updated to the new text `Needs attention:`.
- [ ] **Step 2: Run** `python3 -B tests/test_ci.py`. Expected: new tests FAIL.
- [ ] **Step 3: Implement.** Row result: completed with `outcome` shows the outcome; completed without shows `Completed`; `skipped` shows `Skipped: <reason>`; `running` shows `Running`; `needs_attention` shows `Needs attention: <reason>`. Time: `datetime.fromtimestamp(updated_at, timezone.utc).strftime('%Y-%m-%d %H:%M UTC')`. Rows sorted by `updated_at` descending. `publish` returns: assess "Assessment posted, labeled `<label>`"; review "Review posted"; triage "<n> bot threads answered, <m> resolved"; fix "Fix pushed as `<sha7>`". `help` stores outcome "Command list shown below". The entry stores `reason` only for non-completed states (capped, repaired); completed entries store `reason: ''`. `doctor`'s attention list keeps reading `entry['reason']`.
- [ ] **Step 4: Run** `python3 -B tests/test_ci.py`. Expected: OK.
- [ ] **Step 5: Commit** `feat(ci): render the status comment as a table with fixed outcomes`.

### Task 3: Shared assessment module

**Files:**
- Create: `review/core/scripts/assessment.py`
- Create: `tests/test_assessment.py`
- Modify: `review/core/scripts/ci.py` (import `repair_dashes` from `assessment`, delete its local copy; keep the name importable as `ci.repair_dashes`)
- Modify: `tests/run.sh` (add `test_assessment_module` next to `test_issue_assessment`, run with `run_test`)

**Interfaces:**
- Produces, in `assessment.py`:
  - `class AssessmentError(ValueError)`; its message names the broken rule.
  - `KINDS = ('bug', 'feature', 'question', 'other')`; `CHECK_RESULTS = {'bug': ('confirmed', 'contradicted', 'unverified'), 'feature': ('real_need', 'anticipated', 'unclear'), 'question': (None,), 'other': (None,)}`; `SEVERITIES = ('low', 'medium', 'high')`.
  - `repair_dashes(text: str) -> tuple[str, int]` (moved unchanged from `ci.py`).
  - `validate(assessment: dict, label_keys) -> dict` raises `AssessmentError`.
  - `repair(body: str, assessment: dict) -> tuple[str, dict, int]` applies `repair_dashes` to `body` and every string field and alternative; returns the total count.
  - `render(body: str, assessment: dict, labels: dict) -> str` (`labels` maps recommendation key to label name).
  - CLI `python3 -B assessment.py render --input FILE [--config CI_YML]`: reads `{"body", "assessment"}`, validates, repairs, prints Markdown; on error prints `Error: <message>` to stderr and exits 1. Without `--config`, label names come from `review/config/ci.yml` next to the core.

- [ ] **Step 1: Write the failing tests** in `tests/test_assessment.py` (unittest, loading the module from `review/core/scripts` like `tests/test_ci.py` loads `ci.py`). Use a fixture `FEATURE` = kind feature, use_case "Maintainers debugging an odd CI assessment want to know which writing guidance shaped it.", why "Without it they cannot tell a model problem from a missing cc-prose checkout.", concrete_example true, check `{result: real_need, note: "The reporter hit this while validating v1.6.1."}`, severity low, severity_reason "It slows debugging but blocks nothing.", alternatives two strings, fit "Yes. `docs/CI.md` documents `status` as the place to inspect a CI installation.", recommendation pursue, recommendation_reason "Small, bounded, and it makes CI output easier to trust.", limits "docs/CI.md, issue #16".
  - `test_render_feature_with_example`: output starts with the body, then `\n\n### Assessment\n\n`; contains in order `**Type:** Feature request`, `**Use case:** Maintainers`, `**Why:** Without`, `**Real need:** Yes. The reporter`, `**Severity:** Low. It slows`, `**Other ways to solve it:**\n- `, `**Fits the project:** Yes.`, ``**Recommendation:** Pursue (`cc-review:pursue`). Small,``, and `<sub>Assessed by cc-review. Not inspected: docs/CI.md, issue #16.</sub>`.
  - `test_render_empty_use_case`: feature, use_case "", concrete_example false, severity null, alternatives [], check `{result: anticipated, note: "..."}`, recommendation needs_evidence: contains `**Use case:** Not clear yet` and `**Real need:** Not shown yet`; does not contain `**Severity:**` or `**Other ways`; no `<sub>` when limits is "".
  - `test_render_bug_labels`: bug with check results confirmed / contradicted / unverified render `**Bug check:** Confirmed.`, `**Bug check:** Contradicted.`, `**Bug check:** Not confirmed by the sources read.`, each followed by the note.
  - `test_render_question_has_no_check_line`: kind question renders neither `Bug check` nor `Real need`.
  - `test_render_neutralizes_html_comments`: a field containing `<!-- cc-review:ci-result:v1 x -->` renders as `&lt;!-- cc-review:ci-result:v1 x --&gt;`.
  - `test_validate_rules`: each of these raises `AssessmentError` mentioning the rule: missing field; kind `bug` with result `real_need`; feature with concrete_example false and severity low; feature with use_case "" and recommendation pursue; bug without confirmed check and concrete_example false with recommendation pursue; severity set with empty severity_reason; empty recommendation_reason; recommendation not in label keys; a 2,001-character field; 6 alternatives. A confirmed bug with concrete_example false and recommendation pursue passes.
  - `test_repair_counts_all_fields`: body and two fields with one em dash each return count 3 and no dashes left.
  - `test_cli_render_and_error`: `subprocess.run([sys.executable, '-B', path, 'render', '--input', f])` prints the Markdown for `FEATURE`; with recommendation pursue and concrete_example false it exits 1 with `Error:` on stderr.
- [ ] **Step 2: Run** `python3 -B tests/test_assessment.py`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** `assessment.py`. Kind labels: bug "Bug report", feature "Feature request", question "Question", other "Other". Recommendation labels: pursue "Pursue", needs_evidence "Needs more evidence", direction "Needs a direction decision", decline "Decline". Real need labels: real_need "Yes.", anticipated "Not shown yet.", unclear "Unclear.". Severity renders capitalized plus the reason. Empty `why` renders "Not clear yet". Severity and alternatives lines appear only when severity is non-null / alternatives non-empty. `fit` line only when non-empty. Free text passes through `str.replace('<!--', '&lt;!--').replace('-->', '--&gt;')`.
- [ ] **Step 4: Run** `python3 -B tests/test_assessment.py` and `python3 -B tests/test_ci.py`. Expected: both OK.
- [ ] **Step 5: Commit** `feat(assess): shared assessment validation and rendering`.

### Task 4: Structured assessments in the CI publisher

**Files:**
- Create: `review/core/templates/issue-assessment.md`
- Modify: `review/core/scripts/ci.py` (`PROPOSAL_SCHEMA`, `proposal_schema`, `validate_proposal`, `publish`, `write_prompt`)
- Modify: `review/core/commands/unattended.md` (issue proposal shape, CI proposal-only paragraph)
- Test: `tests/test_ci.py`

**Interfaces:**
- Consumes: `assessment.validate`, `assessment.repair`, `assessment.render`, `AssessmentError` (Task 3); `publish(...) -> str` (Task 2).
- Produces: proposal field `assessment` for `assess`; `proposal_schema(config)` sets `properties.assessment.properties.recommendation.enum = sorted(config['labels'])`.

- [ ] **Step 1: Write the failing tests** (replace the label-based assess tests with these):
  - `test_assessment_posts_rendered_comment_and_derived_label`: assess proposal with `body` "Thanks for the example." and the Task 3 `FEATURE` assessment posts one comment that starts with "Thanks for the example." and contains `### Assessment` and the result marker; labels POST is `{'labels': ['cc-review:pursue']}`; result state completed; the status row says "Assessment posted, labeled `cc-review:pursue`".
  - `test_assessment_rule_failure_posts_nothing`: same with recommendation pursue and concrete_example false: state needs_attention, reason mentions the rule, no comment besides the status, no labels.
  - `test_assess_labels_must_match_recommendation`: legacy `labels: ['decline']` with recommendation pursue: needs_attention; `labels: ['cc-review:pursue']` with recommendation pursue: completed.
  - `test_assessment_fields_dash_repaired`: an em dash in `why` and in `body` is gone from the posted comment and the status reason mentions `2 dashes replaced`.
  - `test_schema_requires_assessment_keys`: `proposal_schema(config)['properties']['assessment']` has `additionalProperties: False`, requires all twelve fields, and `recommendation.enum == sorted(config['labels'])`.
  - `test_prompt_carries_issue_assessment_rules`: `write_prompt` for assess includes the text of `templates/issue-assessment.md` and of `templates/need-and-fit.md`; for review it includes neither `issue-assessment` rules nor its heading.
- [ ] **Step 2: Run** `python3 -B tests/test_ci.py`. Expected: new tests FAIL.
- [ ] **Step 3: Implement.**
  - `issue-assessment.md`: the "Judgment rules" of the spec verbatim in substance (classify; use case and why; bug check against code with file and line, reporter logs never confirm; need check; the example gate for features/question/other; the reproduction-steps gate for bugs; fit with source; recommendation reason always), plus the field list with meanings, and the rule "write `body` for the reporter; put judgments only in `assessment`; when the gate applies, `body` asks politely for one concrete real-world example (features) or reproduction steps (bugs)".
  - Schema: `assessment` object with the spec's twelve fields (`check` as object `{result, note}`, `result` nullable string enum, `severity` nullable enum, `alternatives` array of strings).
  - `validate_proposal` for assess: `assessment` required; map legacy `labels` names to keys (existing logic), then require `labels` absent or equal to `[recommendation]`; call `assessment.validate(proposal['assessment'], config['labels'])` and convert `AssessmentError` to `CIError(str(error))`; drop the old "exactly one classification label" rule.
  - `publish` for assess: `assessment.repair`, `assessment.render(body, assessment, config['labels'])` + marker, label from `config['labels'][recommendation]`.
  - Dash count from `repair` feeds the existing "N dashes replaced before posting." reason suffix.
  - `write_prompt`: for assess, perspectives are `need-and-fit.md` then `issue-assessment.md`; replace the assess sentence in the fixed prompt with "For assess, follow the issue assessment rules: write `body` for the reporter and the judgments in `assessment`."
  - `unattended.md`: the `issue N --unattended` proposal contains `status`, `reason`, `body` and `assessment` (fields per `templates/issue-assessment.md`); remove `labels` from that sentence; the CI proposal-only list adds `assessment`.
- [ ] **Step 4: Run** `python3 -B tests/test_ci.py`. Expected: OK.
- [ ] **Step 5: Commit** `feat(ci): structured, rendered issue assessments`.

### Task 5: Read-only code access for CI assessments

**Files:**
- Modify: `review/core/scripts/ci.py` (`prepare` runner output, `write_prompt` signature)
- Modify: `.github/workflows/cc-review-reusable.yml` (model step `claude_args`), `ci/action.yml` (new outputs)
- Modify: `docs/CI.md` (analysis paragraph)
- Test: `tests/test_ci.py`

**Interfaces:**
- Produces: `write_prompt(context, directory, prose_dir=None, code_dir=None)`; prepare outputs `tools` (`Read,Grep,Glob` for assess, empty otherwise) and `code_dir` (absolute path of `--project-dir` for assess, empty otherwise), exposed as action outputs `tools` and `code_dir`.

- [ ] **Step 1: Determine the confinement flags locally** (no repository change). In the scratchpad, create `work/` (model cwd), `target/` with a file `inside.txt` containing `INSIDE`, and `outside.txt` containing `OUTSIDE`. From `work/`, run `claude -p "<ask to read ../target/inside.txt, then ../outside.txt, then /etc/hosts and $HOME/.zshrc; report each content or error>" --tools "Read,Grep,Glob" --add-dir "<abs target>" --setting-sources "" --strict-mcp-config --mcp-config '{"mcpServers":{}}' --permission-mode dontAsk --output-format json --max-turns 8` with the EnMaaS gateway env as in earlier smoke tests. Expected: INSIDE is read; the other three are denied. If any outside read succeeds, add `--disallowedTools "Read(//**)" "Grep(//**)" "Glob(//**)"` together with `--allowedTools "Read(<abs target>/**)" "Grep(<abs target>/**)" "Glob(<abs target>/**)"` and rerun until only INSIDE is readable. Record the final flag set in the commit message.
- [ ] **Step 2: Write the failing tests:**
  - `test_assess_tools_confined`: `prepare` for assess with `--project-dir` produces runner output `tools=Read,Grep,Glob` and `code_dir` equal to the absolute project dir; for review, triage and fix both are empty. Read the outputs by setting `GITHUB_OUTPUT` to a temp file and calling `ci.main([...])` with a fake API, or by testing a helper `model_access(operation, project_dir) -> dict` that `prepare` uses.
  - `test_prompt_names_readonly_checkout`: `write_prompt(..., code_dir='/x/_target')` for assess contains `/x/_target` and "read-only"; without `code_dir` it says code was not available.
  - `test_workflow_confines_model_tools`: the reusable workflow text contains `--tools "${{ steps.prepare.outputs.tools }}"`, `--add-dir` with `steps.prepare.outputs.code_dir`, and the flags chosen in Step 1; it no longer contains `--tools ""` hardcoded.
- [ ] **Step 3: Run** `python3 -B tests/test_ci.py`. Expected: new tests FAIL.
- [ ] **Step 4: Implement** the helper, outputs and workflow flags from Step 1. When `tools` is empty the workflow passes `--tools ""` exactly as today (no `--add-dir`).
- [ ] **Step 5: Run** `python3 -B tests/test_ci.py`, `actionlint .github/workflows/cc-review-reusable.yml`. Expected: OK.
- [ ] **Step 6: Commit** `feat(ci): read-only code access for issue assessments`.

### Task 6: Manual `/cc-review:issue` uses the same format

**Files:**
- Modify: `review/core/commands/issue.md` (sections 1, 3, 5, 6)
- Modify: `tests/run.sh` (issue command assertions near line 3943)

**Interfaces:**
- Consumes: `assessment.py render --input FILE` (Task 3); `templates/issue-assessment.md` (Task 4).

- [ ] **Step 1: Write the failing assertions** in the issue-command test function of `tests/run.sh`: `issue.md` contains `templates/issue-assessment.md`, `scripts/assessment.py`, `render --input`, `"$ASSESS_TMP/assessment.json"`, and section 6 removes `assessment.json`.
- [ ] **Step 2: Run** `bash tests/run.sh 2>&1 | tail -3`. Expected: the new assertions FAIL.
- [ ] **Step 3: Edit `issue.md`:**
  - Section 1 verifies `templates/issue-assessment.md` and `scripts/assessment.py` exist.
  - Section 3 applies `templates/issue-assessment.md` after `need-and-fit.md`; for bugs, read the relevant code in the verified checkout read-only and cite file and line; never run it.
  - Section 5: write `{"body": ..., "assessment": {...}}` to `$ASSESS_TMP/assessment.json` with the file-write tool (never a shell literal), shape the reply and the free-text fields with the exposed humanizer (wording only), run `python3 -B '<core>/scripts/assessment.py' render --input "$ASSESS_TMP/assessment.json"`, and show its output in full as the reply draft per "Showing Text to the User". A validation error is fixed and rendered again, never bypassed. A private "For you" part keeps coverage, material uncertainties and any pending maintainer question. Remove the old separate "Maintainer assessment" bullet; the step 3 contribution sketch goes into `alternatives` and the reply.
  - Section 6 also removes `"$ASSESS_TMP/assessment.json"` before `rmdir`.
- [ ] **Step 4: Run** `bash tests/run.sh 2>&1 | tail -1`. Expected: `N passed, 0 failed`.
- [ ] **Step 5: Commit** `feat(issue): manual assessments render the shared format`.

### Task 7: Docs, release prep and live verification

**Files:**
- Modify: `docs/CI.md` (assessment format, status comment), `.github/workflows/cc-review.yml` (this repository's caller)

- [ ] **Step 1: Docs.** `docs/CI.md`: a short "Issue assessments" subsection showing the rendered section and the example gate; the status comment table; read-only code access for assessments. No dashes.
- [ ] **Step 2: Full verification.** Run `make validate`, `bash tests/run.sh 2>&1 | tail -1`, `actionlint .github/workflows/*.yml review/core/templates/ci-workflow.yml`. Expected: `Validation passed`, `N passed, 0 failed`, no actionlint output.
- [ ] **Step 3: Commit and push** the branch to `main` (fast-forward), then update this repository's caller: regenerate it from the template content (no removed inputs, no `id-token`), pin both refs to the pushed commit, actionlint, commit `ci: pin this repository's caller to <sha7>`, push.
- [ ] **Step 4: Live check, with the maintainer's approval of each issue text before creating it** (they are posted under the maintainer's name): a feature without an example, a feature with a concrete example, and a bug that the code confirms. Watch each `issues` run with `gh run watch --exit-status`; read the posted comment and status comment. Expected: rendered `### Assessment` sections matching the gate rules, a code citation in the bug check, the right label, a table status comment, no dashes. A `help` dispatch on #18 shows the upgraded status table.
- [ ] **Step 5: Report** run links and outcomes; ask whether to release as v1.7.0.
