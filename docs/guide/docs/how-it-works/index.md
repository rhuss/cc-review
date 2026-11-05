# How it works

<!-- Sources:
cc-review:README.md:3-6
cc-review:README.md:11
cc-review:README.md:329-391
-->

Every review run has the same shape. A panel of focused reviewers each read your changes in their own fresh context, two critics filter the findings they return, and a fix loop resolves the blocking ones and re-reviews until the gate is clear. What reaches you at the end is one report of fewer, higher-confidence issues, with the Critical and Important ones already fixed wherever cc-review could fix them, instead of a separate comment stream from every reviewer and tool. The pages below take that run apart one layer at a time.

The pages, in reading order:

- [The review pipeline](pipeline.md) walks the stages a single run moves through, from discovering the reviewers to writing the final report.
- [Reviewers](reviewers.md) describes the panel itself: the six built-in lanes, the external tools, the opt-in Gator persona, and the rules every reviewer follows.
- [Meta-review](meta-review.md) covers the two critics, the Skeptic and the Calibrator, that judge the merged findings before anything is acted on.
- [Gate and fix](gate-and-fix.md) explains the pass-or-fix gate and the autonomous loop that clears the blocking findings so the gate can pass.
- [Measured results](results.md) reports how cc-review has performed in practice, as dated measurements from recorded runs on public and local code.
