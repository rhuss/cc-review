# Implementation Plan: Review Draft Approval

**Branch**: `011-review-draft-approval` | **Date**: 2026-11-02 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/011-review-draft-approval/spec.md`

## Summary

Every cc-review PR review is drafted before it is posted. A new Python helper (`review_draft.py`) assembles the payload from a slots file using the reviewer fallback template, adds a fact-based attribution statement, renders a preview, lints the draft and fingerprints it. A new Bash script (`post-review.sh`) posts only a payload whose fingerprint matches the approval, after commit, head, duplicate-marker, history and conversation checks. `review.md` Step 7.5 is split into draft, approve and post halves used by single-PR review and by bulk worker (g), which becomes a drafting worker; `bulk.md` apply runs prepare, approve and post passes. Run facts (curation, fix-round test outcomes) are recorded as they happen. The `reviewer-voice.md` examples start with the severity label.

## Technical Context

**Language/Version**: Bash (POSIX-leaning, as existing scripts), Python 3 standard library (as `review_continuity.py` and siblings), Markdown command definitions

**Primary Dependencies**: `jq`, `gh`, existing `platform.sh`, `rate-limit.sh`, `bulk-state.sh`, `review_continuity.py`, `reviewer_activity.py`

**Storage**: JSON and Markdown files in the run's ignored state directories (`$PR_DIR`, `$REVIEW_RUN_DIR`), bulk `state.json`

**Testing**: `tests/run.sh` (plain Bash assertions, `make test`), plus a `tests/test_review_draft.py` unittest module wired through `run_test`, following `test_review_continuity`

**Target Platform**: Claude Code, Codex and OpenCode harnesses running the shared `review/core` engine on macOS/Linux

**Project Type**: Harness-agnostic agent plugin (command Markdown + helper scripts)

**Performance Goals**: Drafting all PRs of a five-PR bulk run finishes before the first preview (SC-006); scripts run in well under a second per draft

**Constraints**: No write API call before approval in interactive modes; posted bytes equal the checked file; no prompts in unattended or non-interactive modes; SKILL.md shims unchanged (CLAUDE.md contract)

**Scale/Scope**: Up to `pr_posting.max_inline_comments` (default 50) inline comments per review; bulk runs of tens of PRs

## Constitution Check

The project constitution (`.specify/memory/constitution.md`) is an unfilled template, so there are no ratified gates. Project rules from `CLAUDE.md` apply instead:

| Rule | Status |
|---|---|
| Review logic lives in `core/`, shims add none | Pass: all changes are in `review/core/` |
| SKILL.md shims stay under 50 lines and unchanged in role | Pass: no shim changes |
| Bash + Markdown + `jq`/`yq` technologies | Pass with note: Python helpers already exist in `core/scripts`; the new helper follows them |

Post-design re-check: unchanged, pass.

## Project Structure

### Documentation (this feature)

```text
specs/011-review-draft-approval/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── scripts.md
│   └── worker-protocol.md
└── tasks.md            (created by /speckit-tasks)
```

### Source Code (repository root)

```text
review/core/
├── commands/
│   ├── review.md            Step 6 facts, 7.5g curation, 7.5 split (draft / approve / post), Worker Mode (f) facts, (g) drafting worker, Step 8 reporting
│   └── bulk.md              Decision drill-down curation flag, Review Decision and Apply: prepare, approve, post passes, withheld status, unattended policy
├── scripts/
│   ├── review_draft.py      NEW: facts-set, assemble, attribution, preview, lint, fingerprint, conversation-diff, inputs-key
│   ├── post-review.sh       NEW: guarded POST of an approved draft
│   ├── bulk-state.sh        withheld status, summary "Needs attention"
│   └── platform.sh          keep author type in fetched snapshots where missing
└── templates/
    └── reviewer-voice.md    examples start with the severity label; rewrite scope note

specs/005-bulk-review-triage/contracts/worker-protocol.md   pointer to the new flow (posting row)
README.md                                                   user-facing note on preview, attribution, withheld

tests/
├── run.sh                   new run_test entries (review_draft, post_review, bulk withheld)
├── test_review_draft.py     NEW unittest module
└── fixtures/review-draft/   NEW slots, facts, drafts with single defects, gh stubs
```

**Structure Decision**: Extend the existing `review/core` engine. Deterministic work moves into two new scripts next to their siblings; the Markdown commands orchestrate and keep LLM work (slot rewrite, edit interpretation) limited to slot text.

## Design Overview

1. **Facts** (FR-010a): `review_draft.py facts-set` is called by 7.5g / bulk drill-down (`curated`) and after every fix-round test run (`executed`).
2. **Draft** (FR-001 to FR-006, FR-007 to FR-011): slots file, slot-only rewrite, `assemble`, `lint`, one redraft, `preview`. Thread actions collected, not performed.
3. **Approve** (FR-015 to FR-020): single-PR after 7.5h; bulk as a separate pass after all drafts. Edits change slots or downgrade the event, then re-assemble. Approval records the fingerprint.
4. **Post** (FR-021 to FR-026): `post-review.sh`; then thread actions per 7.5f with approved bodies.
5. **Unattended / non-interactive** (FR-014, FR-027): same draft and lint, `policy` approval, `withheld` on persistent lint failure.

Risks: `review.md` and `bulk.md` are long, instruction-dense files; the split must keep existing Follow-up Continuity, marker and recovery rules intact. Mitigation: move text, do not paraphrase it; keep the 7.5 sub-step letters so cross-references stay valid; tests assert key phrases exist in the commands (as existing tests do).

## Complexity Tracking

No constitution violations to justify.
