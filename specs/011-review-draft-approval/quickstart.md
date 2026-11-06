# Quickstart: Review Draft Approval

## Prerequisites

- `bash`, `jq`, `python3`, `gh` (authenticated) as for cc-review today.
- Worktree `011-review-draft-approval` with the feature implemented.

## 1. Automated tests

```bash
make test                       # whole suite (tests/run.sh)
bash tests/run.sh review_draft  # draft assembly, attribution, preview, lint, fingerprint, conversation diff
bash tests/run.sh post_review   # guarded posting with a stubbed gh
```

Expected: all pass. The `review_draft` tests cover each lint rule with a fixture draft that contains exactly that defect (SC-005) and a clean draft that passes; assembly tests confirm every inline comment has the three labels and the source footer in order, also after a simulated rewrite of slot text (SC-004); attribution tests confirm curation wording only with `curated: true` and command results only from `executed[]` (SC-003).

The `post_review` tests stub `gh` and confirm: no POST on fingerprint mismatch, missing commit, moved head, existing marker, or new non-bot comments; the POST body equals the draft file byte for byte (SC-002); a timeout followed by a marker hit reports `FOUND` and posts nothing more.

## 2. Single-PR walkthrough (manual, against a test PR)

1. Run `/cc-review:review --pr <n>` on a PR with a few findings; choose "post all".
2. Confirm the preview appears and that `gh api repos/<o>/<r>/pulls/<n>/reviews` shows no new review yet.
3. Ask for an edit ("drop the second inline comment"); confirm a new preview with the comment, its table row and the counts gone.
4. Approve; confirm the posted review equals the approved preview and that Review Details starts with "These findings were produced by cc-review's reviewer agents and posted without a per-finding review."

## 3. Bulk walkthrough (manual)

1. `/cc-review:review --bulk --search '<query matching 2 test PRs>'`, choose "Apply proposed actions".
2. Confirm both drafts are prepared before the first preview, then both previews are shown one after another before any review appears on GitHub.
3. Approve one, skip the other; confirm one review posted, the other PR `skipped`.
4. Interrupt during the approval pass and run `--bulk --resume`; confirm the answered PR is not asked again.

## 4. Unattended check

`/cc-review:review --bulk --unattended ...`: no prompt; reviews posted as comments; a PR whose draft fails lint twice shows as `withheld` under "Needs attention".
