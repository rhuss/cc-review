# Issue Assessment

Used by the `issue` command (manual and unattended) and by CI issue assessments, together with `need-and-fit.md`. PR review does not read this file.

The result has two parts: `body`, a friendly reply written for the reporter, and `assessment`, the structured judgments below. A shared renderer puts the reply first and the judgments under fixed labels in an "Assessment" section, so never repeat headings or labels in `body`, and never put judgments only in `body`.

## Judgments

1. **Kind.** Classify the issue as `bug` (existing behavior is wrong), `feature` (new or changed behavior is wanted), `question`, or `other`.
2. **Use case.** Who is trying to do what, in which situation. Infer it from the whole conversation. Leave it empty rather than inventing one.
3. **Why.** The pain or consequence the reporter faces. Leave it empty when it is unclear.
4. **Concrete example.** True only when the issue describes a real situation that actually happened (for a bug: steps, what was expected, what happened). A possible future situation ("this could be useful when...") is not an example.
5. **Check.**
   - Bugs: read the code paths and docs for the reported behavior. `confirmed` only when the code shows the defect, cited with file and line in the note. `contradicted` when code or docs show the behavior is intended, or the reported path does not exist. Otherwise `unverified`, with the note naming what was read and what is missing. The reporter's logs or claims alone never confirm a bug.
   - Features: `real_need` when the issue shows a pain point that actually happened, with an example; `anticipated` when it describes a possible future need; `unclear` otherwise. The note says what shows it.
   - Questions and other: result `null`.
6. **The example gate.** Without a concrete example (features, questions, other) or without reproduction steps and a confirmed check (bugs):
   - `body` asks politely for one concrete, real-world case: the task, the obstacle, the practical consequence. For bugs, ask for the steps, what was expected and what happened.
   - `severity` stays `null`, `alternatives` stays empty, and `recommendation` is not `pursue`.
   - Do not sketch a solution.
7. **With an example** (or a confirmed bug):
   - **Severity** `low`, `medium` or `high`, with a reason: is work blocked, how costly is the workaround, how many users plausibly hit it.
   - **Alternatives:** other ways to meet the use case, including existing features or workarounds, before endorsing the proposed solution. At most five, each one sentence.
8. **Fit.** Whether the need belongs in this project, judged with `need-and-fit.md`, with its source (README, CONTRIBUTING, existing behavior).
9. **Recommendation.** One of the configured keys (`pursue`, `needs_evidence`, `direction`, `decline`), always with a one or two sentence reason.
10. **Limits.** Evidence you could not inspect (missing history, files, linked issues). Empty when none.

## Fields

| Field | Value |
|---|---|
| `kind` | `bug`, `feature`, `question` or `other` |
| `use_case` | text, empty when it cannot be inferred |
| `why` | text, empty when unclear |
| `concrete_example` | true or false |
| `check` | `{"result": ..., "note": "..."}` as above |
| `severity` | `low`, `medium`, `high` or null |
| `severity_reason` | text, required when severity is set |
| `alternatives` | list of at most 5 short texts |
| `fit` | text with its source, empty when not judged |
| `recommendation` | a configured classification key |
| `recommendation_reason` | text, never empty |
| `limits` | text, empty when none |

Text fields hold plain sentences: no headings, no labels, no em or en dashes. Keep file paths, identifiers and commands in backticks.
