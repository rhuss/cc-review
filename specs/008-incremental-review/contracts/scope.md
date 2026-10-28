# Scope Helper Contract

`python3 review_scope.py prepare --repo PATH --input SNAPSHOT.json --output DIRECTORY`

Snapshot contains identity, current head/base refs, complete review list, coverage key, full override and renewed-request boolean. Output `scope.json` and `review.diff`. Invalid inputs exit nonzero. Missing baseline/comparison selects explained full scope. No network, hosting writes or checkout/index/ref changes.

Other subcommands accept `--input FILE` and print JSON:

- `targets`: identity/head, complete thread collection, threads -> exact owned targets/completeness.
- `reconcile`: target batch and explicit outcomes -> verified outcomes/resolution candidates/completeness.
- `filter`: scope, findings, verified carried identities -> accepted findings/exclusions.
- `marker`: scope, run ID, required reviewer results, reconciled verification -> completion evidence and marker or incomplete reasons.
- `coverage`: effective reviewers, settings and context files -> stable coverage fingerprint, including parser contents rather than installation paths.
- `refresh`: completion candidate, fresh thread snapshot and prepared outcomes -> revalidated completion or incomplete reasons. Newly resolved owned targets no longer require unresolved-thread outcomes.
- `publication`: saved completion, expected identity/run/head -> validated marker or explicit incomplete label; inconsistent completed evidence is rejected.

Bulk candidates persist as `scope/completion-input.json` with `scope/outcomes.json`; the apply helper rechecks open head and conversations before publishing completion evidence. A standalone completion claim without its candidate inputs is insufficient to publish a new baseline.

Adapters accept `--full` for single/bulk review; it changes scope, never permissions. Existing activity guards authorize thread mutations separately from this helper's evidence.
