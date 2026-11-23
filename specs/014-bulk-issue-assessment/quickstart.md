# Quickstart: Validating Bulk Issue Assessment

## Offline checks (no network, no model)

```bash
python3 -B tests/test_issue_bulk.py     # selection, skip rules, paging, state, measure, post idempotency
bash tests/run.sh issue                 # full runner, filtered
```

Expected: all tests pass. They cover each skip reason (SC-003), paging past skipped candidates (SC-005), `selected + skipped == scanned` (SC-004), argument validation (FR-002), resume without duplicate posts or PRs (SC-007), bound measurement (FR-023), and fix containment (no local execution, outside-worktree changes abandon the fix).

## Helper smoke test against a real repository (read-only)

```bash
python3 -B review/core/scripts/issue_bulk.py validate --bulk --search 'label:bug' --limit 5
python3 -B review/core/scripts/issue_bulk.py select --repo rhuss/cc-review --limit 5 --scan 30 --out /tmp/sel.json
jq '{scanned, ceiling_reached, selected: [.selected[].number], skipped: [.skipped[] | {number, reason}]}' /tmp/sel.json
```

Expected: maintainer-authored issues without replies appear in `selected`; issues with maintainer replies show `maintainer_replied`.

## End-to-end in a disposable test repository

1. Create a throwaway repository with three open issues: one untouched small bug (with a matching code location), one with a maintainer reply, one referenced by a non-maintainer draft PR.
2. Run `issue --bulk --limit 5` from a local clone.
3. Expect: two issues selected (the answered one skipped with reason), one approval prompt each, the PR-linked issue offering "review linked PRs", the small bug offering "fix it".
4. Approve posting for the bug and choose "fix it".
5. Expect: the comment with the assessment section and label on the issue; a draft PR from `cc-review/fix-issue-<n>` with "Fixes #<n>" and the note that tests run in the PR checks; no test or build command ran locally; `git status` and `git branch` in the clone unchanged; report listing every outcome.
6. Interrupt a second run after one post, run `issue --resume`, and confirm no duplicate comment.
