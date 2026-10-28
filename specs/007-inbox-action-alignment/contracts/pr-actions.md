# PR Action and Reviewer Activity Contract

## Shared assessment

`review/core/scripts/pr_actions.py` exposes importable normalization/assessment functions and a JSON CLI usable by `bulk-select.sh`. Both call the same decision functions. CLI arguments and JSON structure are validated before service access; untrusted PR text is data, never code.

Input specifies repository/user/scope and canonical PR evidence from [data-model.md](../data-model.md). Output retains both action assessments, coverage warnings and exclusions. Shared selection preserves existing `{selected: [...], excluded: [...]}` output and seed fields, adding role/evidence. No required change to existing user flags.

Default review candidate rules and reviewed-at-head semantics stay compatible with current `bulk-select.sh`. Triage includes own-PR unresolved feedback and qualifying owned reviewer follow-ups, including drafts. Explicit search filters narrow candidates; limits and exclusions remain visible. Incomplete evidence cannot become a confident ineligible assessment. Independent established actions survive unrelated missing context.

## Read-only inbox

`inbox.py` attaches the shared assessment to each PR item using raw bounded detail before display normalization. Items of other types retain their existing schema/behavior. The snapshot scope records action selection semantics so the report can distinguish eligibility from actual processing under different discovery/limit scopes. The report may explain actions but must not invent a contradictory action category.

No state helper called by inbox creates directories, writes files or initializes legacy triage state. Explicit `--repo` identity controls which existing reviewer cache is read.

## Reviewer activity helper

`reviewer_activity.py` provides fingerprint, load, record and marker operations. Missing cache returns empty state; invalid identity/content is incomplete evidence with an actionable warning. Writes are atomic, preserve unrelated thread records and use the identity-scoped path defined in research R4. Tests set `CC_REVIEW_REVIEWER_STATE_FILE` and never write real user state.

Real replies retain `<!-- cc-review-triage -->` and may append a bounded, narrowly parsed `cc-review-activity:v1` marker containing exact thread/root/head/digest and deterministic activity key. Accept recovery markers only from the authenticated author on the actual matching thread. Cache/no-post outcomes cannot advance a review baseline.

## Reviewer plan/apply

Reviewer role is carried by trusted bulk selection/state and checked against plan role and PR ownership. Reject a reviewer plan with a prepared commit or author-only mutation before any push or thread write. Reviewer plans never use path/line/author fallback to find a target.

Each reviewer action includes exact thread/root ID, expected head and activity fingerprint. Recheck open PR, head, ownership, unresolved state and conversation before its write; recheck before resolving after a post. Missing/truncated/mismatched decisive evidence yields a stale/incomplete reason and no affected write. On retry, recognize only the exact activity marker, record post and resolution independently, and preserve outcomes requiring no post.

`commands/triage.md` uses these same ownership/fingerprint rules in single-PR and prepare modes. Reviewer mode skips author bot fixes/CI repair. `commands/review.md` checks handled activity before overlapping replies/resolutions and records only thread work actually completed. Existing author plans and state remain compatible.


## Internal CLI interfaces

These are helper interfaces for existing commands, not new user-facing flags. Use Python 3.9-compatible type annotations. Each CLI invocation reads exactly one JSON value from stdin, emits exactly one JSON object to stdout, and sends diagnostics to stderr. Unknown operations, invalid JSON/types, invalid identities and nonpositive limits fail with exit 2; missing required dependencies or unusable service/state access fail with exit 1. A usable partial assessment exits 0 and includes warnings; it cannot claim complete empty results. Existing bulk service rate-limit exit 75 remains unchanged.

`pr_actions.py assess|select --source inbox|bulk|canonical --repo owner/name --user login --host host --review-mode default|all-open|search [--include-review-drafts]` reads an array of PR records. `select` also requires `--action review|triage --limit N`. The caller supplies records from the requested discovery/query scope; this helper does not execute or reinterpret GitHub search syntax. Source adapters preserve discovery reasons and scope/coverage metadata so an excluded or unobserved candidate is distinguishable from a verified ineligible PR. Both operations load existing handled state for the explicit identity through `load_activity`; no read creates a path. Importable `normalize_pr`, `assess_pr` and `select_prs` remain pure and use caller-supplied state.

- `assess` returns `{"assessments": [Assessment], "warnings": [str]}`.
- `select` returns `{"selected": [Seed], "excluded": [Exclusion], "warnings": [str]}`. Seeds retain all existing keys and add `triage_role` (`"author"` or `"reviewer"` for triage; null for review) and `assessment`. Exclusions retain `number`, `title`, `reason` and add the relevant `assessment` when known.
- `Assessment` contains PR `host`, `repository`, `number`, `user` plus `review` and `triage`. Each action has `eligible: bool`, `role: str|null`, `reason: str`, `evidence: list[dict]`, `uncertain: bool`, `complete: bool`, `exclusion: str|null`. Unsupported executable eligibility is false with `complete=false`; independently established actions survive missing evidence for the other action.

`reviewer_activity.py load|fingerprint|check|record` reads one object. All envelopes carry `identity: {host: str, repository: str, user: str, pr: int}`. Repository is `owner/name`; PR is a positive integer. Host/repository/user are validated path components, never interpreted as a filesystem path supplied by hosting content. The state-file override remains the explicitly configured trusted test seam.

- `load`: input `{"identity": Identity}`; output `{"records": dict, "complete": bool, "warnings": [str]}`. Missing state is complete empty state. Malformed or wrong-identity content returns incomplete state with an actionable warning, never a verified empty queue.
- `fingerprint`: input `{"identity": Identity, "head_oid": str, "thread": ThreadEvidence}`; output `{"activity": Activity|null, "complete": bool, "reason": str|null, "warnings": [str]}`. Missing decisive evidence yields null activity and `complete=false`.
- `check`: input `{"identity": Identity, "expected": Activity, "current_pr": {"state": str, "head_oid": str, "author": str}, "thread": ThreadEvidence}`; output `{"allowed": bool, "complete": bool, "reason": str|null, "activity": Activity|null, "warnings": [str]}`. It verifies open PR, other-author ownership, unresolved thread, exact root ownership/provenance, and matching head/conversation. No service access or writes occur in this helper; the caller fetches current evidence before every affected write.
- `record`: input `{"identity": Identity, "activity": Activity, "outcome": Outcome, "reply_id": int|null, "resolved": bool}`; output `{"recorded": bool, "complete": bool, "reason": str|null, "warnings": [str]}`. Only completed approved outcomes may be recorded. The CLI maps `activity` to the internal `thread` record argument and carries `reply_id`/`resolved` with the completed outcome; all callers use that same mapping. A failed state write is an error and leaves the earlier cache readable. Serialize read/merge/replace with a per-identity interprocess `fcntl` lock on the supported macOS/Linux targets so concurrent writes preserve unrelated thread records. `record_activity` implements this operation; reads need no directory creation.

`Activity` is `{thread_id: str, root_comment_id: str, head_oid: str, conversation_digest: str, activity_key: str}`. `thread_id` and `root_comment_id` are exact GraphQL node IDs; existing `comment_id: int` is the exact root database ID used by the reply API. `conversation_digest` and `activity_key` are deterministic SHA-256 hex strings. A `ThreadEvidence` retains these thread/root identities, root author/body/containing review provenance/original commit, unresolved status, bounded comments with exact identities, full body and edit timestamps, and explicit coverage. Fingerprints use original bodies before display sanitization/truncation. A missing root or truncated decisive conversation cannot match a handled activity. `Outcome` is `{status: "confirmed-fixed"|"still-present"|"accepted-explanation"|"deferred"|"unclear", completed: bool}`; pending questions/disagreements are incomplete outcomes. Identity and record operations never advance review baselines.

Importable interfaces supplement plan.md: `parse_activity_marker(body: str) -> Optional[dict]`, `check_activity(identity: dict, expected: dict, current_pr: dict, thread: dict) -> dict`, and `load_activity(host: str, repository: str, user: str) -> tuple[dict, list[str]]`. The load wrapper treats validation warnings as incomplete state; incomplete state cannot support a negative eligibility conclusion. `activity_marker(identity, activity, reply_body)` returns a bounded marker bound to the exact reply text; the caller appends it to an actual signed reply. Editing the reply body invalidates marker recovery and the prior fingerprint. Recognize exactly one well-formed marker in its own HTML-comment position, not a quoted marker or a different author's reply.

## Reviewer plan fields

The reviewer extension retains the author plan shape and the existing `.cc_review_threads[]`/`.human[]` approval flow. Top-level reviewer fields are:

```json
{
  "pr": 42,
  "triage_role": "reviewer",
  "expected_head": "head-oid",
  "activity_identity": {"host": "github.com", "repository": "acme/widget", "user": "me", "pr": 42},
  "prepared_commit": null,
  "cc_review_threads": [],
  "human": []
}
```

Each reviewer `.cc_review_threads[]` entry retains `comment_id`, `thread_id`, `author`, `path`, `line`, `body`, `action`, `resolve` and adds `activity: Activity` and `outcome: Outcome`. The exact root database ID is `comment_id`; `thread_id` must equal `activity.thread_id`. A finalized no-post verification uses `body=""`, `resolve=false`, `outcome.completed=true`; retain that entry for approval and handled recording instead of filtering it out. `.human[]` retains `text`, `assessment`, `draft`, `decision` and adds the same activity/outcome fields. Only `decision="approve"|"edit"` can apply the corresponding user-approved response. Null/skipped decisions remain pending and cannot become completed handling. Resolve only confirmed verified fixes or explanations explicitly accepted under the applicable approval/unattended policy.

Trust reviewer authority from selection/state plus a fresh PR author/owned-root check; plan role/identity must agree with state. Reviewer plans reject non-null prepared commits, author mutation requests and author-only reply/resolution arrays before any write. Pending questions cannot be converted into automatic acceptance by renaming an outcome. The same fields are consumed in T007 preparation, T008–T010 bulk apply and T012 single-PR helper calls.
