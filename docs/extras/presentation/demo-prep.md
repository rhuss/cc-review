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

## Demo targets (updated 2026-11-06)

| Block | Harness | Target | Mode | Posts? |
|---|---|---|---|---|
| Live kickoff (0-5, results at 35) | Claude Code | new sdk-go draft PR "honor Config.Timeout, RetryPolicy and Logger" | author, `--pr <n> --profile thorough` | approve on stage, own repo |
| Fallback for the live run | Codex | same branch, local, no `--pr`, `--output` outside the repo | author, local | no |
| Observability example | OpenCode | [NVIDIA/OpenShell#5243](https://github.com/NVIDIA/OpenShell/pull/5243) | reviewer | no (choose "post nothing") |
| inbox | Claude Code | NVIDIA/OpenShell, from a local checkout | read-only, guided tour | no |
| triage (from the inbox tour) | Claude Code | [NVIDIA/OpenShell#4697](https://github.com/NVIDIA/OpenShell/pull/4697) | reviewer role | drafts only |
| issue | Claude Code | [NVIDIA/OpenShell#5282](https://github.com/NVIDIA/OpenShell/issues/5282) | assessment | drafts only |

Every pre-run happens in a different harness, so the terminal has a finished Claude Code, Codex and OpenCode run to fall back on, and the "three agents" claim is shown, not told.

### Live review: new sdk-go PR (author mode)

All existing sdk-go PRs of yours ([#9](https://github.com/ai-openshell/sdk-go/pull/9), [#10](https://github.com/ai-openshell/sdk-go/pull/10), [#11](https://github.com/ai-openshell/sdk-go/pull/11), [#13](https://github.com/ai-openshell/sdk-go/pull/13)) already carry your reviews, so the live run uses a fresh one.

- **Change:** port of [NVIDIA/OpenShell#4510](https://github.com/NVIDIA/OpenShell/issues/4510). `v1.NewClient` reads only `Address`, `Auth` and `TLS`; `Timeout`, `RetryPolicy` and `Logger` are set by `gateway.NewClient` options (`WithTimeout`, `WithRetryPolicy`, `WithLogger`) and then ignored. Checked against sdk-go `73ef0c2`.
- **Why:** retries invite real findings (non-idempotent RPCs, backoff, context deadline versus `Timeout`) for correctness and production readiness; Goal Alignment has an issue to check against; Go tests keep fix rounds short; author mode lets the fix loop push.
- **Prepare:** sdk-go issue for the port; branch with the fix, about 100 to 300 lines; draft PR that closes the issue, opened the day before and not reviewed by anyone.
- **Fallback:** run the same branch in Codex the day before, locally (no `--pr`) and with `--output` outside the repository, so nothing reaches GitHub and the PR stays untouched for the live run.

### Observability example: NVIDIA/OpenShell#5243 (reviewer mode, pre-run)

- [#5243](https://github.com/NVIDIA/OpenShell/pull/5243) "feat(tracing): show boundary connection time during sandbox startup": +266/-0, 4 files, no reviews yet, closes your issue [#5160](https://github.com/NVIDIA/OpenShell/issues/5160), so Goal Alignment checks it against your own request. Run in OpenCode; at the end choose to post nothing.
- Bigger alternative with more findings: [#4590](https://github.com/NVIDIA/OpenShell/pull/4590) "push gateway metrics over OTLP" (+852/-63, 17 files, closes your issue [#4489](https://github.com/NVIDIA/OpenShell/issues/4489)); already 1 review and 11 comments.

### inbox and triage: NVIDIA/OpenShell

- No review requests to you on OpenShell right now, but enough material: [#4697](https://github.com/NVIDIA/OpenShell/pull/4697) (8 cc-review threads from you, 10 replies by others, latest 2026-11-06), [#4789](https://github.com/NVIDIA/OpenShell/pull/4789) and [#5079](https://github.com/NVIDIA/OpenShell/pull/5079) with new activity, and open issues you filed (for example [#5319](https://github.com/NVIDIA/OpenShell/issues/5319)).
- Run `inbox` from a local checkout of NVIDIA/OpenShell so the tour can hand off.
- From the tour, hand [#4697](https://github.com/NVIDIA/OpenShell/pull/4697) ("fix(python): add opt-in sandbox delete timeout", +105/-6) to `triage`: reviewer role, checks the author's replies and fixes against your threads, drafts responses. Fallback: [#5079](https://github.com/NVIDIA/OpenShell/pull/5079) (2 threads, 2 replies).
- Bot profiles: still no CodeRabbit or Copilot reviews on these repositories, so that path stays unshown unless a bot review is requested a day before.

### Issue (`/issue`)

| Candidate | Why |
|---|---|
| **[NVIDIA/OpenShell#5282](https://github.com/NVIDIA/OpenShell/issues/5282)** (recommended) | External contributor, `state:triage-needed`, a feature request (configurable MicroVM workspace root): good material for need, fit and value |
| [NVIDIA/OpenShell#5250](https://github.com/NVIDIA/OpenShell/issues/5250) | External contributor, small CLI bug (`status` exits 0 for an unregistered gateway), quick to assess |
| [ai-openshell/sdk-go#7](https://github.com/ai-openshell/sdk-go/issues/7) / [#8](https://github.com/ai-openshell/sdk-go/issues/8) | External contributor, docs issues on your own repo; the drafted reply could actually be posted |

Only draft replies on stage. Do not post to NVIDIA/OpenShell issues or PRs live.

## Checklist

### One week before

- [ ] Open the sdk-go issue (port of OpenShell #4510) and implement the fix on a branch (about 100 to 300 lines).
- [ ] Do a **timed dry run** of that branch with `--profile thorough` in the exact harness and permission mode used on stage, locally without `--pr`. It must finish well under 30 minutes, including up to three fix rounds.
- [ ] Check that cc-review is installed and logged in for Codex and OpenCode.
- [ ] Take the terminal screenshot for slide 2 (status table) during the dry run; save as `public/images/kickoff-status-table.png`.
- [ ] Triage PR: [NVIDIA/OpenShell#4697](https://github.com/NVIDIA/OpenShell/pull/4697); request a bot review somewhere only if bot profiles should be shown.
- [x] Verify the "1-19%" figure (0.9-19.2%) on slide 3 in the full paper of arXiv 2508.18771. Verified 2026-11-05: 0.9% to 19.2% of valid AI comments led to changes, depending on the tool; human comments about 60%; 178 repositories.
- [ ] Generate the cover image (`ai-image-prompts.md`).

### One day before

- [ ] Refresh the data behind slides 11-14 (local report aggregation and OpenShell outcomes in `data/`), update numbers if they moved.
- [ ] Reset the sdk-go branch to its pre-review state (the dry run may have changed it), push it and open the **draft PR**; nobody reviews it before the talk.
- [ ] Pre-runs: Codex on the sdk-go branch (local, `--output` outside the repo), OpenCode on [NVIDIA/OpenShell#5243](https://github.com/NVIDIA/OpenShell/pull/5243) (post nothing). Keep both terminals open.
- [ ] Check that #5243 and #4697 are still open and #4697 still has unanswered replies.
- [ ] Check that the chosen issue is still open and unanswered; have a second candidate ready.
- [ ] Record the dry run console as fallback.

### On stage, before starting

- [ ] Pre-approve edit and test permissions so the background review never stops on a prompt while slides are shown.
- [ ] `gh auth status` works; CodeRabbit and Codex CLIs are logged in.
- [ ] sdk-go checked out on the PR branch, clean working tree; a NVIDIA/OpenShell checkout for `inbox` in a second tab.
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

- `/inbox` in the NVIDIA/OpenShell checkout: the attention table and "My take", waiting on others, no current action. Accept the guided tour, look at one or two items, and hand the PR with review comments to `triage` from the tour, which leads straight into the next step.
- `/triage --pr 4697` (or via the tour): verification of the author's replies against your threads, drafted responses. Draft only.
- `/issue 5282` on a fresh issue: need, fit, value, reply draft.

Then switch back to the slides for "Try it!".

## Fallbacks

- **Review not finished at minute 35**: switch to the Codex pre-run of the same branch and walk through its report; let the live run finish during the inbox block and check back at the end.
- **Want an observability example or a third harness**: the OpenCode pre-run on NVIDIA/OpenShell#5243.
- **External tool fails** (CodeRabbit, Codex): the status table shows it as failed with a reason. Mention it as a feature: the panel keeps going.
- **No network**: the recorded runs plus the PR #5 `review-findings.md` from the cc-review repository.
