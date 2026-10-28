# Research: Review Convergence

## R1: Separate history from coverage

Decision: retain `review_scope.py` unchanged and add `review_continuity.py`.
Rationale: manual history and resolved discussion are relevant even when no completion marker exists. Altering baseline selection would conflate conversation with code coverage.
Alternative: extend scope markers with manual history; rejected because it changes their trust meaning.

## R2: Preserve prose, validate decisions

Decision: collect raw source conversations and surrounding issue comments, then require semantic assessments with exact source references and code evidence. Summaries are assessed as whole sources, with all constituent concerns evaluated.
Rationale: no deterministic text rule can safely infer whether an explanation is accepted or a summary contains one or several findings.
Alternative: proximity/keyword matching; rejected because it can erase unanswered questions or material concerns.

## R3: Conservative completeness

Decision: use an exact fingerprint of identity, head and collected history. Missing pages, duplicate sources, stale or missing assessments and unresolved questions prevent a clean conclusion. An accepted explanation requires existing explicit approval.
Rationale: a clean result must not arise from incomplete context. Source collections have existing bounded pagination; limits remain visible.

## R4: One policy across tools and modes

Decision: supply prior history to prompt workers and critics, and apply the common semantic/deterministic assessment to all merged candidates including command outputs. Full scope and follow-up history are independent.
Rationale: external tools cannot be assumed to honor delta or conversation prompts. The final policy is mandatory even when meta-review is skipped.

## R5: Existing thread authority

Decision: preserve `verification.json` and its exact activity/approval rules for resolutions. Manual/summary continuations affect reports and gate counts but cannot manufacture thread-resolution authority.
Rationale: avoids expanding triage ownership or introducing writes from new prose classifications.
