# Validation Quickstart

1. Run `python3 -B tests/test_ci.py` for offline router, state and publication-policy fixtures.
2. Run `make test` and `make validate`; validate workflow YAML with actionlint when available.
3. Invoke `cc-review:ci setup` in a disposable repository. Choose GITHUB_TOKEN and supply provider credentials through `gh secret set`, then commit/push the generated workflow/config.
4. Dispatch the test workflow, inspect its summary, open a PR and issue, and post `/cc-review help`. Observe one status comment, COMMENT reviews and configured issue labels.
5. Try an unauthorized command and automatic fork event; neither runs the model. Authorize fork review from a writer comment and confirm no fork checkout/execution.
6. Run doctor, disable all triggers, dispatch again and confirm no work. Cloud/App smoke tests require those identities and cannot be proven by offline tests.

Live provider/App acceptance is tracked in [issue #17](https://github.com/rhuss/cc-review/issues/17).
