# Measured results

<!-- Sources:
cc-review:review/core/agents/meta-skeptic.md:17-26
url:https://github.com/NVIDIA/OpenShell/pull/5082
url:https://github.com/NVIDIA/OpenShell/pull/5083
url:https://github.com/NVIDIA/OpenShell/pull/4789
-->

The pages before this one describe how cc-review is built and what each stage is meant to do. This one reports how well it has done it in practice. Everything below is a measurement taken at a point in time, not a guarantee of future behavior, and every figure carries the date it was measured. The numbers come from two recorded data sets: the labeled findings from cc-review runs on the public NVIDIA/OpenShell pull requests (`openshell-findings-labeled.jsonl`), and an aggregate of the maintainer's own local review reports (`local-reports-aggregate.json`). Read them as evidence from those runs, not as a specification of what cc-review will do on your change.

## Findings on the public OpenShell pull requests

The clearest public evidence is a set of cc-review runs on the NVIDIA/OpenShell repository, recorded in the labeled OpenShell findings data set. As measured in early November 2026, those runs produced 208 inline findings across 20 public pull requests, and the data set labels each finding with what became of it.

The two fix outcomes dominate. 77 findings were fixed with the fix verified in the code, and another 40 were fixed as reported by the author, so 117 of the 208 findings, about 56 percent, were addressed by a fix. The rest break down as 28 resolved without an explicit reply, 27 still open, 16 deferred, 16 that went stale with no reply, 3 withdrawn, and 1 rejected. These counts are the state of those threads as measured in early November 2026, attributed to the same OpenShell findings data set; the open and deferred ones in particular can still change as the pull requests move.

Because the OpenShell repository is public, you can read the threads yourself. cc-review's findings appear on [pull request #5082](https://github.com/NVIDIA/OpenShell/pull/5082), [pull request #5083](https://github.com/NVIDIA/OpenShell/pull/5083), and [pull request #4789](https://github.com/NVIDIA/OpenShell/pull/4789), among the 20 covered by the measurement.

## Fix rate across the maintainer's local runs

The second data set is an aggregate of local cc-review reports kept by the maintainer. As measured in early November 2026 it covers 147 recorded reports, the dated ones running from late March to early November 2026. For each report and severity it records how many findings were found and how many were fixed.

The headline measurement is the blocking severities. Across those 147 reports, and attributed to the local reports aggregate, cc-review found 632 Critical and Important findings and fixed 585 of them, about 93 percent, as measured in early November 2026. These are the severities the gate blocks on (see [Gate and fix](gate-and-fix.md)), so this is the rate at which the fix loop cleared the issues that would otherwise hold a change back. Counting every severity together, the same reports found 1901 findings and fixed 979, about 51 percent. The gap between the two rates is expected: Minor and Notable findings fall outside the gate, so many are reported for the record and left for you to judge rather than fixed automatically.

## What meta-review did in the measured reports

A smaller subset of the local reports ran with meta-review recorded in full. As measured in early November 2026 that subset is 7 reports covering 132 findings, again drawn from the local reports aggregate. In those reports the Calibrator recorded 16 severity adjustments, for example downgrading an Important finding to Minor, while the Skeptic removed none of the 132 findings outright as false positives.

That last number is the honest limit of the current meta-review, not a selling point. The Skeptic's role, by its own instructions, is to read the code behind each finding and judge it confirmed, weakly supported, or a false positive. In the measured subset it confirmed or weakened findings but struck none of them, so the only severity changes meta-review made in those reports came from the Calibrator's 16 downgrades (see [Meta-review](meta-review.md)). Read the measured removal count of zero as a reminder that the Skeptic is cautious by design: in these runs no finding was a clear enough false positive for it to drop.

## How to read these numbers

Every figure on this page is a dated measurement from the two recorded data sets, taken in early November 2026. They describe cc-review's behavior on the OpenShell pull requests and on the maintainer's own changes up to that date, and they will drift as the tool, the reviewers, and the code under review change. Treat them as evidence that cc-review clears most of the blocking issues it raises and that its reviews have led to real fixes in public code, not as a promise of a particular fix rate on your next review.
