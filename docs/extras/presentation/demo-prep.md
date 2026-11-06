# Demo Preparation

Everything to set up before the session. The slides and presenter notes only cover what happens on stage.

## Session timeline

| Time | Block | Needs |
|------|-------|-------|
| 0-5 min | Kickoff | Demo PR checked out, permissions pre-approved, terminal ready |
| 5-35 min | Slides | Review runs in the background, must finish by minute 35 |
| 35-45 min | Results | Finished run, or the fallback report |
| 45-55 min | inbox, triage, issue | A repo with open work, a PR with review comments, a fresh issue |
| 55-60 min | Wrap-up | QR code slide |

## Demo targets (candidates, collected 2026-11-05)

### Review PR (kickoff, results)

The review should run in **author mode** on one of your own PRs, so the fix loop can push and the posting step goes to a repository you own.

| Candidate | Size | Why | Risk |
|---|---|---|---|
| **[ai-openshell/sdk-go#13](https://github.com/ai-openshell/sdk-go/pull/13)** (recommended) | +74/-22, 5 files | Closes [#12](https://github.com/ai-openshell/sdk-go/issues/12), so Goal Alignment has a real issue to check against; Go tests are fast for the fix loop; no reviews yet | Small diff may produce few findings |
| [ai-openshell/sdk-go#9](https://github.com/ai-openshell/sdk-go/pull/9) | +540/-7, 8 files | OIDC scope handling, gives the Security lane real material; more findings to show | Longer run; ported from [NVIDIA/OpenShell#3284](https://github.com/NVIDIA/OpenShell/pull/3284), which was reviewed before, so findings may overlap |
| [ai-openshell/sdk-go#11](https://github.com/ai-openshell/sdk-go/pull/11) | +56/-53, 5 files | Token refresh on every request, small and concurrency-relevant | Ported from [NVIDIA/OpenShell#4914](https://github.com/NVIDIA/OpenShell/pull/4914) by another author; author mode fixes would push to a ported branch |

NVIDIA/OpenShell PRs from other authors are not good review targets on stage: the run would be in reviewer mode (no fix loop), and anything posted lands on a colleague's PR in public.

### Issue (`/issue`)

| Candidate | Why |
|---|---|
| **[NVIDIA/OpenShell#5282](https://github.com/NVIDIA/OpenShell/issues/5282)** (recommended) | External contributor, `state:triage-needed`, a feature request (configurable MicroVM workspace root): good material for need, fit and value |
| [NVIDIA/OpenShell#5250](https://github.com/NVIDIA/OpenShell/issues/5250) | External contributor, small CLI bug (`status` exits 0 for an unregistered gateway), quick to assess |
| [ai-openshell/sdk-go#7](https://github.com/ai-openshell/sdk-go/issues/7) / [#8](https://github.com/ai-openshell/sdk-go/issues/8) | External contributor, docs issues on your own repo; the drafted reply could actually be posted |

Only draft the reply on stage. Do not post to NVIDIA/OpenShell issues live.

### Triage PR (`/triage`)

Neither repository has CodeRabbit, Copilot or Greptile reviews on open PRs right now.

- **[ai-openshell/sdk-go#5](https://github.com/ai-openshell/sdk-go/pull/5)**: 7 human review comments plus one `github-advanced-security[bot]` comment, own PR. Works for the human-comment path of triage.
- To show bot profiles, request a Copilot review on one sdk-go PR a day before, or keep a recorded triage run as backup.

### Inbox (`/inbox`)

- **ai-openshell/sdk-go**: 6 open PRs and 5 issues, small enough to run fast and show the grouping (needs your attention, waiting on others, no action).
- NVIDIA/OpenShell gives a more realistic picture but takes longer on a busy repository.

## Checklist

### One week before

- [ ] Pick the review PR; do a **timed dry run** with `--profile thorough` in the exact harness and permission mode used on stage. It must finish well under 30 minutes, including up to three fix rounds.
- [ ] Take the terminal screenshot for slide 2 (status table) during the dry run; save as `public/images/kickoff-status-table.png`.
- [ ] Decide on the triage PR; request a bot review if bot profiles should be shown.
- [x] Verify the "1-19%" figure (0.9-19.2%) on slide 3 in the full paper of arXiv 2508.18771. Verified 2026-11-05: 0.9% to 19.2% of valid AI comments led to changes, depending on the tool; human comments about 60%; 178 repositories.
- [ ] Generate the cover image (`ai-image-prompts.md`).

### One day before

- [ ] Refresh the data behind slides 11-14 (local report aggregation and OpenShell outcomes in `data/`), update numbers if they moved.
- [ ] Reset the demo PR branch to its pre-review state (the dry run may have pushed fixes), or prepare a fresh branch.
- [ ] Check that the chosen issue is still open and unanswered; have a second candidate ready.
- [ ] Record the dry run console as fallback.

### On stage, before starting

- [ ] Pre-approve edit and test permissions so the background review never stops on a prompt while slides are shown.
- [ ] `gh auth status` works; CodeRabbit and Codex CLIs are logged in.
- [ ] Demo repository checked out on the PR branch, clean working tree.
- [ ] Slidev running (`npx slidev slides.md` in `docs/extras/presentation`), presenter mode open on the second screen.
- [ ] Notifications off, terminal font size up.

## Run sheet

### Results (35-45 min), after the takeaways slide

- Switch to the terminal. Walk through the console summary, then `review-findings.md`.
- Reviewer status table: completed, skipped, failed, each with a reason.
- Meta-review lines: removed, calibrated, contradictions, and the agent quality scores.
- Fix rounds and test results.
- The posting step: approve before anything reaches GitHub.
- Invite questions while walking through the report.

### inbox, triage, issue (45-55 min)

- `/inbox` on the demo repository: needs your attention, waiting on others, no current action.
- `/triage --pr <n>` on a PR with review comments: classification, bot profiles, drafted replies.
- `/issue <n>` on a fresh issue: need, fit, value, reply draft.

Then switch back to the slides for "Try it this week".

## Fallbacks

- **Review not finished at minute 35**: show the dry run's `review-findings.md` and the console recording; let the live run finish during the inbox block and check back at the end.
- **External tool fails** (CodeRabbit, Codex): the status table shows it as failed with a reason. Mention it as a feature: the panel keeps going.
- **No network**: the recorded runs plus the PR #5 `review-findings.md` from the cc-review repository.
