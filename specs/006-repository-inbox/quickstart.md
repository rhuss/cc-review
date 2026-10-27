# Quickstart: Repository Inbox

Prerequisites: Python 3.9+, authenticated gh, supported cc-review installation.

## Offline Checks

Run `python3 -B -m unittest discover -s tests -p 'test_inbox.py' -v`, `make test`, and `make validate`. Offline tests need no token and must preserve the checkout.

## Live Collector

Run `python3 review/core/scripts/inbox.py --repo rhuss/cc-review --type issue --limit 2`. Expect issue-only snapshot entries and coverage; no remote writes.

## Harness

Invoke `inbox --repo rhuss/cc-review` through the installed harness. Expect all three groups, with a coverage warning if Discussions are disabled.

Invoke `inbox --repo rhuss/cc-review --type issue,discussion --since 2026-10-01 --limit 5`. Expect the selected types and an explicit scope/limit explanation.

Check own PR feedback, a requested review, and a human conversation. Every action must have evidence; ambiguous responsibility must be marked. Suggested commands must remain suggestions.

## Negative Cases

Try unknown/empty types, --limit 0, and an impossible calendar date. Fail before service calls. Offline failures prove missing sources/details are distinct from an empty inbox.

## Validation Record (2026-10-26)

- Inbox unittest suite: 31 tests passed.
- Full project suite: 1,164 assertions passed, zero failed, across 141 runner tests.
- make validate: marketplace and plugin manifests passed; the validator also reports the existing optional missing-icon warning.
- Python 3.9 syntax parsing passed for collector and tests.
- Live GraphQL validation passed for all three search queries and all three typed detail queries.
- Live issue-only and all-type snapshots of rhuss/cc-review succeeded. Observed one authored issue, no relevant PRs, disabled Discussions, and a visible long-body truncation warning.
- Real CLI integration preserves staged, unstaged and untracked content and permits only query operations.
- OpenCode installation test resolves the new command and core collector.
- Native contextual presentation can be tried through the drafted post-pipeline runbook; automated tests verify collection and packaging, not model-language judgments.
