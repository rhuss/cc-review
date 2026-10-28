# Quickstart Validation

1. Run `python3 -m unittest discover -s tests -p 'test_review_scope.py'`: semantic Git/baseline/rebase/verification cases pass without network.
2. Run `make test` and `make validate`: existing selectors, activity, adapters and plugin manifests pass.
3. Run `review --pr <number>` in a supported agent: absent v1 personal completion evidence selects explained full review; existing approval rules apply.
4. After a complete approved posted review and an author update, repeat: automatic whole-delta review including fixes and explicit earlier-finding verification.
5. Run `review --pr <number> --full` or `review --bulk --full`: explicit full scope, unchanged approval policy.
6. A proven pure rebase avoids a code-review post while retaining thread work. A renewed request requires verification and acknowledgment.

Live commands are optional user actions, not automatic test fixtures. Do not post to production PRs merely to validate this guide.
