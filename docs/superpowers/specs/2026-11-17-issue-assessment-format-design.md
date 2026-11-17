# Readable Issue Assessments and Status Comments

Date: 2026-11-17
Status: approved 2026-11-17

## Intent

Issue assessments posted by cc-review (CI and local unattended runs) and the
drafts shown by manual `/cc-review:issue` must be readable by people and must
show the judgments a maintainer cares about:

- Can we infer the use case: who tries to do what, in which situation?
- Is the why clear: what pain or consequence results?
- For a bug: is it a real bug, verified where possible?
- For a feature: does it come from a real pain point with a concrete example,
  rather than something the reporter anticipates?
- When the concrete example is missing: ask politely for one real-world use
  case, and stop there.
- When it is present: judge how severe the use case is, and think about other
  ways the use case could be met.

The trigger was the live smoke test (#17, #18): the posted reply was decent, but
the maintainer reasoning landed as one run-on paragraph in the status comment,
and neither text made the judgments above visible.

## Goals

- One posted comment per assessment: a friendly reply to the reporter on top,
  then an `### Assessment` section with the judgments under fixed, plain labels.
- The same format in CI, local `issue --unattended`, and the manual draft.
- Wording shaped by cc-prose (CI: pinned humanizer guidance in the prompt;
  manual: the exposed `prose:humanizer` skill), with dash repair as the net.
- A status comment people can read: one compact table, deterministic outcome
  text, the model's reasoning only in the run's step summary.

- Bugs are checked against the actual code in both modes: CI gets read-only
  access to the default-branch checkout for assessments.

## Non-goals

- Running code or reproducing bugs. Code is read, never executed, in both modes.
- Code access for PR review, triage or fix in this change (possible later, base
  branch only, never the PR head).
- Changing PR review output. The new rules live in a new template, so the
  PR reviewer prompt (which pastes `need-and-fit.md`) is unaffected.
- Posting from manual `/cc-review:issue`. It still only drafts.
- Removing providers is not part of this design. The maintainer decided to keep
  only `anthropic` (API key) and `gateway` (API key plus base URL); dropping
  `oauth`, `vertex`, `bedrock` and `federation` is a separate cleanup.

## Anti-goals

- A form-like wall of fields. Labels without content are omitted.
- Solution sketches, severity or alternatives when no concrete example exists.
  That reads as pre-judging and invites anticipated features.
- Claiming a bug is verified when only docs were read.
- Format drift between runs or between CI and manual mode.

## Constraints

- The CI model today has no tools and sees: the issue snapshot (body, up to 50
  comments), README/CONTRIBUTING/AGENTS/CLAUDE from the default branch, the
  bundled templates, and cc-prose humanizer text. This design adds read-only
  file tools for `assess`, limited to the default-branch checkout `_target`.
  Default-branch code is trusted; GitHub's `pull_request_target` rule only
  forbids running untrusted PR code, which stays true (no PR checkout, no
  shell, no network, no GitHub token).
- The API key is in the model process's environment. On Linux a file reader
  could read it from `/proc/self/environ`, so file access must be confined to
  `_target` and everything else denied.
- Every GitHub mutation goes through the deterministic publisher in `ci.py`,
  which validates the structured proposal first and fails closed.
- Callers pin cc-review by commit, so old pins keep the old schema. The local
  unattended path always runs current code. No cross-version schema support is
  needed.
- The hidden status marker (`<!-- cc-review:ci:v1 {...} -->`) drives
  idempotency and must keep working for existing status comments.
- No em or en dashes in posted text.

## Approaches

1. **Structured fields, assembled by a shared script (chosen).** The model
   returns the reply plus assessment fields; one renderer puts them under
   fixed headings for CI and manual mode alike. Consistent and testable;
   mirrors review's slots/assemble pattern. Costs a schema change and the
   most code.
2. **Template in the prompt.** The model writes the whole Markdown comment.
   Little code, but headings drift (GLM already ignored a precise label
   instruction once) and nothing is testable.
3. **Structured in CI, template in manual mode.** Two renderers of one format
   that would drift apart.

The maintainer picked 1.

## Design

### Assessment fields

For `assess`, the proposal carries `body` (the reply to the reporter) and a
new required `assessment` object:

| Field | Type | Meaning |
|---|---|---|
| `kind` | `bug` \| `feature` \| `question` \| `other` | What the issue is |
| `use_case` | string | Who tries to do what, in which situation. Empty when it cannot be inferred |
| `why` | string | The pain or consequence. Empty when unclear |
| `concrete_example` | boolean | The issue describes a real situation that happened, not an anticipated one |
| `check.result` | see below | Outcome of the bug check or need check |
| `check.note` | string | What was checked, against which source, and what it showed |
| `severity` | `low` \| `medium` \| `high` \| null | How much the use case hurts |
| `severity_reason` | string | One or two sentences of grounds |
| `alternatives` | string[] | Other ways to meet the use case, including existing workarounds |
| `fit` | string | Whether the need belongs in this project, with the source (README, CONTRIBUTING, existing behavior). Empty when not judged |
| `recommendation` | `pursue` \| `needs_evidence` \| `direction` \| `decline` | Same keys as `labels` in `ci.yml` |
| `recommendation_reason` | string | One or two sentences: why this recommendation |
| `limits` | string | Evidence that could not be inspected. Empty when none |

`check.result` values: for `bug`, `confirmed`, `contradicted` or
`unverified`; for `feature`, `real_need`, `anticipated` or `unclear`; for
`question`/`other`, null.

The label comes from `recommendation` (`config.labels[recommendation]`). The
proposal's `labels` field is no longer used for `assess`; the publisher rejects
an `assess` proposal that still sends one that disagrees with the
recommendation.

### Judgment rules

A new template `templates/issue-assessment.md` holds these rules (my call: a
separate file, because `review.md` pastes all of `need-and-fit.md` into the PR
goal-alignment reviewer). `need-and-fit.md` stays unchanged and still applies to
issues. `issue.md` and the CI prompt read both.

- **Classify** the issue as bug, feature, question or other.
- **Use case and why:** infer them from the whole conversation; leave a field
  empty instead of inventing it.
- **Bug check:** read the code paths and docs for the reported behavior.
  `confirmed` only when the code (file and line cited in `check.note`) shows
  the defect; `contradicted` when code or docs show the behavior is intended,
  or the reported path does not exist; otherwise `unverified`, with
  `check.note` naming what was read and what is missing. The reporter's logs
  or claims alone never confirm a bug.
- **Need check:** `real_need` when the issue shows a pain point that actually
  happened, with an example; `anticipated` when it describes a possible future
  situation; `unclear` otherwise.
- **No concrete example (features, question, other):** the reply asks politely
  for one real-world case (the task, the obstacle, the consequence). Severity
  stays null, alternatives stay empty, and the recommendation is not `pursue`.
- **Bugs (my call):** the gate is reproduction detail instead of a use-case
  example. Without steps (what was done, what was expected, what happened) or
  a `confirmed` check, the reply asks for those steps, severity stays null and
  the recommendation is not `pursue`. A `confirmed` bug may be pursued without
  a feature-style use case.
- **Fit:** judge with `need-and-fit.md` and record it in `fit` with its source.
- **Recommendation reason:** always state why, in `recommendation_reason`, so a
  `decline` or `direction` never appears without grounds (my call; the builder
  check showed the field list had no place for it).
- **Example present:** rate severity with grounds (blocked work, workaround
  cost, how many users plausibly hit it), and list other ways to meet the use
  case, including existing features or workarounds, before endorsing the
  proposed solution.

### Validation (publisher, deterministic)

`validate_proposal` for `assess` additionally enforces:

- `assessment` present, all fields of the right type, strings bounded
  (for example 2,000 characters each, at most 5 alternatives).
- `check.result` allowed for the `kind`.
- The gate: for `feature`/`question`/`other`, `concrete_example` false or
  `use_case` empty implies `severity` null, `alternatives` empty and
  `recommendation` not `pursue`. For `bug`, the same holds unless
  `check.result` is `confirmed` or `concrete_example` is true (steps given).
- `recommendation_reason` non-empty.
- `severity` non-null requires a non-empty `severity_reason`.
- `recommendation` is a configured label key.

A failed rule becomes `needs_attention` with a reason that names the rule;
nothing is posted.

### Rendered comment

A new shared module `review/core/scripts/assessment.py` provides
`render(body, assessment, config)` and a CLI
(`python3 -B assessment.py render --input <file.json> [--config <ci.yml>]`)
printing the Markdown. `ci.py` imports it. Example with an example present:

```markdown
<reply to the reporter>

### Assessment

**Type:** Feature request
**Use case:** Maintainers debugging an odd CI assessment want to know which writing guidance shaped it.
**Why:** Without it they cannot tell a model problem from a missing cc-prose checkout.
**Real need:** Yes. The reporter hit this while validating v1.6.1.
**Severity:** Low. It slows debugging but blocks nothing.
**Other ways to solve it:**
- Print the cc-prose commit in the run's step summary only.
- Record it in the status comment's hidden marker.

**Fits the project:** Yes. `docs/CI.md` documents `status` as the place to inspect a CI installation.
**Recommendation:** Pursue (`cc-review:pursue`). Small, bounded, and it makes CI output easier to trust.

<sub>Assessed by cc-review. Not inspected: docs/CI.md, issue #16.</sub>
```

Without a concrete example, the section shows Type, Use case ("Not clear
yet" when empty), Why, the need or bug check, and Recommendation; Severity and
alternatives are omitted. Labels shown per kind: "Bug check" for bugs (with
"Confirmed", "Not confirmed by the sources read", "Contradicted"), "Real need"
for features ("Yes", "Not shown yet", "Unclear"), nothing for question/other.
The footer appears only with non-empty `limits`, plus the result marker the
publisher already appends.

Dash repair runs on `body` and on every string field before rendering.

### CI and local unattended flow

- **Code access (assess only).** The model step allows `Read`, `Grep` and
  `Glob` for `assess`, confined to the absolute path of `_target` with
  Claude Code permission rules; every other path is denied, including
  `/proc`, `runner.temp` and the cc-review/cc-prose checkouts. Other
  operations keep `--tools ""`. The prompt tells the model where the checkout
  is and that it is read-only evidence. The turn and time limits stay as
  configured. A workflow step or test proves a read outside `_target` fails.
  Local `issue --unattended` runs in the user's own Claude session and reads
  the verified local checkout, as manual mode does.
- `PROPOSAL_SCHEMA` adds the `assessment` object (enums as above,
  `recommendation` limited to the configured keys like `labels` today).
- The prompt's assess instruction is replaced by the judgment rules above in
  short form, plus "write `body` for the reporter, put judgments in
  `assessment`".
- `publish` for `assess` posts `render(...)` instead of the raw body and
  applies the label derived from `recommendation`.
- `unattended.md` describes the new proposal shape for `issue --unattended`.

### Manual flow (`/cc-review:issue`)

Step 3 uses the new judgment rules, reading code read-only for the bug check
as it already may. Step 5 writes the reply and the assessment
fields to a private JSON file in `ASSESS_TMP`, runs the cc-prose humanizer on
the reply and the free-text fields (wording only), renders with
`assessment.py render`, and shows the rendered comment in full as the reply
draft. A private section for the maintainer keeps coverage, material
uncertainties and any pending maintainer question (step 4); the step 3
contribution sketch moves into `alternatives` and the reply. Still no posting.

### cc-prose

CI already loads the pinned humanizer into the prompt; its rules now apply to
the reply and every free-text assessment field. Manual mode invokes the
exposed humanizer skill on the same texts. The bundled maintainer voice stays
the fallback.

### Status comment

```markdown
### cc-review CI

| Action | Result | Updated | Log |
|---|---|---|---|
| assess | Assessment posted, labeled `cc-review:pursue` | 2026-11-17 10:00 UTC | [run](...) |
| review | Needs attention: checks are still pending. Rerun with `/cc-review review` once they pass. | 2026-11-17 11:12 UTC | [run](...) |

<details><summary>Commands</summary>

`/cc-review review`, `/cc-review triage`, `/cc-review assess`, `/cc-review fix`, `/cc-review help`. Writers may request actions; fixes require a same-repository PR.
</details>

<!-- cc-review:ci:v1 {...} -->
```

- The heading stays `### cc-review CI` (my call): older pinned CI versions only
  recognize a status comment starting with it, and a renamed heading would make
  them post a second status comment and assess again.
- Rows sorted by `updated_at`, newest first.
- Completed rows show a deterministic outcome from the publisher: assess
  "Assessment posted, labeled `x`"; review "Review posted"; triage "N bot
  threads answered, M resolved"; fix "Fix pushed as `abc1234`"; help "Command
  list shown below" plus the `<details>` block. Skipped and running rows show
  their state.
- `needs_attention` and `skipped` rows show their reason prefixed with "Needs
  attention:" or "Skipped:", whether the publisher or the model wrote it (my
  call: the model's remedy is what the maintainer needs to act), capped at
  300 characters and dash-repaired.
- For completed rows, the model's `reason` goes only to the step summary.
- The marker JSON keeps its schema; entries gain an `outcome` string. Entries
  written by older code (no `outcome`) render from `state` alone.
- Table cells escape `|` and newlines.

## Testing

- Unit: tool confinement (prompt/workflow args allow only `_target`; a CI
  smoke step or test shows a read outside fails); render for each kind, with and without example, empty limits; field
  validation rules; derived label; dash repair per field; status table
  rendering, sorting, escaping, old entries without `outcome`; prompt content.
- Existing CI tests updated for the schema change.
- Full suite, `make validate`, actionlint.
- Live, after merge: new test issues through this repository's CI: a feature
  without an example, a feature with one, and a bug that the code confirms.

## Left to the builder

- Exact wording of fixed labels and outcome strings within the style above.
- String length bounds.
- Whether `assessment.py` also exposes a `validate` CLI for manual mode.
- How the manual flow names its private JSON file.
