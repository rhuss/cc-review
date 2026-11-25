# Brainstorm: Verify External Reviewer Findings

**Date:** 2026-11-24
**Status:** idea
**Related:** #13 (skeptic-false-positives), #04 (meta-reviewer), #05 (reviewer-plugins)

## Problem Framing

A review of [ai-openshell/sdk-go#70](https://github.com/ai-openshell/sdk-go/pull/70) reached the user with one Important finding that was plainly false, and it made the gate fail.

The finding came from Codex (`codex review`, CLI v0.167.0, P1 mapped to Important) and pointed at `hack/automation/core-registry.sh:13`. Its claim was that an anonymous Quay manifest request receives a bearer-token challenge, so Quay-only releases are never found. The claim is wrong. An anonymous request with the same Accept header returns 200 for published tags and 404 for unpublished ones. The correctness and gator reviewers ran the helper against the live registries and confirmed this, the Skeptic reproduced the 200, and the orchestrator checked it a third time.

The false positive still passed every stage, because of three independent gaps:

1. **The external tool could not verify and guessed.** The Codex run log (`commands/codex.err`) shows that Codex tried the same probe and got `curl: (6) Could not resolve host: quay.io`. `codex review` runs in a `workspace-write` sandbox without network access. Codex then filled the gap with GHCR-style token behavior and reported P1 instead of marking the claim as unverified. Nothing in cc-review reads `.err` files for that kind of signal.
2. **The meta-review is told not to look.** `core/agents/meta-skeptic.md:63-64` says: "External tool findings (source_agent = "coderabbit", "copilot", "codex") pass through unchanged. Set their verdict to `confirmed` without evaluation." `core/agents/meta-calibrator.md:87-88` exempts them from calibration in the same way. In this run the Skeptic reproduced the refuting evidence, wrote "on the merits this is a false positive", and still returned `confirmed` as the rule requires.
3. **The orchestrator cannot overrule.** In `core/commands/review.md` Step 4b, only a Skeptic `false-positive` verdict removes a finding. The orchestrator held refuting evidence, but the rules still made it report the gate as FAIL and show the finding as Important.

Further observations from the same run:

- The exemption list is hardcoded by tool name. It does not cover `greptile`, any user or project command reviewer, or a future tool, which contradicts the plugin model of #05 (no reviewer names in core).
- Codex's output ignored the declared `delimited` format (a "Review comment" bullet with `[P1]` and a `path:start-end` reference), so the orchestrator parsed it from the body notes. Parsing worked, but there is no deterministic converter (see the idea inbox entry on `json`/`delimited` converters).
- Codex loaded its own copy of the cc-review plugin and the superpowers skill and read `commands/review.md` before reviewing. That costs context, and an "independent" reviewer reads our orchestration rules.
- The Calibrator scored Codex at precision 0.0 for this run, so the signal existed but had no effect on the finding.

**Why the exemption exists (assumed):** external tools are a second opinion from a different vendor, and letting our own model veto them would defeat the cross-vendor value (#13 idea 5). That rationale holds against *opinion*, but not against a factual claim that a reproducible check refutes.

**Success:** an external finding refuted by reproducible evidence (a command and its output, or code that contradicts it) is marked false-positive and stays visible in the report's removed section. External findings that hold up keep their weight, and the cross-vendor second opinion survives.

**Anti-goals:** our own model silently vetoing every external finding it dislikes; removed findings disappearing from the report; giving external tools network access in untrusted (fork) checkouts.

## Ideas

1. **Evaluate external findings like any other, with a higher bar for removal.**
   - Drop the "confirmed without evaluation" rule in the Skeptic.
   - Removing a finding from a `kind: command` reviewer requires reproducible counter-evidence: the exact command and its output, or a file and line that contradicts the claim. Plausibility arguments only allow `weak`.
   - Key the rule on `kind: command` (or `category: external`) from discovery, never on a list of tool names.
2. **Let the Calibrator calibrate external severities.** Same evidence bar for a downgrade. Today the Calibrator scores the tool (precision 0.0) but cannot touch the finding.
3. **An orchestrator evidence channel.** When the orchestrator or a prompt reviewer holds refuting evidence (here, two reviewers ran the helper live), pass it to the Skeptic as input. Never let the orchestrator remove findings on its own outside the meta-review.
4. **Surface failed verification attempts from the tool's log.** A post-parse step scans the command reviewer's stderr for failed checks (`Could not resolve host`, `Operation not permitted`, sandbox denials) near the cited file and tags the finding `unverified: no network`. The Skeptic then treats it as an unverified claim.
5. **Give Codex the means to verify, where safe.** For trusted checkouts (not fork PRs, see the Untrusted Checkout section of `review.md`), enable network in the sandbox (Codex has a `sandbox_workspace_write.network_access` setting; the flag for `codex review` is still to be confirmed). Alternatively, instruct the tool to label unverifiable runtime claims, if `codex review` accepts a prompt.
6. **Isolate the external tool from cc-review itself.** Run Codex with plugins/skills disabled (or a clean `CODEX_HOME`), so it reviews the change and not our orchestration prompts.
7. **Regression fixture.** Add a meta-review test case: an external finding with refuting evidence (this Quay case) must end up `false-positive`, and an external finding with no counter-evidence must stay `confirmed`. This fits #13 idea 1 (a labeled eval set).

## Open Questions

- Should a refuted external finding be removed, or demoted to Notable with the refutation attached? #13 asks the same for internal findings.
- Is a command plus its output enough evidence, or does a removal also need agreement from a second source (another reviewer, or the orchestrator's check)?
- Does a network-enabled Codex in trusted checkouts widen the attack surface in ways the trust model of #05 does not cover (for example, a PR that adds a URL the tool then fetches)?
- How do we detect "the tool tried and failed to verify" across tools whose logs differ (Codex, CodeRabbit, Copilot)? Per-reviewer parsing notes, or a shared pattern list?
- Does the cross-vendor value of external tools (#13 idea 5) need its own protection, for example the Skeptic may not mark an external finding weak on judgment alone?
