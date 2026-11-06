# Research: Review Draft Approval

All Technical Context items were resolved from the existing code base; no external research was needed.

## R-001: Where the review text is produced today

- **Finding**: Step 7.5 of `review/core/commands/review.md` builds the review in prose instructions: 7.5i formats comment bodies (prose rewrite through the humanizer when available), 7.5j aggregates positive observations, 7.5k assembles the payload with `jq` into a temp file, 7.5k2 truncates, 7.5l posts through `post_review` (`review/core/scripts/platform.sh`), 7.5m recovers. In bulk, Worker Mode (g) runs the same steps non-interactively and posts right away.
- **Decision**: Split 7.5 into a draft half (7.5a to 7.5k2 plus attribution, assembly, lint, preview) and a post half (checks, POST, thread actions, recovery). Both single-PR and bulk call the same halves.
- **Rationale**: One code path; the post half is a script, so "post exactly what was approved" is enforced by code.
- **Alternatives considered**: A draft-only flag on worker (g) with LLM posting (rejected in the brainstorm: posting stays an LLM promise, prompt-based lint misses small defects).

## R-002: Language for the new deterministic pieces

- **Finding**: Newer cc-review helpers that parse and validate structured data are Python 3 standard-library scripts (`review_continuity.py`, `pr_actions.py`, `review_scope.py`, `reviewer_activity.py`), invoked as `python3 -B` and tested through `tests/run.sh` wrappers plus `tests/test_*.py` unittest modules. Bash scripts (`bulk-apply.sh`, `bulk-state.sh`, `platform.sh`) own GitHub calls and run state.
- **Decision**: `review_draft.py` (Python, stdlib only) for assembly, attribution, preview, lint, fingerprint and conversation diff; `post-review.sh` (Bash) for the guarded POST, reusing `platform.sh`.
- **Rationale**: Text processing with code-span and fence exclusion, ordered label checks and canonical JSON hashing are error-prone in `jq`/`sed`; Python matches existing helpers. GitHub calls stay in Bash next to `platform.sh` and `rate-limit.sh`.
- **Alternatives considered**: All Bash plus `jq` (rejected: prose-only lint rules and Unicode dash detection outside code spans are fragile); one Python script that also calls `gh` (rejected: duplicates `platform.sh` and its rate-limit handling).

## R-003: Structure by construction

- **Finding**: The fallback template in `review/core/templates/reviewer-voice.md` defines `**{severity}**: {description}`, `**Why this matters**: {rationale}`, `**Suggested fix**: {fix}`, `_Source: ..._`. The examples in the same file use a title label instead of the severity. The previous run lost the labels because the humanizer rewrote whole bodies.
- **Decision**: The drafting step writes a slots file: per finding the three text slots, plus summary prose slots (What Went Well bullets, Follow-up progress prose). The prose rewrite edits only slot text. `review_draft.py assemble` renders labels, footers, table, counts, attribution, marker and completion lines. Examples in `reviewer-voice.md` are rewritten to start with the severity label.
- **Rationale**: The humanizer never sees a label, so it cannot remove one; the lint is a second line of defense.
- **Alternatives considered**: Instruction-only ("keep the labels") plus lint (rejected: this is what failed).

## R-004: Payload fingerprint

- **Decision**: SHA-256 over the canonical JSON of the payload (`sort_keys`, compact separators, UTF-8) plus the canonical JSON of the thread actions. `post-review.sh` recomputes it from the file it is about to send and compares it with the recorded approval (or, in unattended and non-interactive modes, the recorded checked fingerprint). It sends the file's bytes unchanged.
- **Rationale**: Matches the canonical hashing already used by `review_continuity.py` (`_json` + `sha256`). A canonical form makes the fingerprint independent of formatting while the file sent is exactly the file checked.

## R-005: Run facts

- **Finding**: Curation is only implied today (`accepted.json` exists in bulk; nothing in single-PR). Fix rounds run `TEST_CMD` and write only `round-<k>/regressions.json`, where `[]` also covers "no test command".
- **Decision**: A per-PR `facts.json` (bulk: `$PR_DIR/facts.json`; single-PR: `$REVIEW_RUN_DIR/facts.json`), written through `review_draft.py facts-set` at the moment a fact happens: the findings decision records `curated` (true only when every Critical and Important finding was answered individually), the fix worker records `{round, command, outcome}` with outcome `passed`, `failed` or `no-test-command`. Repro presence is derived at assembly from the findings (`failure_scenario` or `reproducer` fields, as gator emits).
- **Rationale**: Facts survive resume and are the single source for both the attribution statement and the unsupported-claim lint.

## R-006: Attribution wording

- **Decision**: Fixed sentences selected by facts, assembled in this order as the first line of `### Review Details`:
  - curated: "I went through these findings one by one and selected the ones posted here; cc-review's reviewer agents produced them."
  - not curated: "These findings were produced by cc-review's reviewer agents and posted without a per-finding review."
  - executed commands (one clause per recorded command, latest round): "The run executed `<command>` in fix round <k>: <passed|failed>." (omitted when none was recorded; `no-test-command` produces "No test command was detected, so no tests were run.")
  - repro present and not executed: "Failure scenarios were derived from reading the code and were not executed."
- **Rationale**: Every clause maps to one recorded fact; the lint knows which first-person verbs each fact allows ("I went through"/"selected" only when curated).

## R-007: Lint rules and prose extraction

- **Decision**: `review_draft.py lint` checks the assembled payload against facts and the expected head. Prose is the text left after removing fenced code blocks, inline code spans, URLs (`https?://\S+`), HTML comments (marker lines) and path-like tokens (containing `/` or a dot-extension without spaces). Rules (plus `result`: test-result phrases in generated text when `executed[]` is empty, per the plan review decision): marker present (exact `<!-- cc-review:run-id:<RUN_MARKER> -->`); `commit_id` present and equal to the expected head; per comment: labels in order and source footer last; summary sections in the FR-004 order; exactly one attribution statement, first line of Review Details; no U+2014 or U+2013 in prose; first-person verification patterns (`\bI (ran|run|tested|verified|executed|curated|checked|reproduced|confirmed)\b`, `\bI went through\b`, `\bI selected\b`) only where the facts allow; `[.!?][A-Z]` in prose. Output: JSON array of `{rule, location, message}`; exit 0 when empty, 1 otherwise. Claim rules apply to generated text only (summary prose, What Went Well, attribution), not to finding slots, per FR-011.
- **Rationale**: Deterministic, testable with fixture drafts (SC-005).

## R-008: Conversation check

- **Finding**: Analysis already writes `$SCOPE_DIR/threads.json`, `comments.json` and `reviews.json` in both modes (`review.md` Prior Review Context; `SCOPE_DIR` is `$PR_DIR/scope` in bulk). Author objects come from GraphQL/REST with `login`; bot accounts have `__typename: Bot` (GraphQL) or `type: Bot` / `[bot]` login suffix (REST).
- **Decision**: `review_draft.py conversation-diff --analysis <scope dir> --current <dir> --user <login>` returns new item identities authored by someone other than the user and not a bot (threads by root comment node ID, review comments by node ID, conversation comments by node ID, reviews by ID). `post-review.sh` fetches the current data with the existing `platform.sh` functions into a temp dir. Snapshot fetches keep the author type; where a fetch lacks it, the `[bot]` login suffix decides.
- **Rationale**: Reuses analysis data (FR-020a is mostly satisfied already; the plan adds author-type retention). Identity comparison ignores edits as clarified.
- **Follow-up Continuity**: the existing history recheck (`review_continuity.py` fingerprint of `history.json` against freshly fetched history) runs before the conversation diff; a mismatch maps to the same outcome (`CHANGED`).

## R-009: Thread actions (7.5f) move to the post phase

- **Decision**: The draft half writes proposed replies and resolutions to `thread-actions.json` (thread ID, reply body, resolve flag, activity fingerprint) and shows them in the preview. After approval and a successful review POST, the posting step performs them with the existing 7.5f guard, freshness recheck, activity marker and `reviewer_activity.py record`, using the approved bodies verbatim.
- **Rationale**: Nothing is written before approval (US1 scenario 1), while 7.5f's per-thread safety logic is reused unchanged.

## R-010: Persistence, resume and statuses

- **Decision**: Draft files live in `<draft dir>` = `$PR_DIR/post` (bulk) or `$REVIEW_RUN_DIR/post` (single-PR): `slots.json`, `payload.json` (the issue's `review-payload.json`), `thread-actions.json`, `preview.md`, `lint.json`, `draft.json` (inputs key + fingerprint + lint attempt count). Bulk state per PR gains `.draft` `{fingerprint, inputs_key}` and `.approval` `{answer, fingerprint, at}`; `bulk-state.sh` gains the status `withheld`. The inputs key is a hash of expected head, the set of finding IDs to post, and facts. On resume, a draft is reused when `draft.json` exists and its inputs key matches; an approval is reused when its fingerprint equals the draft's.
- **Rationale**: Drafting includes an LLM rewrite, so only reuse (not re-generation) can keep fingerprints stable across resume.

## R-011: Bulk worker changes

- **Decision**: Worker (g) becomes the **drafting worker** (no write API calls; returns `STATUS ok draft=<dir> fingerprint=<sha> lint=<n>`). Posting is done by the coordinator calling `post-review.sh` directly (a script, no subagent), then performing thread actions (subagent only if thread actions exist, reusing 7.5f). Unattended mode: draft, lint, record the checked fingerprint as the approval with answer `policy`, then post; a lint failure after the one redraft sets `withheld`.
- **Rationale**: The coordinator never reads PR content except previews in the approve pass, which is the user-facing step that the spec requires.

## R-012: Single-PR flow

- **Decision**: Step 7.5 in single-PR: 7.5g (findings decision, records `curated`), 7.5h, then **Draft** (7.5i to 7.5k2 + assemble + lint, redraft once), **Preview and approve** (interactive only: approve, edit, skip; edits change `slots.json` or the event and re-assemble), **Post** (`post-review.sh`, then thread actions). Non-interactive single-PR: no preview; a lint failure withholds and is reported in the Step 8 summary.
