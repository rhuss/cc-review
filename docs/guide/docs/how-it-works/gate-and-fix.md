# Gate and fix

<!-- Sources:
cc-review:review/core/commands/review.md:916-925
cc-review:review/core/commands/review.md:997-1001
cc-review:review/core/commands/review.md:1005-1015
cc-review:README.md:139
cc-review:README.md:141
cc-review:README.md:386-390
-->

By the time the findings reach this stage, meta-review has filtered them into one list (see [Meta-review](meta-review.md)). cc-review now has to turn that list into a decision: is the change ready, or does something still need fixing first? Two mechanisms do that. The gate reads the list and returns a verdict, and the fix loop tries to clear the findings that fail the gate so the verdict can flip to a pass.

## The gate

The gate is a count, not a judgment. cc-review counts the findings whose severity is one that blocks a merge. Which severities those are comes from a configuration setting, `REQUEST_CHANGES_SEVERITIES`, which holds Critical and Important by default. If the count is zero, the review is a **gate pass**. If the count is above zero, the review is a **gate fail**, and it stays failed unless the fix loop clears those findings within its round limit.

Minor and Notable findings fall outside that set, so neither one blocks a pass on its own. Notable findings are informational by definition, and Minor findings are reported for the record, yet the gate does not weigh either. A change can therefore carry a long tail of small suggestions and still pass, as long as nothing Critical or Important remains.

On a follow-up review the gate also accounts for concerns carried over from earlier rounds. A material concern that an earlier review raised and that is still open keeps the gate from a clean pass, even when the new changes add no findings of their own. An unresolved question from a previous round counts as unfinished work rather than as something the new diff quietly settled.

## The fix loop

When the gate fails and the run is set to fix, cc-review enters an autonomous fix loop. The loop runs a bounded number of rounds. The limit comes from the `max_fix_rounds` configuration setting and defaults to 3.

Each round has the same shape. cc-review gathers the findings it will act on and groups them by file. The Critical and Important findings are always in scope; when the run asked for all fixes rather than only the blocking ones, every Minor and Notable finding that carries a concrete suggested fix joins them. Inside each file, cc-review applies the fixes from the bottom of the file upward, working through the findings in descending line order. Editing the lower lines first would shift the line numbers of the findings still waiting above them, so starting from the bottom keeps every remaining line reference accurate.

Once the edits are staged, cc-review runs the project's test suite if it could detect one. A passing suite lets the round proceed. A failing test does not: cc-review turns each failure into a new Critical finding with the category `regression`. A fix that breaks the build cannot pass itself off as a clean result, because it returns as a fresh blocking finding in the same loop.

cc-review then re-reviews only the files the round changed. It re-dispatches the same reviewers that ran the first time, restricted to the modified files, and reuses the earlier decisions about which reviewers were enabled rather than running discovery again. The new findings are merged with the Minor findings still on the list, and the gate runs once more. If Critical and Important are both at zero, the loop passes and stops early.

If the blocking findings are not cleared, the loop tries again, up to the three-round default. When it reaches that limit with findings still open, the gate-fail result stands and the review reports what remains instead of looping on. The loop exists to clear the issues it can fix automatically, not to force a pass.

## Follow-up reviews converge

A pull request is rarely reviewed only once. When you ask cc-review to review a PR again after pushing more commits, it does not start over. A follow-up reviews the changes since your last trustworthy completed run, including the code you changed to address earlier findings.

Earlier concerns are neither forgotten nor silently cleared. cc-review verifies each one explicitly against the current code and keeps it in its original thread until it is addressed. A concern that does not reappear in the new round never counts as proof that it was fixed. cc-review also remembers the earlier discussion, both its own comments and your replies, so it continues an existing concern instead of opening a duplicate, and it explains itself when it reverses advice it gave before.

The aim of a follow-up is to converge, not to accumulate. New findings focus on material problems, so optional polish does not open another round, and a critical finding on code the latest commits did not touch needs concrete evidence before it is raised. Once the verification is done and nothing substantive is left, the report can conclude that there are **no outstanding material concerns**. That is a legitimate result, not a sign of an incomplete review. A clean conclusion still does not approve or merge the PR on its own. It tells you the change is clear, and the decision stays with you.

To see where the gate and the fix loop sit in a full run, from discovery through the final report, see [The review pipeline](pipeline.md).
